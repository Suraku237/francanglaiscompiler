import io
import json
import wave
from pathlib import Path
from unittest.mock import patch

from backend.tests.test_api import ApiTestCase
from data_collector import dataset


def wav_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 1600)
    return output.getvalue()


class AudioApiTests(ApiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.content = wav_bytes()

    def create_audio(self, **fields):
        return self.client.post(
            "/api/dataset/audio",
            data={"fields": json.dumps({"text": "Audio test", "language": "francanglais", **fields})},
            files={"file": ("capture.wav", self.content, "audio/wav")},
        )

    def test_create_audio_and_playback_stay_local(self):
        response = self.create_audio(contributor="Test contributor", notes="Keep exact provenance")
        self.assertEqual(response.status_code, 201, response.text)
        entry = response.json()
        self.assertEqual(entry["review_status"], "unreviewed")
        self.assertEqual(entry["notes"], "Keep exact provenance")
        self.assertNotEqual(entry["audio_filename"], "capture.wav")
        saved = self.client.get(f"/api/dataset/{entry['id']}/audio")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.content, self.content)
        self.assertEqual(saved.headers["cache-control"], "private, no-store")
        ranged = self.client.get(f"/api/dataset/{entry['id']}/audio", headers={"Range": "bytes=0-15"})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, self.content[:16])
        self.assertEqual(self.requests, [])

    def test_replacement_resets_review_and_preserves_old_committed_file(self):
        original = self.create_audio(review_status="approved", contributor="Original collector").json()
        response = self.client.patch(
            f"/api/dataset/{original['id']}/audio",
            data={"fields": json.dumps({"notes": "Reviewed separately"})},
            files={"file": ("new.wav", self.content, "audio/wav")},
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = response.json()
        self.assertEqual(updated["review_status"], "unreviewed")
        self.assertEqual(updated["contributor"], "Original collector")
        self.assertNotEqual(updated["audio_filename"], original["audio_filename"])
        self.assertTrue((Path(dataset.AUDIO_DIR) / original["audio_filename"]).exists())

    def test_detach_is_explicit_and_retains_committed_audio(self):
        created = self.create_audio(review_status="approved")
        self.assertEqual(created.status_code, 201, created.text)
        original = created.json()
        response = self.client.patch(
            f"/api/dataset/{original['id']}/audio",
            files={
                "fields": (None, json.dumps({"review_status": "unreviewed"})),
                "remove_audio": (None, "true"),
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["audio_filename"], "")
        self.assertTrue((Path(dataset.AUDIO_DIR) / original["audio_filename"]).exists())
        self.assertEqual(self.client.get(f"/api/dataset/{original['id']}/audio").status_code, 404)

    def test_duplicate_does_not_leave_an_uncommitted_attachment(self):
        self.assertEqual(self.create_audio().status_code, 201)
        before = list(Path(dataset.AUDIO_DIR).iterdir())
        duplicate = self.create_audio()
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), before)
        self.assertEqual(len(dataset.load_all()), 1)

    def test_failed_csv_write_cleans_only_the_new_attachment(self):
        with patch.object(dataset, "append_entry", side_effect=OSError("Write denied")):
            response = self.create_audio()
        self.assertEqual(response.status_code, 500, response.text)
        self.assertIn("Cannot read or save", response.json()["detail"])
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])
        self.assertEqual(dataset.load_all(), [])

    def test_invalid_and_truncated_audio_are_not_saved(self):
        for filename, data, expected in (
            ("capture.txt", b"not audio", 415),
            ("capture.wav", b"not audio", 422),
            ("capture.wav", self.content[:50], 422),
            ("capture.wav", b"", 422),
        ):
            with self.subTest(filename=filename, length=len(data)):
                response = self.client.post(
                    "/api/dataset/audio", data={"fields": '{"text":"Not saved"}'},
                    files={"file": (filename, data, "audio/wav")},
                )
                self.assertEqual(response.status_code, expected, response.text)
        self.assertEqual(dataset.load_all(), [])
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), [])

    def test_audio_limit_is_enforced_before_storage(self):
        with patch("backend.audio_api.MAX_FILE_BYTES", 64):
            response = self.create_audio()
        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(dataset.load_all(), [])

    def test_entry_fields_cannot_override_server_audio_path(self):
        response = self.create_audio(audio_filename="outside.wav")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(dataset.load_all(), [])

    def test_failed_edit_preserves_existing_audio(self):
        original = self.create_audio().json()
        before = list(Path(dataset.AUDIO_DIR).iterdir())
        response = self.client.patch(
            f"/api/dataset/{original['id']}/audio",
            data={"fields": '{"category":"Not an allowed topic"}'},
            files={"file": ("new.wav", self.content, "audio/wav")},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(list(Path(dataset.AUDIO_DIR).iterdir()), before)
        self.assertEqual(dataset.load_all()[0]["audio_filename"], original["audio_filename"])

    def test_conflicting_attachment_instructions_are_rejected(self):
        original = self.create_audio().json()
        response = self.client.patch(
            f"/api/dataset/{original['id']}/audio",
            data={"fields": '{"review_status":"unreviewed"}', "remove_audio": "true"},
            files={"file": ("new.wav", self.content, "audio/wav")},
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(dataset.load_all()[0]["audio_filename"], original["audio_filename"])

    def test_audio_lookup_rejects_missing_and_traversing_paths(self):
        self.assertEqual(self.client.get("/api/dataset/missing/audio").status_code, 404)
        original = self.create_audio().json()
        for filename in ("../outside.wav", "..\\outside.wav", "missing.wav"):
            dataset.update_entry(original["id"], {"audio_filename": filename})
            response = self.client.get(f"/api/dataset/{original['id']}/audio")
            self.assertEqual(response.status_code, 404)

    def test_upload_rejects_extra_and_duplicate_fields(self):
        for fields in (
            [("fields", (None, '{"text":"Test"}')), ("unexpected", (None, "value"))],
            [("fields", (None, '{"text":"Test"}')), ("fields", (None, '{"text":"Other"}'))],
        ):
            response = self.client.post(
                "/api/dataset/audio",
                files=[("file", ("capture.wav", self.content, "audio/wav")), *fields],
            )
            self.assertIn(response.status_code, (400, 422), response.text)
        self.assertEqual(dataset.load_all(), [])
