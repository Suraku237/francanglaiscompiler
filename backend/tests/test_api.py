import csv
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from filelock import Timeout

from backend import coursework_store
from backend.config import Settings
from backend.main import create_app
from backend.tests.support import block_outbound_http
from data_collector import dataset

class ApiTestCase(unittest.TestCase):
    include_academic = True

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix=".api-test-", dir=Path(__file__).parent,
        )))
        self.stack.enter_context(patch.object(dataset, "DATASET_PATH", str(self.directory / "dataset.csv")))
        self.stack.enter_context(patch.object(dataset, "AUDIO_DIR", str(self.directory / "audio")))
        self.stack.enter_context(patch.object(coursework_store, "PROJECT_DIR", self.directory / "coursework"))
        self.outbound_http = block_outbound_http(self.stack)
        self.stack.callback(self.assert_no_outbound_http)
        self.client = self.make_client()

    def assert_no_outbound_http(self) -> None:
        for transport in self.outbound_http:
            transport.assert_not_called()

    def make_client(self) -> TestClient:
        settings = Settings(cors_origins=["http://localhost:5173"])
        app = create_app(
            settings, include_academic=self.include_academic, require_auth=False,
        )
        return self.stack.enter_context(TestClient(app))

class ApiTests(ApiTestCase):
    def test_health_is_compiler_only_without_provider_details(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "mode": "compiler"})
        self.assert_no_outbound_http()

    def test_removed_generation_routes_are_404_and_absent_from_openapi(self) -> None:
        schema = self.client.get("/openapi.json").json()
        for path, payload in (
            ("/api/translate", {"text": "Bonjour"}),
            ("/api/chat", {"message": "Hello"}),
            ("/api/imports/suggest", {"text": "I di waka."}),
            ("/api/coursework/explain", {"grammar": "S -> NOUN", "text": "taxi"}),
        ):
            with self.subTest(path=path):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertNotIn(path, schema["paths"])
        self.assert_no_outbound_http()

    def test_analyze_validation_rejects_empty_overlong_and_extra_inputs(self) -> None:
        for payload in (
            {"text": ""}, {"text": " \n "}, {"text": "a" * 4001}, {"text": None},
            {"text": "taxi", "api_key": "not-accepted"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post("/api/analyze", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/api/analyze", json={"text": "a" * 4000}).status_code, 200)
        self.assert_no_outbound_http()

    def test_analyze_preserves_raw_input_before_lexing(self) -> None:
        from backend.main import analyze

        text = "  Où est le taxi ?\r\nJe n’ai pas d'argent.\t "
        with patch("backend.main.analyze", wraps=analyze) as analyze_call:
            response = self.client.post("/api/analyze", json={"text": text})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(analyze_call.call_args.args[0], text)
        self.assert_no_outbound_http()

    def test_lexer_and_coursework_metadata_are_local(self) -> None:
        response = self.client.post("/api/analyze", json={"text": "Le taxi don refuse."})
        self.assertEqual(response.status_code, 200)
        self.assertIn("don refuse", response.json()["verb_phrases"])
        self.assertEqual(response.json()["tokens"][2]["category"], "PIDGIN_MARKER")
        metadata = self.client.get("/api/metadata").json()
        self.assertEqual(metadata["categories"], dataset.CATEGORIES)
        self.assertEqual(metadata["entry_types"], dataset.ENTRY_TYPES)
        self.assert_no_outbound_http()

    def test_dataset_crud_search_stats_and_persistence(self) -> None:
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        created = self.client.post("/api/dataset", json={
            "text": "Le taxi don refuse.", "category": "Taxi / Commuting",
            "english_gloss": "The taxi refused.", "notes": "Line one\nLine two",
        })
        self.assertEqual(created.status_code, 201, created.text)
        entry_id = created.json()["id"]
        self.assertTrue(created.json()["timestamp"])
        response = self.client.get("/api/dataset", params={"query": "TAXI"})
        self.assertEqual(len(response.json()["entries"]), 1)
        self.assertEqual(response.json()["by_category"], {"Taxi / Commuting": 1})
        self.assertEqual(self.client.get("/api/dataset", params={"query": "absent"}).json()["total"], 1)
        updated = self.client.patch(f"/api/dataset/{entry_id}", json={"french_gloss": "Le taxi a refuse."})
        self.assertEqual(updated.status_code, 200)
        stored = dataset.load_all()[0]
        self.assertEqual(stored["french_gloss"], "Le taxi a refuse.")
        self.assertEqual(stored["notes"], "Line one\nLine two")
        self.assertEqual(self.make_client().get("/api/dataset").json()["total"], 1)
        deleted = self.client.delete(f"/api/dataset/{entry_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(deleted.content, b"")
        self.assertEqual(dataset.total_count(), 0)

    def test_duplicate_create_and_patch_rejected(self) -> None:
        self.client.post("/api/dataset", json={"text": "Original"})
        self.assertEqual(self.client.post("/api/dataset", json={"text": " original "}).status_code, 409)
        second = self.client.post("/api/dataset", json={"text": "Second"}).json()
        self.assertEqual(self.client.patch(f"/api/dataset/{second['id']}", json={"text": "ORIGINAL"}).status_code, 409)
        self.assertEqual(dataset.total_count(), 2)

    def test_missing_entry_and_invalid_edits(self) -> None:
        self.assertEqual(self.client.patch("/api/dataset/missing", json={"text": "changed"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/dataset/missing").status_code, 404)
        for payload in ({"text": " "}, {"text": None}, {"audio_filename": "../secret"}, {}, {"id": "changed"}):
            self.assertEqual(self.client.patch("/api/dataset/missing", json=payload).status_code, 422)
        self.assertEqual(self.client.post("/api/dataset", json={"text": "Hi", "category": "invalid"}).status_code, 422)

    def test_existing_record_metadata_preserved_on_edit(self) -> None:
        original = {field: "" for field in dataset.FIELDNAMES}
        original.update(
            id="legacy", text="Legacy entry", entry_type="Sentence",
            category="historical category", audio_filename="recording.wav", timestamp="old timestamp",
        )
        dataset.append_entry(original)
        response = self.client.patch("/api/dataset/legacy", json={"text": "Updated entry", "category": "historical category"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["audio_filename"], "recording.wav")
        self.assertEqual(response.json()["timestamp"], "old timestamp")

    def test_full_patch_can_preserve_legacy_type_and_category_while_editing_notes(self) -> None:
        for index, (entry_type, category) in enumerate((("", ""), ("Legacy type", "Historical topic"))):
            original = {field: "" for field in dataset.FIELDNAMES}
            original.update(
                id=f"legacy-{index}", text=f"Legacy entry {index}", entry_type=entry_type,
                category=category, audio_filename="recording.wav", timestamp="old timestamp",
            )
            dataset.append_entry(original)
            saved = dataset.load_all()[-1]
            patch_payload = {
                name: value for name, value in saved.items() if name not in ("id", "timestamp", "audio_filename")
            }
            patch_payload["notes"] = "Revised notes"
            response = self.client.patch(f"/api/dataset/{saved['id']}", json=patch_payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["entry_type"], entry_type)
            self.assertEqual(response.json()["category"], category)
            self.assertEqual(response.json()["notes"], "Revised notes")
            self.assertEqual(response.json()["timestamp"], "old timestamp")
            self.assertEqual(response.json()["audio_filename"], "recording.wav")
            for invalid in ({"entry_type": "New unsupported type"}, {"category": "New unsupported topic"}):
                self.assertEqual(self.client.patch(f"/api/dataset/{saved['id']}", json=invalid).status_code, 422)

    def test_legacy_csv_header_is_read_without_rewriting_and_upgraded_on_save(self) -> None:
        path = Path(dataset.DATASET_PATH)
        entry = {field: "" for field in dataset.LEGACY_FIELDNAMES}
        entry.update(id="legacy", text="Old expression", notes="Original notes", audio_filename="old.wav")
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=dataset.LEGACY_FIELDNAMES)
            writer.writeheader()
            writer.writerow(entry)
        original = path.read_bytes()
        response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["entries"][0]["source_location"], "")
        self.assertEqual(path.read_bytes(), original)
        changed = self.client.patch("/api/dataset/legacy", json={"source_location": "Campus"})
        self.assertEqual(changed.status_code, 200)
        saved = dataset.load_all()[0]
        self.assertEqual(saved["source_location"], "Campus")
        self.assertEqual(saved["notes"], "Original notes")
        self.assertEqual(saved["audio_filename"], "old.wav")
        with path.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(next(csv.reader(handle)), dataset.FIELDNAMES)

    def test_storage_failure_is_not_reported_as_success(self) -> None:
        with patch.object(dataset, "load_all", side_effect=OSError("private path")):
            response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("private path", response.text)

    def test_malformed_csv_not_overwritten(self) -> None:
        path = Path(dataset.DATASET_PATH)
        path.write_text("wrong,header\nuntouched,data\n", encoding="utf-8")
        response = self.client.post("/api/dataset", json={"text": "new"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(path.read_text(encoding="utf-8"), "wrong,header\nuntouched,data\n")

    def test_atomic_write_failure_preserves_original(self) -> None:
        self.client.post("/api/dataset", json={"text": "Original"})
        original = Path(dataset.DATASET_PATH).read_bytes()
        with patch.object(dataset.os, "replace", side_effect=OSError("disk failure")):
            response = self.client.post("/api/dataset", json={"text": "Second"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), original)
        self.assertEqual(list(self.directory.glob(".dataset-*.tmp")), [])

    def test_concurrent_appends_are_not_lost(self) -> None:
        def append(index: int) -> None:
            entry = {field: "" for field in dataset.FIELDNAMES}
            entry.update(id=str(index), text=f"Entry {index}")
            dataset.append_entry(entry)

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(append, range(16)))
        self.assertEqual(dataset.total_count(), 16)
        self.assertEqual(len({item["id"] for item in dataset.load_all()}), 16)
        with open(dataset.DATASET_PATH, newline="", encoding="utf-8") as handle:
            self.assertEqual(next(csv.reader(handle)), dataset.FIELDNAMES)

    def test_cors_is_restricted(self) -> None:
        allowed = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        denied = self.client.get("/api/health", headers={"Origin": "https://untrusted.example"})
        self.assertEqual(allowed.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertNotIn("access-control-allow-origin", denied.headers)

    def test_busy_collection_is_retryable(self) -> None:
        with patch.object(dataset, "load_all", side_effect=Timeout("test.lock")):
            response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 503)
        self.assertIn("busy", response.json()["detail"])

    def test_desktop_helpers_still_update_count_and_delete(self) -> None:
        entry = {field: "" for field in dataset.FIELDNAMES}
        entry.update(id="desktop", text="Desktop text", entry_type="Word", category="Campus Life")
        dataset.append_entry(entry)
        self.assertTrue(dataset.text_exists(" DESKTOP TEXT "))
        self.assertFalse(dataset.text_exists("Desktop text", exclude_id="desktop"))
        dataset.update_entry("desktop", {"text": "Updated desktop text"})
        self.assertEqual(dataset.load_all()[0]["text"], "Updated desktop text")
        self.assertEqual(dataset.count_by("category"), {"Campus Life": 1})
        dataset.delete_entry("desktop")
        self.assertEqual(dataset.total_count(), 0)

    def test_legacy_lexer_pipeline_writes_reports_in_temporary_directory(self) -> None:
        from compiler import run_lexer

        output = self.directory / "reports"
        with (
            patch.object(run_lexer.dataset, "DATASET_PATH", dataset.DATASET_PATH),
            patch.object(run_lexer.dataset, "AUDIO_DIR", dataset.AUDIO_DIR),
            patch.object(run_lexer, "OUTPUT_DIR", str(output)),
            redirect_stdout(io.StringIO()) as console,
        ):
            run_lexer.main()
        self.assertIn("placeholder", console.getvalue())
        self.assertTrue((output / "frequency_report.csv").is_file())
        with (output / "token_table.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 50)
        self.assertEqual(rows[0]["token"], "Le")


if __name__ == "__main__":
    unittest.main()
