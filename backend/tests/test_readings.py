import copy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.collection import CollectionError
from backend.config import Settings
from backend.main import create_app
from backend.shared_workspace import SharedWorkspaceStore
from backend.tests.import_fixtures import wav_bytes
from backend.tests.test_hosted import HostedCase
from backend.workspace_backups import build_archive, validate_archive


class RecordedReadingTests(HostedCase):
    def setUp(self):
        super().setUp()
        self.content = wav_bytes()

    def upload(self, client=None, *, text="  Tchop\t", language="fr", content=None, fields=None, filename="reading.wav"):
        return (client or self.client).post(
            "/api/readings/audio",
            data={"fields": json.dumps(fields if fields is not None else {
                "text": text, "language": language, "share_consent": True,
            })},
            files={"file": (filename, self.content if content is None else content, "audio/wav")},
        )

    def lookup(self, client=None, *, text="tchop", language="fr"):
        return (client or self.client).post("/api/readings/lookup", json={"text": text, "language": language})

    def replace(self, record, client=None, content=None):
        return (client or self.client).patch(
            f"/api/readings/{record['id']}/audio", data={"fields": json.dumps({"share_consent": True})},
            files={"file": ("replacement.wav", self.content if content is None else content, "audio/wav")},
        )

    def test_readings_require_authentication_csrf_valid_text_language_and_consent(self):
        self.assertEqual(self.lookup().status_code, 401)
        self.assertEqual(self.upload().status_code, 401)
        self.register()
        self.assertEqual(self.lookup().json(), {"reading": None})
        for fields in (
            {"text": "", "language": "fr", "share_consent": True},
            {"text": " \t", "language": "fr", "share_consent": True},
            {"text": "x" * 4001, "language": "fr", "share_consent": True},
            {"text": "tchop", "language": "unsupported", "share_consent": True},
            {"text": "tchop", "language": "fr"},
            {"text": "tchop", "language": "fr", "share_consent": False},
            {"text": "tchop", "language": "fr", "share_consent": 1},
            {"text": "tchop", "language": "fr", "share_consent": True, "owner_id": "forged"},
        ):
            with self.subTest(fields=list(fields)):
                self.assertEqual(self.upload(fields=fields).status_code, 422)
        self.assertEqual(self.client.post(
            "/api/readings/lookup", json={"text": "tchop", "language": "fr"},
            headers={"X-CSRF-Token": "wrong"},
        ).status_code, 403)
        self.assertEqual(self.lookup().json(), {"reading": None})

    def test_recordings_are_shared_without_creating_fieldwork_or_analyzer_tests(self):
        user = self.register()
        saved = self.upload()
        self.assertEqual(saved.status_code, 201, saved.text)
        record = saved.json()
        self.assertEqual(record["text"], "  Tchop\t")
        self.assertEqual(record["ownership"]["owner_id"], user["id"])
        self.assertTrue(record["ownership"]["can_edit"])
        self.assertEqual(self.lookup().json()["reading"], record)
        self.assertEqual(self.lookup(language="en").json(), {"reading": None})
        self.assertEqual(self.lookup(text="tchop!").json(), {"reading": None})
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(self.client.get("/api/analyzer/tests").json()["summary"]["total"], 0)
        audio = self.client.get(record["audio_url"])
        self.assertEqual(audio.content, self.content)
        self.assertEqual(audio.headers["cache-control"], "private, no-store")
        ranged = self.client.get(record["audio_url"], headers={"Range": "bytes=0-15"})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, self.content[:16])
        other = self.other()
        self.register(other, "second@example.com")
        shared = self.lookup(other).json()["reading"]
        self.assertEqual(shared["ownership"]["owner_id"], user["id"])
        self.assertFalse(shared["ownership"]["can_edit"])
        self.assertEqual(other.get(record["audio_url"]).content, self.content)
        self.assertEqual(self.replace(record, other).status_code, 403)
        self.assertEqual(other.delete(f"/api/readings/{record['id']}").status_code, 403)

    def test_duplicate_casefolded_recording_keeps_creator_audio_and_disk_usage(self):
        user = self.register()
        original = self.upload().json()
        store = self.shared_store(user)
        before = store.export_document()
        files = sorted(path.name for path in store.audio_dir.iterdir())
        duplicate = self.upload(text="TCHOP")
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(self.lookup().json()["reading"], original)
        self.assertEqual(store.export_document(), before)
        self.assertEqual(sorted(path.name for path in store.audio_dir.iterdir()), files)

    def test_creator_can_replace_remove_and_recreate_without_reassigning_old_ownership(self):
        user = self.register()
        store = self.shared_store(user)
        original = self.upload().json()
        changed_bytes = self.content[:-2] + b"\x05\x00"
        changed = self.replace(original, content=changed_bytes)
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["id"], original["id"])
        self.assertEqual(changed.json()["created_at"], original["created_at"])
        self.assertEqual(self.client.get(original["audio_url"]).content, changed_bytes)
        self.assertTrue((store.audio_dir / original["audio_filename"]).is_file())
        self.assertEqual(self.client.delete(f"/api/readings/{original['id']}").status_code, 204)
        self.assertEqual(self.lookup().json(), {"reading": None})
        self.assertEqual(self.client.get(original["audio_url"]).status_code, 404)
        other = self.other()
        second = self.register(other, "second@example.com")
        recreated = self.upload(other).json()
        self.assertNotEqual(recreated["id"], original["id"])
        self.assertEqual(recreated["ownership"]["owner_id"], second["id"])
        self.assertEqual(store.ownership("reading", original["id"]).owner_id, user["id"])

    def test_invalid_audio_and_failed_writes_leave_no_uncommitted_files_or_rows(self):
        user = self.register()
        store = self.shared_store(user)
        before = store.export_document()
        for filename, data, status in (
            ("reading.txt", self.content, 415), ("reading.wav", b"bad", 422),
            ("reading.wav", b"", 422), ("reading.wav", self.content[:50], 422),
        ):
            with self.subTest(filename=filename, length=len(data)):
                self.assertEqual(self.upload(filename=filename, content=data).status_code, status)
        with patch("backend.audio_api.MAX_FILE_BYTES", 8):
            self.assertEqual(self.upload().status_code, 413)
        with patch.object(SharedWorkspaceStore, "bump", side_effect=sqlite3.OperationalError("PRIVATE path")):
            failed = self.upload()
        self.assertEqual(failed.status_code, 500)
        self.assertNotIn("PRIVATE", failed.text)
        self.assertEqual(store.export_document(), before)
        self.assertEqual(list(store.audio_dir.iterdir()), [])

    def test_recordings_survive_reopening_and_owned_backup_restore(self):
        user = self.register()
        original = self.upload().json()
        store = self.shared_store(user)
        document, audio = validate_archive(build_archive(store))
        self.assertEqual(document["format"], 5)
        self.assertEqual(len(document["readings"]), 1)
        self.assertEqual(audio[original["audio_filename"]], self.content)
        self.assertEqual(self.replace(original).status_code, 200)
        store.import_document(document, store.version)
        app = create_app(Settings(), require_auth=True, auth_settings=self.settings)
        with TestClient(app, headers={"Origin": "http://testserver"}) as reopened:
            self.login(reopened)
            self.assertEqual(self.lookup(reopened).json()["reading"], original)
            self.assertEqual(reopened.get(original["audio_url"]).content, self.content)

    def test_format4_remains_readable_but_cannot_erase_another_users_recording(self):
        user = self.register()
        store = self.shared_store(user)
        legacy = store.export_document()
        legacy["format"] = 4
        legacy.pop("readings")
        original = copy.deepcopy(legacy)
        normalized = SharedWorkspaceStore.validate_document(legacy)
        self.assertEqual(legacy, original)
        self.assertEqual(normalized["format"], 5)
        self.assertEqual(normalized["readings"], [])
        other = self.other()
        self.register(other, "second@example.com")
        saved = self.upload(other).json()
        with self.assertRaises(CollectionError) as denied:
            store.authorize_import(normalized)
        self.assertEqual(denied.exception.status_code, 403)
        self.assertEqual(self.client.get(saved["audio_url"]).content, self.content)

    def test_backup_validation_rejects_wrong_lookup_keys_duplicate_rows_and_missing_audio(self):
        user = self.register()
        self.upload()
        store = self.shared_store(user)
        original = store.export_document()
        for mutation in (
            lambda doc: doc["readings"][0].update(key="0" * 64),
            lambda doc: doc["readings"].append(copy.deepcopy(doc["readings"][0])),
            lambda doc: doc.update(ownership=[]),
        ):
            document = copy.deepcopy(original)
            mutation(document)
            with self.assertRaises(CollectionError):
                SharedWorkspaceStore.validate_document(document)
        record = self.lookup().json()["reading"]
        (store.audio_dir / record["audio_filename"]).unlink()
        with self.assertRaises(CollectionError) as missing:
            build_archive(store)
        self.assertEqual(missing.exception.status_code, 409)

    def test_concurrent_creators_cannot_overwrite_each_others_first_recording(self):
        self.register()
        other = self.other()
        self.register(other, "second@example.com")
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(self.upload, (self.client, other)))
        self.assertEqual(sorted(response.status_code for response in responses), [201, 409])
        saved = next(response.json() for response in responses if response.status_code == 201)
        self.assertEqual(self.lookup().json()["reading"]["id"], saved["id"])
