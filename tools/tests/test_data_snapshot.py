import csv
import io
import json
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from backend.coursework_store import default_project
from data_collector import dataset
from tools import data_snapshot


class DataSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="mboa-snapshot-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "audio").mkdir()
        self.audio = self.source / "audio" / "fixture.wav"
        with wave.open(str(self.audio), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(44100)
            audio.writeframes(b"\x00\x00" * 8)
        (self.source / "audio" / "unreferenced.wav").write_bytes(self.audio.read_bytes())
        self.profile = self.source / "coursework" / "project.json"
        self.profile.parent.mkdir()
        profile = default_project().model_copy(update={"discussion": "Synthetic test, not fieldwork"})
        self.profile.write_text(profile.model_dump_json(), encoding="utf-8")
        screenshots = self.profile.parent / "screenshots"
        screenshots.mkdir()
        Image.new("RGB", (8, 8), "white").save(screenshots / "fixture.png")
        self.backup = self.root / "backup"
        self.restored = self.root / "restored"
        self.write_csv(dataset.FIELDNAMES)

    def write_csv(self, fields: list[str], audio: str = "fixture.wav") -> None:
        row = {field: "" for field in fields}
        row.update(
            id="fixture", text='Texte \u00e9tudi\u00e9, "exact"\nseconde ligne',
            entry_type="Sentence", category="Campus Life", audio_filename=audio,
        )
        with (self.source / "dataset.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerow(row)

    def manifest(self) -> dict:
        return json.loads((self.backup / data_snapshot.MANIFEST_NAME).read_text(encoding="utf-8"))

    def change_manifest(self, manifest: dict) -> None:
        (self.backup / data_snapshot.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    def test_round_trip_preserves_exact_bytes_and_all_managed_data(self) -> None:
        original = {
            path.relative_to(self.source): path.read_bytes()
            for path in self.source.rglob("*") if path.is_file()
        }
        report = data_snapshot.create_backup(self.source, self.backup)
        self.assertEqual(report["entries"], 1)
        self.assertEqual(report["referenced_audio"], 1)
        self.assertEqual(report["files"], 5)
        self.assertEqual(data_snapshot.restore_backup(self.backup, self.restored), report)
        for relative, content in original.items():
            self.assertEqual((self.restored / relative).read_bytes(), content)
            self.assertEqual((self.source / relative).read_bytes(), content)
        with wave.open(str(self.restored / "audio" / "fixture.wav")) as audio:
            self.assertEqual(audio.getnframes(), 8)
            self.assertEqual(audio.getframerate(), 44100)
        with Image.open(self.restored / "coursework" / "screenshots" / "fixture.png") as image:
            image.verify()
        self.assertEqual(data_snapshot.verify_backup(self.restored), report)

    def test_all_supported_headers_are_preserved_without_migration(self) -> None:
        for index, fields in enumerate((
            dataset.FIELDNAMES, dataset.PRE_REVIEW_FIELDNAMES, dataset.LEGACY_FIELDNAMES,
        )):
            with self.subTest(fields=len(fields)):
                self.write_csv(fields)
                original = (self.source / "dataset.csv").read_bytes()
                destination = self.root / f"schema-{index}"
                data_snapshot.create_backup(self.source, destination)
                self.assertEqual((destination / "dataset.csv").read_bytes(), original)

    def test_credentials_locks_and_temporary_files_are_not_included(self) -> None:
        (self.source / ".env").write_text("DUMMY_SECRET=never-copy", encoding="utf-8")
        (self.source / ".dataset-unfinished.tmp").write_text("partial", encoding="utf-8")
        (self.profile.parent / ".write-unfinished").write_text("partial", encoding="utf-8")
        (self.source / "audio" / ".gitkeep").touch()
        data_snapshot.create_backup(self.source, self.backup)
        names = {record["path"] for record in self.manifest()["files"]}
        self.assertEqual(names, {
            "dataset.csv", "audio/fixture.wav", "audio/unreferenced.wav",
            "coursework/project.json", "coursework/screenshots/fixture.png",
        })

    def test_existing_destination_is_never_overwritten(self) -> None:
        self.backup.mkdir()
        marker = self.backup / "keep.txt"
        marker.write_text("Keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            data_snapshot.create_backup(self.source, self.backup)
        self.assertEqual(marker.read_text(encoding="utf-8"), "Keep me")

    def test_restore_refuses_live_or_existing_directory(self) -> None:
        data_snapshot.create_backup(self.source, self.backup)
        original = (self.source / "dataset.csv").read_bytes()
        with self.assertRaises(FileExistsError):
            data_snapshot.restore_backup(self.backup, self.source)
        self.assertEqual((self.source / "dataset.csv").read_bytes(), original)

    def test_nested_destination_is_refused(self) -> None:
        with self.assertRaisesRegex(ValueError, "outside"):
            data_snapshot.create_backup(self.source, self.source / "backup")

    def test_missing_referenced_audio_is_an_explicit_failure(self) -> None:
        self.audio.unlink()
        with self.assertRaisesRegex(ValueError, "Referenced audio"):
            data_snapshot.create_backup(self.source, self.backup)
        self.assertFalse(self.backup.exists())
        self.assertEqual(list(self.root.glob(".mboa-snapshot-*")), [])

    def test_malformed_csv_is_not_published(self) -> None:
        (self.source / "dataset.csv").write_text("wrong,header\n1,2\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "CSV header"):
            data_snapshot.create_backup(self.source, self.backup)
        self.assertFalse(self.backup.exists())

    def test_unsafe_audio_reference_is_rejected(self) -> None:
        for filename in ("../outside.wav", "C:\\outside.wav", "/outside.wav", "a\\b.wav"):
            with self.subTest(filename=filename):
                self.write_csv(dataset.FIELDNAMES, filename)
                with self.assertRaises(ValueError):
                    data_snapshot.create_backup(self.source, self.backup)
                self.assertFalse(self.backup.exists())

    def test_file_corruption_is_detected_before_restoration(self) -> None:
        data_snapshot.create_backup(self.source, self.backup)
        (self.backup / "audio" / "fixture.wav").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "damaged or changed"):
            data_snapshot.restore_backup(self.backup, self.restored)
        self.assertFalse(self.restored.exists())

    def test_missing_and_unexpected_files_are_reported(self) -> None:
        data_snapshot.create_backup(self.source, self.backup)
        extra = self.backup / ".env"
        extra.write_text("unexpected", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            data_snapshot.verify_backup(self.backup)
        extra.unlink()
        (self.backup / "audio" / "fixture.wav").unlink()
        with self.assertRaisesRegex(ValueError, "inventory mismatch"):
            data_snapshot.verify_backup(self.backup)

    def test_manifest_paths_and_digests_are_validated(self) -> None:
        data_snapshot.create_backup(self.source, self.backup)
        original = self.manifest()
        changes = (
            {"path": "../outside"},
            {"path": "audio\\outside"},
            {"path": ".env"},
            {"path": "audio/./fixture.wav"},
            {"size": True},
            {"size": -1},
            {"sha256": "not-a-digest"},
        )
        for change in changes:
            with self.subTest(change=change):
                manifest = json.loads(json.dumps(original))
                manifest["files"][0].update(change)
                self.change_manifest(manifest)
                with self.assertRaises(ValueError):
                    data_snapshot.verify_backup(self.backup)

    def test_duplicate_case_colliding_paths_are_rejected(self) -> None:
        data_snapshot.create_backup(self.source, self.backup)
        manifest = self.manifest()
        audio = next(record for record in manifest["files"] if record["path"] == "audio/fixture.wav")
        manifest["files"].append({**audio, "path": "audio/FIXTURE.wav"})
        self.change_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "case-colliding"):
            data_snapshot.verify_backup(self.backup)

    def test_linked_audio_is_not_followed(self) -> None:
        outside = self.root / "outside.wav"
        outside.write_bytes(b"outside")
        link = self.source / "audio" / "linked.wav"
        try:
            link.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"This environment cannot create a symlink: {exc}")
        with self.assertRaisesRegex(ValueError, "Links and reparse"):
            data_snapshot.create_backup(self.source, self.backup)

    def test_concurrent_file_change_aborts_without_publishing(self) -> None:
        original_copy = data_snapshot.shutil.copy2
        changed = []

        def changed_copy(source, destination):
            result = original_copy(source, destination)
            if Path(source).samefile(self.audio):
                self.audio.write_bytes(b"changed-during-backup")
                changed.append(Path(source))
            return result

        with patch.object(data_snapshot.shutil, "copy2", side_effect=changed_copy):
            with self.assertRaisesRegex(ValueError, "changed during copying"):
                data_snapshot.create_backup(self.source, self.backup)
        self.assertEqual(len(changed), 1, "The source-change fault must actually be injected.")
        self.assertFalse(self.backup.exists())
        self.assertEqual(list(self.root.glob(".mboa-snapshot-*")), [])

    def test_source_change_is_detected_with_equivalent_noncanonical_paths(self) -> None:
        self.audio = self.audio.parent / ".." / "audio" / self.audio.name
        self.test_concurrent_file_change_aborts_without_publishing()

    def test_cli_reports_success_and_failure_truthfully(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            code = data_snapshot.main([
                "backup", "--source", str(self.source), "--destination", str(self.backup),
            ])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["verified"])
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
            data_snapshot.main(["restore", str(self.backup), "--destination", str(self.source)])
        self.assertEqual(failure.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
