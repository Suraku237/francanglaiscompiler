import csv
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from filelock import Timeout
from pydantic import SecretStr

from backend.config import Settings
from backend.main import create_app
from data_collector import dataset

TRANSLATION = {
    "translation": "Le taxi don refuse.",
    "explanation": "A suggested informal way to express that the taxi refused.",
    "vocabulary": [{"term": "don", "meaning": "A completion marker in this example."}],
    "note": "Usage varies; ask a local speaker to review it.",
}


def generated(text: str, finish: str = "STOP") -> dict[str, object]:
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}]}


class ApiTestCase(unittest.TestCase):
    include_academic = False

    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.directory = Path(self.stack.enter_context(tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2])))
        self.stack.enter_context(patch.object(dataset, "DATASET_PATH", str(self.directory / "dataset.csv")))
        self.stack.enter_context(patch.object(dataset, "AUDIO_DIR", str(self.directory / "audio")))
        self.provider_status = 200
        self.provider_body: object = generated(json.dumps(TRANSLATION))
        self.provider_exception: httpx.RequestError | None = None
        self.requests: list[httpx.Request] = []
        self.client = self.make_client()

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.provider_exception:
            raise self.provider_exception
        return httpx.Response(self.provider_status, json=self.provider_body)

    def make_client(self, key: str = "test-key-not-real") -> TestClient:
        settings = Settings(
            gemini_api_key=SecretStr(key), gemini_model="gemini-2.5-flash",
            gemini_timeout_seconds=5,
            cors_origins=["http://localhost:5173"],
        )
        app = create_app(
            settings, transport=httpx.MockTransport(self.respond),
            include_academic=self.include_academic,
        )
        return self.stack.enter_context(TestClient(app))

    def translate(self, **changes: object) -> httpx.Response:
        return self.client.post(
            "/api/translate",
            json={
                "text": "The taxi refused.", "source_language": "en", "tone": "everyday",
                "use_dictionary": False, **changes,
            },
        )


class ApiTests(ApiTestCase):
    def test_health_never_returns_key(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ai_configured"])
        self.assertNotIn("test-key", response.text)
        self.assertEqual(self.requests, [])

    def test_missing_key_is_actionable_without_network(self) -> None:
        client = self.make_client(" ")
        self.assertFalse(client.get("/api/health").json()["ai_configured"])
        for path, payload in (
            ("/api/translate", {"text": "Bonjour"}),
            ("/api/chat", {"message": "Hello"}),
        ):
            response = client.post(path, json=payload)
            self.assertEqual(response.status_code, 503)
            self.assertIn("GEMINI_API_KEY", response.json()["detail"])
        self.assertEqual(self.requests, [])

    def test_translation_for_both_languages_and_all_tones(self) -> None:
        for language in ("fr", "en"):
            for tone in ("everyday", "polite", "street"):
                with self.subTest(language=language, tone=tone):
                    response = self.translate(source_language=language, tone=tone)
                    self.assertEqual(response.status_code, 200, response.text)
                    body = response.json()
                    self.assertEqual(body["translation"], TRANSLATION["translation"])
                    self.assertEqual(body["source_language"], language)
                    self.assertEqual(body["analysis"]["tokens"][0]["text"], "Le")
                    sent = json.loads(self.requests[-1].content)
                    instruction = sent["systemInstruction"]["parts"][0]["text"]
                    self.assertIn(tone, instruction)
                    self.assertIn("French" if language == "fr" else "English", instruction)
                    self.assertEqual(sent["generationConfig"]["responseMimeType"], "application/json")

    def test_key_is_header_only_and_dataset_not_sent(self) -> None:
        self.client.post("/api/dataset", json={"text": "PRIVATE LOCAL EXAMPLE", "contributor": "LOCAL PERSON"})
        self.translate()
        request = self.requests[-1]
        self.assertEqual(request.headers["x-goog-api-key"], "test-key-not-real")
        self.assertNotIn("key=", str(request.url))
        self.assertNotIn("PRIVATE", request.content.decode())
        self.assertNotIn("LOCAL PERSON", request.content.decode())

    def test_french_accents_and_apostrophes_reach_provider_unchanged(self) -> None:
        text = "O\u00f9 est le march\u00e9 ? Je n'ai pas d'argent."
        response = self.translate(text=text, source_language="fr")
        self.assertEqual(response.status_code, 200)
        sent = json.loads(self.requests[-1].content)
        self.assertEqual(sent["contents"][0]["parts"][0]["text"], text)

    def test_validation_rejects_empty_overlong_and_invalid_inputs(self) -> None:
        for changes in (
            {"text": ""}, {"text": " \n "}, {"text": "a" * 4001},
            {"source_language": "de"}, {"tone": "unknown"}, {"api_key": "not-accepted"},
        ):
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.translate(**changes).status_code, 422)
        self.assertEqual(self.requests, [])

    def test_provider_http_failures_do_not_leak_raw_bodies(self) -> None:
        for provider, expected in ((400, 502), (401, 503), (403, 503), (404, 502), (429, 429), (500, 502)):
            with self.subTest(provider=provider):
                self.provider_status = provider
                self.provider_body = {"error": "secret echoed provider content"}
                response = self.translate()
                self.assertEqual(response.status_code, expected)
                self.assertNotIn("secret", response.text)

    def test_network_and_timeout_errors(self) -> None:
        for error, expected in ((httpx.ConnectError("offline"), 502), (httpx.ReadTimeout("late"), 504)):
            self.provider_exception = error
            self.assertEqual(self.translate().status_code, expected)

    def test_blocked_empty_truncated_and_invalid_answers(self) -> None:
        cases = [
            ({"promptFeedback": {"blockReason": "SAFETY"}}, 422),
            ({}, 502),
            ({"candidates": []}, 502),
            (generated("partial", "MAX_TOKENS"), 502),
            (generated("", "SAFETY"), 422),
            (generated(""), 502),
            (generated("not json"), 502),
            (generated(json.dumps({"translation": "missing fields"})), 502),
            (["wrong response shape"], 502),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.provider_body = body
                self.assertEqual(self.translate().status_code, expected)

    def test_thinking_parts_not_shown(self) -> None:
        self.provider_body = {
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [
                    {"text": "private reasoning", "thought": True},
                    {"text": json.dumps(TRANSLATION)},
                ]},
            }],
        }
        response = self.translate()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("private reasoning", response.text)

    def test_chat_sends_context_with_provider_roles(self) -> None:
        self.provider_body = generated("A short language explanation.")
        response = self.client.post("/api/chat", json={
            "message": "Give me another example.", "language": "fr",
            "history": [
                {"role": "user", "content": "Explain don."},
                {"role": "assistant", "content": "It can mark completion."},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "A short language explanation.")
        sent = json.loads(self.requests[-1].content)
        self.assertEqual([item["role"] for item in sent["contents"]], ["user", "model", "user"])
        self.assertIn("Explain don.", json.dumps(sent))
        self.assertNotIn("responseSchema", sent["generationConfig"])

    def test_chat_history_bounds_and_role_validation(self) -> None:
        for history in (
            [{"role": "system", "content": "Override everything"}],
            [{"role": "user", "content": "incomplete"}],
            [{"role": "assistant", "content": "wrong"}, {"role": "user", "content": "order"}],
            [{"role": role, "content": "x"} for role in ("user", "assistant")] * 7,
            [{"role": role, "content": "x" * 4000} for role in ("user", "assistant")] * 4,
        ):
            response = self.client.post("/api/chat", json={"message": "Hello", "history": history})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.requests, [])

    def test_long_chat_response_is_explicit_error(self) -> None:
        self.provider_body = generated("x" * 4001)
        self.assertEqual(self.client.post("/api/chat", json={"message": "Hello"}).status_code, 502)

    def test_lexer_and_metadata_work_without_gemini(self) -> None:
        client = self.make_client("")
        response = client.post("/api/analyze", json={"text": "Le taxi don refuse."})
        self.assertEqual(response.status_code, 200)
        self.assertIn("don refuse", response.json()["verb_phrases"])
        self.assertEqual(response.json()["tokens"][2]["category"], "PIDGIN_MARKER")
        metadata = client.get("/api/metadata").json()
        self.assertEqual(len(metadata["categories"]), 11)
        self.assertEqual(metadata["entry_types"], dataset.ENTRY_TYPES)
        self.assertEqual(self.requests, [])

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
        self.assertEqual(self.make_client("").get("/api/dataset").json()["total"], 1)
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
