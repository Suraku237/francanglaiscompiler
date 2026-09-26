import hashlib
import sqlite3
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from filelock import Timeout

from backend import analyzer_history, coursework_store
from backend.analyzer_models import AnalyzerTestRequest
from backend.auth import AuthSettings, AuthStore
from backend.collection import CollectionError
from backend.config import ServerSettings
from backend.main import create_app
from backend.public_access import COOKIE, PUBLIC_OWNER_ID, PublicWorkspaceStore
from backend.readings_api import _save
from backend.readings_models import ReadingUpload
from backend.shared_workspace import SharedWorkspaceStore
from backend.tests.import_fixtures import wav_bytes
from backend.tests.support import block_outbound_http
from backend.workspaces import WorkspaceStore, use_workspace
from compiler.lexer import tokenizer
from compiler.parser.yaounde import GRAMMAR
from compiler.tests.yaounde_cases import CORPUS_CASES
from data_collector.tests.support import synthetic_entry

READ_ONLY = {"owner_id": None, "owner_name": "", "can_edit": False}


class PublicAccessTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="camfranglais-public-test-")))
        self.stack.enter_context(patch.dict(AuthSettings.model_config, env_file=None))
        self.stack.enter_context(patch.dict(ServerSettings.model_config, env_file=None))
        self.outbound = block_outbound_http(self.stack)
        self.stack.callback(self.assert_no_network)
        self.owner_id = str(uuid4())
        accounts = AuthStore(AuthSettings(
            environment="development", data_dir=self.root, public_url="http://testserver",
            mail_mode="file", google_client_id="", google_client_secret="",
        ))
        with accounts.connection() as db:
            db.execute(
                "INSERT INTO users(id,email,display_name,verified,created) VALUES (?,?,?,?,?)",
                (self.owner_id, "private@example.invalid", "Private curator", 1, time.time()),
            )
        self.store = SharedWorkspaceStore(self.root, self.owner_id, "Private curator")
        self.audio = wav_bytes()
        self.filename = f"{uuid4().hex}.wav"
        (self.store.audio_dir / self.filename).write_bytes(self.audio)
        self.entry_id = str(uuid4())
        self.store.save_all([synthetic_entry(
            id=self.entry_id, text="taxi", entry_type="Word", lexical_category="NOUN",
            review_status="approved", audio_filename=self.filename,
        )])
        with use_workspace(self.store):
            coursework_store.save_project(coursework_store.default_project().model_copy(update={
                "grammar": "S -> NOUN", "discussion": "Private archived profile detail.",
            }))
            self.historical = analyzer_history.record_test(AnalyzerTestRequest(
                request_id=str(uuid4()), text="taxi", grammar="S -> NOUN",
            ))
            self.reading = _save(
                ReadingUpload(text="Bonjour le monde", language="fr", share_consent=True),
                None, "fixture.wav", self.audio,
            )
        legacy = WorkspaceStore(self.root, self.owner_id)
        legacy.save_all([synthetic_entry(id=str(uuid4()), text="Private archived source")])
        self.private_paths = [accounts.path, legacy.path, *self.store.audio_dir.iterdir()]
        self.private_hashes = self.fingerprints()
        self.before = self.store.export_document()
        self.settings = ServerSettings(
            environment="development", data_dir=self.root, public_url="http://testserver",
        )
        self.app = create_app(server_settings=self.settings)
        self.client = self.stack.enter_context(TestClient(self.app, headers={"Origin": "http://testserver"}))
        self.bootstrap(self.client)

    def assert_no_network(self):
        for transport in self.outbound:
            transport.assert_not_called()

    def fingerprints(self):
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in self.private_paths}

    def bootstrap(self, client):
        response = client.get("/api/public/session")
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        return response

    def payload(self, **changes):
        return {"request_id": str(uuid4()), "text": "taxi", "grammar": "S -> NOUN", **changes}

    def record(self, payload, client=None):
        response = (client or self.client).post("/api/analyzer/tests", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_archives_preserved(self, new_tests=0):
        after = self.store.export_document()
        for key in self.before:
            if key not in ("analyzer_tests", "test_requests", "ownership", "version"):
                self.assertEqual(after[key], self.before[key], key)
        for key in ("analyzer_tests", "test_requests", "ownership"):
            self.assertEqual(len(after[key]), len(self.before[key]) + new_tests)
            for original in self.before[key]:
                self.assertIn(original, after[key], key)
        self.assertEqual(after["version"], self.before["version"] + new_tests)
        self.assertEqual(self.fingerprints(), self.private_hashes)
        with self.store.connection() as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_bootstrap_is_anonymous_and_public_views_redact_only_presented_ownership(self):
        response = self.bootstrap(self.client)
        self.assertEqual(response.json()["access_mode"], "public_read_only")
        self.assertEqual(response.json()["capabilities"], {
            "analyze": True, "save_tests": True, "edit_collection": False,
            "edit_grammar": False, "edit_recordings": False,
        })
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=lax", response.headers["set-cookie"])
        token = response.json()["csrf_token"]
        self.assertNotEqual(token, self.client.cookies[COOKIE])
        self.assertEqual(self.bootstrap(self.client).json()["csrf_token"], token)
        self.assertFalse(hasattr(self.app.state, "auth_store"))
        paths = ("/api/metadata", "/api/dictionary", "/api/examples", "/api/dataset", "/api/analyzer",
                 "/api/analyzer/tests", f"/api/analyzer/tests/{self.historical.id}")
        for path in paths:
            result = self.client.get(path)
            self.assertEqual(result.status_code, 200, result.text)
            for private in (self.owner_id, "Private curator", "Private archived profile detail.", "private@example.invalid"):
                self.assertNotIn(private, result.text)
        entry = self.client.get("/api/dataset").json()["entries"][0]
        self.assertEqual(entry["ownership"], READ_ONLY)
        self.assertEqual(self.client.get("/api/analyzer").json()["grammar_ownership"], READ_ONLY)
        self.assertEqual(self.client.get("/api/analyzer/tests").json()["tests"][0]["ownership"], READ_ONLY)
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{self.historical.id}").json()["ownership"], READ_ONLY)
        self.assert_archives_preserved()

    def test_account_maintenance_import_and_private_file_surfaces_are_absent(self):
        paths = (
            "/api/auth/session", "/api/auth/register", "/api/auth/login", "/api/auth/google/start",
            "/api/auth/profile", "/api/workspace/projects", "/api/workspace/history",
            "/api/workspace/revisions", "/api/workspace/backups", "/api/workspace/backups/preview",
            "/api/workspace/backups/restore", "/api/coursework", "/api/coursework/project",
            "/api/coursework/screenshots", "/api/import/text", "/api/import/preview",
        )
        for path in paths:
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                with self.subTest(path=path, method=method):
                    response = self.client.request(method, path, json={})
                    self.assertEqual(response.status_code, 404, response.text)
        for path in ("/.env", "/backend/.env", "/.mboa/auth.sqlite3", "/auth.sqlite3",
                     "/shared-workspace/workspace.sqlite3", "/backend/main.py"):
            self.assertEqual(self.client.get(path).status_code, 404, path)
        self.assert_archives_preserved()

    def test_collection_grammar_and_recording_mutations_fail_even_with_valid_csrf(self):
        paths = (
            "/api/dataset", f"/api/dataset/{self.entry_id}", "/api/dataset/audio",
            f"/api/dataset/{self.entry_id}/audio", "/api/analyzer/grammar",
            "/api/readings", f"/api/readings/{self.reading.id}", f"/api/readings/{self.reading.id}/audio",
        )
        for path in paths:
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                response = self.client.request(method, path, json={"text": "Forbidden change", "grammar": "S -> VERB"})
                self.assertEqual(response.status_code, 403, (method, path, response.text))
                self.assertIn("read-only", response.json()["detail"])
        self.assert_archives_preserved()

    def test_public_storage_cannot_modify_profile_collection_recordings_or_restore(self):
        public = PublicWorkspaceStore(self.root)
        operations = (
            lambda: public.save_coursework(coursework_store.default_project()),
            lambda: public.save_all([]),
            lambda: public.require_owner("reading", self.reading.id),
            lambda: public.require_owner("analyzer_test", self.historical.id),
            lambda: public.import_document(self.before, public.version),
            lambda: public.save_backup_settings({}),
        )
        for operation in operations:
            with self.assertRaises(CollectionError) as captured:
                operation()
            self.assertEqual(captured.exception.status_code, 403)
        self.assert_archives_preserved()

    def test_configured_operator_backups_keep_running_without_public_administration_routes(self):
        seen = []

        async def maintenance(data_dir, stop):
            seen.append(data_dir)
            await stop.wait()

        with patch("backend.main.maintain_backups", side_effect=maintenance) as worker:
            with TestClient(create_app(server_settings=self.settings)) as client:
                self.assertEqual(client.get("/api/health").status_code, 200)
                self.assertEqual(client.get("/api/workspace/backups").status_code, 404)
            self.assertEqual(seen, [self.root])
            worker.assert_awaited_once()
        self.assert_archives_preserved()

    def test_saved_tests_keep_raw_input_snapshots_idempotence_and_restart_persistence(self):
        payload = self.payload(text="  taxi  ")
        saved = self.record(payload)
        self.assertEqual(saved["text"], payload["text"])
        self.assertTrue(saved["parse"]["accepted"])
        self.assertEqual(saved["lexical"]["tokens"], [{"text": "taxi", "category": "NOUN"}])
        self.assertEqual(saved["ownership"], READ_ONLY)
        self.assertEqual(self.record(payload), saved)
        with TestClient(create_app(server_settings=self.settings), headers={"Origin": "http://testserver"}) as reopened:
            self.bootstrap(reopened)
            self.assertEqual(reopened.get(f"/api/analyzer/tests/{saved['id']}").json(), saved)
            self.assertEqual(self.record(payload, reopened), saved)
            self.assertEqual(reopened.get("/api/analyzer/tests").json()["summary"]["total"], 2)
        conflict = self.client.post("/api/analyzer/tests", json={**payload, "text": "different"})
        self.assertEqual(conflict.status_code, 409)
        with self.store.connection() as db:
            self.assertEqual(db.execute(
                "SELECT owner_id FROM ownership WHERE kind='analyzer_test' AND record_id=?", (saved["id"],),
            ).fetchone()[0], PUBLIC_OWNER_ID)
        self.assert_archives_preserved(new_tests=1)

    def test_concurrent_retry_computes_and_commits_only_once(self):
        payload = self.payload()
        with patch.object(tokenizer, "analyze_sentence", wraps=tokenizer.analyze_sentence) as analyze, \
                ThreadPoolExecutor(max_workers=4) as workers:
            responses = list(workers.map(
                lambda _: self.client.post("/api/analyzer/tests", json=payload), range(4),
            ))
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), responses[0].json())
        analyze.assert_called_once()
        self.assert_archives_preserved(new_tests=1)

    def test_missing_tokens_wrong_origins_and_cross_visitor_tokens_are_rejected(self):
        for path, payload in (
            ("/api/analyze", {"text": "taxi"}),
            ("/api/analyzer/analyze", {"text": "taxi", "grammar": "S -> NOUN"}),
            ("/api/analyzer/tests", self.payload()),
            ("/api/readings/lookup", {"text": "Bonjour le monde", "language": "fr"}),
        ):
            for headers in (
                {"X-CSRF-Token": ""},
                {"X-CSRF-Token": "wrong"},
                {"Origin": "https://untrusted.example"},
                {"Origin": ""},
            ):
                result = self.client.post(path, json=payload, headers=headers)
                self.assertEqual(result.status_code, 403, result.text)
        with TestClient(self.app, headers={"Origin": "http://testserver"}) as visitor:
            self.bootstrap(visitor)
            result = visitor.post("/api/analyzer/tests", json=self.payload(),
                                  headers={"X-CSRF-Token": self.client.headers["X-CSRF-Token"]})
            self.assertEqual(result.status_code, 403, result.text)
        self.assert_archives_preserved()

    def test_saved_grammar_is_required_for_new_work_but_retries_retrieve_prior_snapshots(self):
        for path, payload in (
            ("/api/analyzer/analyze", {"text": "taxi", "grammar": "S -> VERB"}),
            ("/api/analyzer/tests", self.payload(grammar="S -> VERB")),
        ):
            result = self.client.post(path, json=payload)
            self.assertEqual(result.status_code, 409, result.text)
            self.assertIn("Reload", result.json()["detail"])
        self.assert_archives_preserved()
        payload = self.payload()
        saved = self.record(payload)
        with use_workspace(self.store):
            coursework_store.save_project(coursework_store.load_project().model_copy(update={"grammar": "S -> VERB"}))
        version = self.store.version
        self.assertEqual(self.record(payload), saved)
        self.assertEqual(self.store.version, version)
        self.assertEqual(self.client.post("/api/analyzer/tests", json=self.payload()).status_code, 409)

    def test_collection_audio_and_recorded_readings_remain_available_without_accounts(self):
        self.assertEqual(self.client.get(f"/api/dataset/{self.entry_id}/audio").content, self.audio)
        result = self.client.post("/api/readings/lookup", json={"text": "Bonjour le monde", "language": "fr"})
        self.assertEqual(result.status_code, 200, result.text)
        reading = result.json()["reading"]
        self.assertEqual(reading["ownership"], READ_ONLY)
        self.assertEqual(self.client.get(reading["audio_url"]).content, self.audio)
        missing = self.client.post("/api/readings/lookup", json={"text": "Not recorded", "language": "en"})
        self.assertEqual(missing.json(), {"reading": None})
        self.assertEqual(self.client.get(f"/api/readings/{uuid4()}/audio").status_code, 404)
        self.assert_archives_preserved()

    def test_existing_request_limit_is_exact_persistent_and_expiring(self):
        path = self.app.state.public_access.path
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE limits SET count=119,expires=?", (time.time() + 60,))
        self.assertEqual(self.client.get("/api/metadata").status_code, 200)
        response = self.client.get("/api/metadata")
        self.assertEqual(response.status_code, 429)
        self.assertTrue(1 <= int(response.headers["Retry-After"]) <= 60)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        with TestClient(create_app(server_settings=self.settings)) as reopened:
            self.assertEqual(reopened.get("/api/metadata").status_code, 429)
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("UPDATE limits SET expires=0")
        self.assertEqual(self.client.get("/api/metadata").status_code, 200)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute("SELECT count FROM limits").fetchone()[0], 1)
        self.assert_archives_preserved()

    def test_storage_errors_and_body_limits_are_explicit_without_private_details(self):
        for error in (sqlite3.OperationalError("PRIVATE DATABASE PATH"), OSError("PRIVATE DIRECTORY")):
            with patch.object(self.app.state.public_access, "limit", side_effect=error), \
                    self.assertLogs("backend.public_access", level="ERROR") as messages:
                result = self.client.get("/api/public/session")
            self.assertEqual(result.status_code, 503)
            self.assertNotIn("PRIVATE", result.text + "".join(messages.output))
        with patch.object(self.app.state.public_access, "limit", side_effect=Timeout("PRIVATE LOCK")):
            result = self.client.get("/api/analyzer")
        self.assertEqual(result.status_code, 503)
        self.assertNotIn("PRIVATE", result.text)
        self.assertEqual(self.client.post("/api/analyze", json={"text": "x" * 4001}).status_code, 422)
        self.assertEqual(self.client.post(
            "/api/analyze", content=b"x" * (1024 * 1024 + 1), headers={"Content-Type": "application/json"},
        ).status_code, 413)
        self.assert_archives_preserved()

    def test_production_uses_secure_anonymous_cookie_and_retains_https_headers(self):
        settings = ServerSettings(
            environment="production", data_dir=self.root,
            public_url="https://camfranglais.duckdns.org",
        )
        with TestClient(create_app(server_settings=settings), base_url=settings.public_url,
                        headers={"Origin": settings.public_url}) as client:
            result = self.bootstrap(client)
            self.assertIn("Secure", result.headers["set-cookie"])
            self.assertIn("no-store", result.headers["cache-control"])
            self.assertIn("max-age=", result.headers["strict-transport-security"])
            self.assertEqual(client.get("/api/dataset").status_code, 200)
            self.assertEqual(client.get("/docs").status_code, 404)
            redirect = client.get("http://camfranglais.duckdns.org/api/health", follow_redirects=False)
            self.assertEqual(redirect.status_code, 307)
            self.assertEqual(client.get("/api/health", headers={"Host": "untrusted.example"}).status_code, 400)
        self.assert_archives_preserved()

    def test_all_twelve_corpus_sentences_keep_their_exact_public_results(self):
        with use_workspace(self.store):
            coursework_store.save_project(coursework_store.load_project().model_copy(update={"grammar": GRAMMAR}))
        grammar = self.client.get("/api/analyzer").json()["grammar"]
        results = [self.record(self.payload(text=case.text, grammar=grammar)) for case in CORPUS_CASES]
        self.assertEqual(sum(result["parse"]["accepted"] for result in results), 10)
        self.assertEqual(sum(result["approval"]["accepted"] for result in results), 10)
        for case, result in zip(CORPUS_CASES, results):
            self.assertEqual(result["text"], case.text)
            self.assertEqual(result["parse"]["accepted"], case.accepted)
            self.assertEqual(result["grammar_source"], grammar)
            self.assertEqual(result["ownership"], READ_ONLY)
        self.assertEqual(self.fingerprints(), self.private_hashes)
        after = self.store.export_document()
        self.assertEqual(after["entries"], self.before["entries"])
        self.assertEqual(after["revisions"], self.before["revisions"])
        self.assertEqual(after["readings"], self.before["readings"])


if __name__ == "__main__":
    unittest.main()
