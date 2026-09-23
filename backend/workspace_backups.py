import asyncio
import hashlib
import io
import json
import logging
import re
import sqlite3
import stat
import time
import zipfile
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse
from filelock import Timeout
from pydantic import Field
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .auth import private_directory
from .collection import CollectionError, storage_operation
from .file_storage import atomic_write
from .uploads import multipart_form
from .workspaces import WorkspaceInput, WorkspaceStore, current_workspace, media_name, now

logger = logging.getLogger(__name__)
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 160 * 1024 * 1024
MAX_BACKUP_DISK = 512 * 1024 * 1024


class BackupSettings(WorkspaceInput):
    automatic: bool = False
    interval_hours: Literal[24, 168] = 24
    keep_last: int = Field(default=3, ge=1, le=10)


class BackupRestore(WorkspaceInput):
    token: str = Field(pattern=r"^[0-9a-f]{32}$")
    expected_version: int = Field(ge=0)
    confirmation: Literal["REPLACE"]


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def get_metadata(store: WorkspaceStore, key: str, default):
    with store.connection() as db:
        row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_metadata(store: WorkspaceStore, key: str, value):
    with store.lock(), store.connection() as db:
        db.execute(
            "INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )


def backup_directory(store: WorkspaceStore) -> Path:
    path = store.root / "backups"
    private_directory(path)
    return path


def referenced_media(document: dict) -> set[str]:
    names = set()
    records = [row["data"] for row in document["entries"]]
    records += [
        row[key] for row in document["revisions"] for key in ("before_data", "after_data") if row[key]
    ]
    for content in records:
        value = json.loads(content)["audio_filename"]
        if value:
            names.add(media_name(value))
    return names


def build_archive(store: WorkspaceStore) -> bytes:
    document = store.export_document()
    files = {"workspace.json": json.dumps(document, ensure_ascii=False).encode("utf-8")}
    for path in store.audio_dir.iterdir():
        if not path.is_file() or path.is_symlink():
            raise CollectionError(409, "Audio storage contains an unsupported file; backup stopped.")
        files["audio/" + media_name(path.name)] = path.read_bytes()
    if not referenced_media(document).issubset({name.removeprefix("audio/") for name in files if name.startswith("audio/")}):
        raise CollectionError(409, "A recording referenced by the workspace or its revisions is missing.")
    if sum(len(content) for content in files.values()) > MAX_EXPANDED:
        raise CollectionError(409, "The workspace is too large for an in-app backup.")
    manifest = {"format": 1, "files": {name: checksum(content) for name, content in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps(manifest).encode())
    data = output.getvalue()
    if len(data) > MAX_ARCHIVE:
        raise CollectionError(409, "The backup exceeds 32 MB. Ask the operator for a server-level backup.")
    validate_archive(data)
    return data


def validate_archive(data: bytes) -> tuple[dict, dict[str, bytes]]:
    if len(data) > MAX_ARCHIVE:
        raise CollectionError(413, "Backups must not exceed 32 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if not 2 <= len(entries) <= 1002:
                raise ValueError("Archive file count")
            names = [entry.filename for entry in entries]
            if len(set(name.casefold() for name in names)) != len(names):
                raise ValueError("Duplicate file names")
            total = 0
            for entry in entries:
                name = entry.filename
                if name not in ("workspace.json", "manifest.json") and not re.fullmatch(
                    r"audio/[0-9a-f]{32}\.(wav|mp3|m4a|ogg|flac|webm)", name,
                ):
                    raise ValueError("Unsupported path")
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError("Linked or encrypted archive")
                limit = 1024 * 1024 if name == "manifest.json" else 32 * 1024 * 1024 if name == "workspace.json" else 12 * 1024 * 1024
                if entry.file_size > limit:
                    raise ValueError("File limit")
                total += entry.file_size
            if total > MAX_EXPANDED:
                raise ValueError("Expanded limit")
            files = {name: archive.read(name) for name in names}
            manifest = json.loads(files.pop("manifest.json"))
            if not isinstance(manifest, dict) or set(manifest) != {"format", "files"} or manifest["format"] != 1:
                raise ValueError("Invalid manifest")
            if manifest["files"] != {name: checksum(content) for name, content in files.items()}:
                raise ValueError("Checksum mismatch")
            document = WorkspaceStore.validate_document(json.loads(files.pop("workspace.json")))
            audio = {name.removeprefix("audio/"): content for name, content in files.items()}
            if not referenced_media(document).issubset(audio):
                raise ValueError("Missing media")
            from .audio_api import _audio_extension
            for name, content in audio.items():
                _audio_extension(name, content)
            return document, audio
    except (ValueError, TypeError, KeyError, OSError, zipfile.BadZipFile, RuntimeError, RecursionError) as exc:
        raise CollectionError(422, "This backup is invalid, damaged, unsupported or exceeds safe import limits.") from exc


def catalog(store: WorkspaceStore) -> list[dict]:
    with store.connection() as db:
        return sorted(
            [json.loads(row[0]) for row in db.execute("SELECT value FROM meta WHERE key LIKE 'backup:item:%'")],
            key=lambda row: (row["created_at"], row["id"]), reverse=True,
        )


def snapshot(store: WorkspaceStore, *, kind: str = "manual") -> dict:
    with store.lock():
        directory = backup_directory(store)
        data = build_archive(store)
        existing = [item for item in directory.iterdir() if item.suffix == ".zip"]
        if any(path.is_symlink() for path in existing):
            raise CollectionError(503, "Backup storage contains an unsupported file.")
        if sum(path.stat().st_size for path in existing) + len(data) > MAX_BACKUP_DISK:
            raise CollectionError(409, "Backup storage is full. Download and delete older backups first.")
        identifier = uuid4().hex
        entry = {"id": identifier, "created_at": now(), "size": len(data), "sha256": checksum(data), "kind": kind}
        path = directory / f"{identifier}.zip"
        atomic_write(path, data)
        try:
            set_metadata(store, "backup:item:" + identifier, entry)
        except (OSError, sqlite3.Error):
            path.unlink(missing_ok=True)
            raise
        return entry


def delete_backup(store: WorkspaceStore, identifier: str):
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise CollectionError(404, "Backup not found.")
    with store.lock(), store.connection() as db:
        row = db.execute("SELECT value FROM meta WHERE key=?", ("backup:item:" + identifier,)).fetchone()
        if not row:
            raise CollectionError(404, "Backup not found.")
        path = backup_directory(store) / f"{identifier}.zip"
        if path.is_symlink():
            raise CollectionError(409, "The backup storage path is invalid.")
        path.unlink(missing_ok=True)
        db.execute("DELETE FROM meta WHERE key=?", ("backup:item:" + identifier,))


def preview_backup(store: WorkspaceStore, content: bytes) -> dict:
    document, _ = validate_archive(content)
    with store.lock():
        directory = backup_directory(store) / "previews"
        private_directory(directory)
        for path in directory.glob("*.zip"):
            if path.is_file() and not path.is_symlink() and path.stat().st_mtime < time.time() - 3600:
                path.unlink()
        if len(list(directory.glob("*.zip"))) >= 3:
            raise CollectionError(409, "Up to three backup previews can be pending. Restore one or wait for expiry.")
        token = uuid4().hex
        atomic_write(directory / f"{token}.zip", content)
        info = {"token": token, "expires_at": time.time() + 3600, "workspace_version": store.version,
                "counts": {key: len(document[key]) for key in (
                    "projects", "entries", "history", "revisions", "coursework", "screenshots", "analyzer_tests",
                )},
                "warnings": [
                    "Restoring replaces all projects, collected entries, saved work, revisions, coursework profiles, "
                    "screenshots and recorded analyzer tests in your account. A safety backup is created first.",
                    "Older format-1 backups contain no coursework profiles or screenshots.",
                    "Older format-1 and format-2 backups contain no recorded analyzer tests.",
                ]}
        set_metadata(store, "backup:preview:" + token, info)
        return info


def restore_backup(store: WorkspaceStore, payload: BackupRestore) -> dict:
    with store.lock():
        key = "backup:preview:" + payload.token
        info = get_metadata(store, key, None)
        if not info or info["expires_at"] <= time.time():
            raise CollectionError(400, "This backup preview expired or was already used. Preview it again.")
        if payload.expected_version != info["workspace_version"] or store.version != payload.expected_version:
            raise CollectionError(409, "The workspace changed after preview. Preview the backup again.")
        path = backup_directory(store) / "previews" / f"{payload.token}.zip"
        if path.is_symlink() or not path.is_file():
            raise CollectionError(400, "The backup preview is unavailable.")
        document, audio = validate_archive(path.read_bytes())
        safety = snapshot(store, kind="pre-restore")
        created = []
        remap = {}
        try:
            for name, content in audio.items():
                target = store.audio_dir / name
                if target.is_symlink():
                    raise CollectionError(409, "The audio storage path is invalid.")
                if target.exists() and target.read_bytes() != content:
                    remap[name] = uuid4().hex + target.suffix
                    target = store.audio_dir / remap[name]
                if not target.exists():
                    store.check_audio_capacity(len(content))
                    atomic_write(target, content)
                    created.append(target)
            for table, columns in (("entries", ("data",)), ("revisions", ("before_data", "after_data"))):
                for row in document[table]:
                    for column in columns:
                        if row[column]:
                            record = json.loads(row[column])
                            record["audio_filename"] = remap.get(record["audio_filename"], record["audio_filename"])
                            row[column] = json.dumps(record)
            store.import_document(document, payload.expected_version)
        except (CollectionError, OSError, ValueError, sqlite3.Error):
            for created_path in created:
                created_path.unlink(missing_ok=True)
            raise
        with store.connection() as db:
            db.execute("DELETE FROM meta WHERE key=?", (key,))
        path.unlink(missing_ok=True)
        return {"counts": info["counts"], "pre_restore_backup_id": safety["id"], "workspace_version": store.version}


def maintenance_cycle(data_dir: Path) -> int:
    root = data_dir / "workspaces"
    if not root.exists():
        return 0
    completed = 0
    for directory in root.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        try:
            if str(UUID(directory.name)) != directory.name:
                continue
        except ValueError:
            continue
        store = None
        try:
            store = WorkspaceStore(data_dir, directory.name)
            with store.lock():
                settings = BackupSettings.model_validate(get_metadata(store, "backup:settings", {}))
                state = get_metadata(store, "backup:state", {})
                if not settings.automatic or state.get("last_attempt", 0) > time.time() - 300:
                    continue
                if state.get("last_success", 0) > time.time() - settings.interval_hours * 3600:
                    continue
                set_metadata(store, "backup:state", {**state, "last_attempt": time.time()})
                snapshot(store, kind="automatic")
                automatic = [item for item in catalog(store) if item["kind"] == "automatic"]
                for old in automatic[settings.keep_last:]:
                    delete_backup(store, old["id"])
                set_metadata(store, "backup:state", {"last_attempt": time.time(), "last_success": time.time(), "last_error": ""})
                completed += 1
        except (CollectionError, OSError, sqlite3.Error, Timeout, ValueError) as exc:
            logger.error("Automatic workspace backup failed (%s)", type(exc).__name__)
            if store is not None:
                try:
                    set_metadata(store, "backup:state", {
                        "last_attempt": time.time(), "last_error": "Automatic backup failed. Contact the operator or create a manual backup.",
                    })
                except (OSError, sqlite3.Error, Timeout):
                    logger.error("Could not record an automatic backup failure.")
    return completed


async def maintain_backups(data_dir: Path, stop: asyncio.Event):
    while not stop.is_set():
        try:
            await run_in_threadpool(maintenance_cycle, data_dir)
        except (CollectionError, OSError, sqlite3.Error, Timeout, ValueError) as exc:
            logger.error("Automatic backup maintenance failed (%s); retrying next minute.", type(exc).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            continue


def install_backups(app: FastAPI):
    router = APIRouter(prefix="/api/workspace/backups", tags=["Private backups"])

    @router.get("")
    def list_backups():
        store = current_workspace()
        return storage_operation(lambda: {
            "backups": catalog(store),
            "settings": BackupSettings.model_validate(get_metadata(store, "backup:settings", {})).model_dump(),
            "state": get_metadata(store, "backup:state", {}), "workspace_version": store.version,
        })

    @router.post("", status_code=201)
    def create_backup():
        return storage_operation(lambda: snapshot(current_workspace()))

    @router.patch("/settings")
    def settings(payload: BackupSettings):
        storage_operation(lambda: set_metadata(current_workspace(), "backup:settings", payload.model_dump()))
        return payload

    @router.post("/preview")
    async def preview(request: Request):
        async with multipart_form(request, fields=set(), max_file_bytes=MAX_ARCHIVE) as form:
            file = form.get("file")
            if not isinstance(file, UploadFile):
                raise CollectionError(422, "Select a workspace backup ZIP.")
            content = await file.read(MAX_ARCHIVE + 1)
            return await run_in_threadpool(lambda: storage_operation(lambda: preview_backup(current_workspace(), content)))

    @router.post("/restore")
    def restore(payload: BackupRestore):
        return storage_operation(lambda: restore_backup(current_workspace(), payload))

    @router.get("/{identifier}/download")
    def download(identifier: str):
        store = current_workspace()
        def response():
            entry = next((item for item in catalog(store) if item["id"] == identifier), None)
            if entry is None:
                raise CollectionError(404, "Backup not found.")
            path = backup_directory(store) / f"{entry['id']}.zip"
            if not path.is_file() or path.is_symlink() or checksum(path.read_bytes()) != entry["sha256"]:
                raise CollectionError(409, "This backup is missing or damaged.")
            return FileResponse(path, media_type="application/zip", filename=f"mboa-backup-{identifier}.zip")
        return storage_operation(response)

    @router.delete("/{identifier}", status_code=204)
    def remove(identifier: str):
        storage_operation(lambda: delete_backup(current_workspace(), identifier))

    app.include_router(router)
