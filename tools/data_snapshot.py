"""Verified local backups; restores always go to a new directory."""

import argparse
import csv
import hashlib
import json
import re
import shutil
import stat
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import TypedDict

from filelock import FileLock, Timeout

from data_collector import dataset

DEFAULT_SOURCE = Path(__file__).resolve().parents[1] / "data_collector"
MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 8 * 1024 * 1024


class FileRecord(TypedDict):
    path: str
    size: int
    sha256: str


class Verification(TypedDict):
    files: int
    bytes: int
    entries: int
    referenced_audio: int


def _plain_path(path: Path) -> None:
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError(f"Links and reparse points are not supported: {path}")


def _files_below(directory: Path) -> Iterator[Path]:
    _plain_path(directory)
    if not directory.is_dir():
        raise ValueError(f"Expected a directory: {directory}")
    for path in sorted(directory.iterdir()):
        _plain_path(path)
        if path.is_dir():
            yield from _files_below(path)
        elif path.is_file():
            yield path
        else:
            raise ValueError(f"Not a regular file: {path}")


def _digest(path: Path) -> str:
    _plain_path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _payload_name(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name or "\\" in name or ":" in name or "\x00" in name
        or path.is_absolute() or ".." in path.parts or path.as_posix() != name
    ):
        raise ValueError(f"Invalid snapshot path: {name!r}")
    if not (
        name in ("dataset.csv", "coursework/project.json")
        or (len(path.parts) >= 2 and path.parts[0] == "audio")
        or (len(path.parts) >= 3 and path.parts[:2] == ("coursework", "screenshots"))
    ):
        raise ValueError(f"Path is outside the supported data payload: {name!r}")
    return path


def _payload_files(source: Path) -> list[Path]:
    _plain_path(source)
    csv_path = source / "dataset.csv"
    _plain_path(csv_path)
    if not csv_path.is_file():
        raise ValueError("The source must contain a dataset.csv file.")
    files = [csv_path]
    audio = source / "audio"
    if audio.exists() or audio.is_symlink():
        files.extend(path for path in _files_below(audio) if path.name != ".gitkeep")
    coursework = source / "coursework"
    if coursework.exists() or coursework.is_symlink():
        _plain_path(coursework)
        if not coursework.is_dir():
            raise ValueError("The coursework path is not a directory.")
        profile = coursework / "project.json"
        if profile.exists() or profile.is_symlink():
            _plain_path(profile)
            if not profile.is_file():
                raise ValueError("The coursework profile is not a regular file.")
            files.append(profile)
        screenshots = coursework / "screenshots"
        if screenshots.exists() or screenshots.is_symlink():
            files.extend(_files_below(screenshots))
    return sorted(files)


def _csv_details(path: Path) -> tuple[int, set[str]]:
    references: set[str] = set()
    count = 0
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames not in (
            dataset.FIELDNAMES, dataset.PRE_REVIEW_FIELDNAMES, dataset.LEGACY_FIELDNAMES,
        ):
            raise ValueError("The CSV header is not a supported current or legacy schema.")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("The CSV contains an incomplete or malformed row.")
            count += 1
            audio = row["audio_filename"]
            if audio:
                if PurePosixPath(audio).name != audio:
                    raise ValueError("An audio reference must be a filename, not a path.")
                references.add(_payload_name(f"audio/{audio}").as_posix())
    return count, references


def _read_manifest(snapshot: Path) -> list[FileRecord]:
    path = snapshot / MANIFEST_NAME
    _plain_path(path)
    if path.stat().st_size > MAX_MANIFEST_BYTES:
        raise ValueError("The snapshot manifest is too large.")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or set(manifest) != {"version", "created_at", "files"}:
        raise ValueError("Invalid snapshot manifest structure.")
    if type(manifest["version"]) is not int or manifest["version"] != 1:
        raise ValueError("Unsupported snapshot manifest version.")
    if not isinstance(manifest["created_at"], str):
        raise ValueError("The snapshot timestamp is invalid.")
    timestamp = datetime.fromisoformat(manifest["created_at"])
    if timestamp.tzinfo is None:
        raise ValueError("The snapshot timestamp must include its timezone.")
    if not isinstance(manifest["files"], list) or not manifest["files"]:
        raise ValueError("The snapshot must list its data files.")
    records: list[FileRecord] = []
    seen: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "size", "sha256"}:
            raise ValueError("Invalid file record in snapshot manifest.")
        name, size, digest = entry["path"], entry["size"], entry["sha256"]
        if not isinstance(name, str):
            raise ValueError("Snapshot file paths must be strings.")
        _payload_name(name)
        if name.casefold() in seen:
            raise ValueError(f"Duplicate or case-colliding snapshot path: {name}")
        if type(size) is not int or size < 0:
            raise ValueError(f"Invalid file size for {name}.")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"Invalid SHA-256 digest for {name}.")
        seen.add(name.casefold())
        records.append({"path": name, "size": size, "sha256": digest})
    if "dataset.csv" not in {record["path"] for record in records}:
        raise ValueError("The manifest must include dataset.csv.")
    return records


def verify_backup(snapshot: Path) -> Verification:
    _plain_path(snapshot)
    records = _read_manifest(snapshot)
    actual = {path.relative_to(snapshot).as_posix() for path in _files_below(snapshot)}
    expected = {MANIFEST_NAME, *(record["path"] for record in records)}
    if actual != expected:
        raise ValueError(
            f"Snapshot file inventory mismatch; missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}."
        )
    for record in records:
        path = snapshot.joinpath(*_payload_name(record["path"]).parts)
        if path.stat().st_size != record["size"] or _digest(path) != record["sha256"]:
            raise ValueError(f"Snapshot file is damaged or changed: {record['path']}")
    entries, references = _csv_details(snapshot / "dataset.csv")
    if missing := references - actual:
        raise ValueError(f"Referenced audio is absent from the snapshot: {sorted(missing)}")
    return {
        "files": len(records),
        "bytes": sum(record["size"] for record in records),
        "entries": entries,
        "referenced_audio": len(references),
    }


def _destination(source: Path, destination: Path) -> Path:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Destination already exists; choose a new directory: {destination}")
    source = source.resolve(strict=True)
    destination = destination.absolute()
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ValueError("The destination parent must be an existing directory.")
    resolved = parent / destination.name
    if resolved == source or resolved.is_relative_to(source):
        raise ValueError("The destination must be outside the source directory.")
    return resolved


def _copy_file(source: Path, destination: Path) -> FileRecord:
    before = _digest(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    copied = _digest(destination)
    if before != copied or before != _digest(source):
        raise ValueError(f"A source file changed during copying: {source.name}")
    return {"path": "", "size": destination.stat().st_size, "sha256": copied}


def _publish(staged: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Destination appeared during copying: {destination}")
    staged.rename(destination)


def create_backup(source: Path, destination: Path) -> Verification:
    _plain_path(source)
    source = source.resolve(strict=True)
    destination = _destination(source, destination)
    with ExitStack() as locks:
        locks.enter_context(FileLock(source / "dataset.csv.lock", timeout=10))
        coursework = source / "coursework"
        if coursework.exists() or coursework.is_symlink():
            _plain_path(coursework)
            locks.enter_context(FileLock(coursework / "project.lock", timeout=10))
            locks.enter_context(FileLock(coursework / "screenshots.lock", timeout=10))
        sources = _payload_files(source)
        with tempfile.TemporaryDirectory(prefix=".mboa-snapshot-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "snapshot"
            staged.mkdir()
            records: list[FileRecord] = []
            for path in sources:
                name = path.relative_to(source).as_posix()
                record = _copy_file(path, staged.joinpath(*_payload_name(name).parts))
                record["path"] = name
                records.append(record)
            if sources != _payload_files(source):
                raise ValueError("Data files changed during backup; close all apps and retry.")
            for path, record in zip(sources, records):
                if _digest(path) != record["sha256"]:
                    raise ValueError("Data changed during backup; close all apps and retry.")
            (staged / MANIFEST_NAME).write_text(
                json.dumps({
                    "version": 1,
                    "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "files": records,
                }, indent=2) + "\n",
                encoding="utf-8",
            )
            verification = verify_backup(staged)
            _publish(staged, destination)
    return verification


def restore_backup(snapshot: Path, destination: Path) -> Verification:
    verification = verify_backup(snapshot)
    destination = _destination(snapshot, destination)
    records = _read_manifest(snapshot)
    with tempfile.TemporaryDirectory(prefix=".mboa-restore-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "restored"
        staged.mkdir()
        for record in records:
            relative = _payload_name(record["path"])
            copied = _copy_file(snapshot.joinpath(*relative.parts), staged.joinpath(*relative.parts))
            if copied["sha256"] != record["sha256"] or copied["size"] != record["size"]:
                raise ValueError("The snapshot changed during restoration; nothing was published.")
        shutil.copy2(snapshot / MANIFEST_NAME, staged / MANIFEST_NAME)
        if verify_backup(staged) != verification:
            raise ValueError("Restored content does not match the verified snapshot.")
        (staged / "audio").mkdir(exist_ok=True)
        _publish(staged, destination)
    return verification


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Back up or verify local research data; restore only to a new directory.",
        epilog="Close all apps first. Backups contain private text, identities and recordings; keep them restricted.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    backup = commands.add_parser("backup", help="Create a verified snapshot in a new directory.")
    backup.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    backup.add_argument("--destination", type=Path, required=True)
    verify = commands.add_parser("verify", help="Check the complete inventory and SHA-256 hashes.")
    verify.add_argument("snapshot", type=Path)
    restore = commands.add_parser("restore", help="Restore to a new directory, never over live data.")
    restore.add_argument("snapshot", type=Path)
    restore.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            result = create_backup(args.source, args.destination)
        elif args.command == "verify":
            result = verify_backup(args.snapshot)
        else:
            result = restore_backup(args.snapshot, args.destination)
    except (OSError, ValueError, csv.Error, Timeout) as exc:
        parser.exit(1, f"Snapshot operation failed: {exc}\n")
    print(json.dumps({"operation": args.command, "verified": True, **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
