import base64
import asyncio
import hashlib
import io
import json
import re
import tempfile
import threading
import time
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm
from pydantic import SecretStr, ValidationError
from starlette.concurrency import run_in_threadpool

from backend.auth import AuthSettings, AuthStore, COOKIE, OAUTH_COOKIE, AuthError, digest
from backend.config import Settings
from backend.main import create_app
from backend.tests.import_fixtures import wav_bytes
from backend.tests.support import block_outbound_http
from backend.workspace_backups import BackupRestore, maintenance_cycle, maintain_backups, preview_backup, restore_backup, snapshot, validate_archive
from backend.workspaces import WorkspaceStore, HistoryInput
from backend.collection import CollectionError
from data_collector import dataset
from data_collector.tests.support import synthetic_entry

PASSWORD = "Workspace-test-password-2026!"
HISTORY = {
    "kind": "translation", "title": "Customer greeting",
    "content": {"source_text": "tchop", "source_language": "francanglais", "target_language": "en",
                "translation": "to eat", "explanation": "Dictionary reference", "note": "Review context."},
}


class HostedCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(
            prefix=".hosted-test-", dir=Path(__file__).parent,
        )))
        self.mail = []
        self.outbound_http = block_outbound_http(self.stack)
        self.settings = AuthSettings(
            data_dir=self.root, public_url="http://testserver", mail_mode="file",
            google_client_id="", google_client_secret=SecretStr(""),
        )
        self.app = create_app(
            Settings(), auth_settings=self.settings,
            mailer=lambda address, subject, text: self.mail.append((address, text)),
        )
        self.client = self.stack.enter_context(TestClient(self.app, headers={"Origin": "http://testserver"}))
        self.store = self.app.state.auth_store

    def assert_no_outbound_http(self):
        for transport in self.outbound_http:
            transport.assert_not_called()

    def token(self, email):
        text = next(text for address, text in reversed(self.mail) if address == email)
        match = re.search(r"token=([A-Za-z0-9_-]+)", text)
        if match is None:
            self.fail("The synthetic account email must contain a verification or recovery token.")
        return match.group(1)

    def register(self, client=None, email="first@example.com"):
        client = client or self.client
        response = client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Test user"})
        self.assertEqual(response.status_code, 202, response.text)
        token = self.token(email)
        self.assertNotIn(token, response.text)
        verified = client.post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200, verified.text)
        return self.login(client, email)

    def login(self, client, email="first@example.com", password=PASSWORD):
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        client.headers["X-CSRF-Token"] = data["csrf_token"]
        return data["user"]

    def other(self):
        client = TestClient(self.app, headers={"Origin": "http://testserver"})
        self.addCleanup(client.close)
        return client

    def entry(self, client=None, text="Business phrase", **values):
        client = client or self.client
        response = client.post("/api/dataset", json={"text": text, "language": "francanglais", **values})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def legacy_directory(self):
        directory = self.root / "legacy"
        self.stack.enter_context(patch.object(dataset, "DATASET_PATH", str(directory / "dataset.csv")))
        self.stack.enter_context(patch.object(dataset, "AUDIO_DIR", str(directory / "audio")))
        self.stack.enter_context(patch.object(dataset, "_LOCKS", {}))
        return directory


class AccountTests(HostedCase):
    def test_all_private_surfaces_require_an_account(self):
        for path in ("/api/dataset", "/api/dictionary", "/api/metadata", "/api/workspace/history",
                     "/api/workspace/projects", "/api/workspace/backups", "/api/dataset/unknown/audio"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_verified_registration_and_cookie_protection(self):
        email = "person@example.com"
        registered = self.client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Person"})
        self.assertEqual(registered.status_code, 202)
        self.assertEqual(self.client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code, 403)
        token = self.token(email)
        self.assertEqual(self.client.post("/api/auth/verify-email", json={"token": token}).status_code, 200)
        self.assertEqual(self.client.post("/api/auth/verify-email", json={"token": token}).status_code, 400)
        response = self.client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
        self.assertEqual(response.status_code, 200)
        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=lax", cookie)
        raw = self.client.cookies[COOKIE]
        with self.store.connection() as db:
            stored = db.execute("SELECT token FROM sessions").fetchone()[0]
            password_hash = db.execute("SELECT password_hash FROM users").fetchone()[0]
        self.assertNotEqual(raw, stored)
        self.assertTrue(password_hash.startswith("$argon2id$"))
        self.assertNotIn(PASSWORD, password_hash)

    def test_csrf_and_origin_are_enforced(self):
        self.register()
        body = {"text": "A private phrase"}
        self.assertEqual(self.client.post("/api/dataset", json=body).status_code, 201)
        self.assertEqual(self.client.post("/api/dataset", json=body, headers={"X-CSRF-Token": ""}).status_code, 403)
        self.assertEqual(self.client.post("/api/dataset", json=body, headers={"Origin": "https://attacker.example"}).status_code, 403)
        other = self.other()
        self.assertEqual(other.post("/api/auth/login", json={"email": "first@example.com", "password": PASSWORD},
                                   headers={"Origin": "https://attacker.example"}).status_code, 403)

    def test_password_reset_revokes_sessions_and_is_single_use(self):
        self.register()
        other = self.other()
        self.login(other)
        response = other.post("/api/auth/forgot-password", json={"email": "first@example.com"})
        self.assertEqual(response.status_code, 200)
        token = self.token("first@example.com")
        reset = other.post("/api/auth/reset-password", json={"token": token, "password": PASSWORD + "new"})
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(self.client.get("/api/dataset").status_code, 401)
        self.assertEqual(other.get("/api/dataset").status_code, 401)
        self.assertEqual(other.post("/api/auth/reset-password", json={"token": token, "password": PASSWORD}).status_code, 400)
        self.login(other, password=PASSWORD + "new")

    def test_logout_invalidates_the_server_session(self):
        self.register()
        raw = self.client.cookies[COOKIE]
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 204)
        self.client.cookies.set(COOKIE, raw)
        self.assertEqual(self.client.get("/api/dataset").status_code, 401)

    def test_expired_tokens_and_sessions_fail_closed(self):
        self.register()
        with self.store.connection() as db:
            db.execute("UPDATE sessions SET expires=0")
        self.assertEqual(self.client.get("/api/dataset").status_code, 401)
        self.client.post("/api/auth/forgot-password", json={"email": "first@example.com"})
        token = self.token("first@example.com")
        with self.store.connection() as db:
            db.execute("UPDATE tokens SET expires=0")
        self.assertEqual(self.client.post("/api/auth/reset-password", json={"token": token, "password": PASSWORD}).status_code, 400)

    def test_forgot_and_duplicate_registration_do_not_disclose_accounts(self):
        self.register()
        known = self.client.post("/api/auth/forgot-password", json={"email": "first@example.com"})
        absent = self.client.post("/api/auth/forgot-password", json={"email": "absent@example.com"})
        self.assertEqual(known.json(), absent.json())
        duplicate = self.client.post("/api/auth/register", json={"email": "first@example.com", "password": PASSWORD, "display_name": "Replacement"})
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(self.client.get("/api/auth/session").json()["user"]["display_name"], "Test user")

    def test_persistent_atomic_rate_limits_have_retry_after(self):
        self.store.throttle("test", 1, 60)
        with self.assertRaises(AuthError) as error:
            self.store.throttle("test", 1, 60)
        self.assertEqual(error.exception.status, 429)
        retry_after = error.exception.retry_after
        if retry_after is None:
            self.fail("Rate-limited requests must include a retry interval.")
        self.assertGreater(retry_after, 0)
        reopened = AuthStore(self.settings)
        with self.assertRaises(AuthError) as persisted:
            reopened.throttle("test", 1, 60)
        self.assertEqual(persisted.exception.status, 429)

        def attempt(_index):
            try:
                reopened.throttle("concurrent-test", 4, 60)
                return 200
            except AuthError as failure:
                return failure.status

        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(attempt, range(12)))
        self.assertEqual(results.count(200), 4)
        self.assertEqual(results.count(429), 8)

    def test_production_configuration_cannot_use_file_mail_or_plain_http(self):
        with patch.dict(AuthSettings.model_config, {"env_file": None}):
            with self.subTest(case="plain HTTP"), self.assertRaises(ValidationError):
                AuthSettings(environment="production", public_url="http://app.example",
                             mail_mode="smtp", smtp_host="smtp.example", mail_from="app@example.com")
            with self.subTest(case="file mail"), self.assertRaises(ValidationError):
                AuthSettings(environment="production", public_url="https://app.example", mail_mode="file")
            with self.subTest(case="unpaired Google credentials"), self.assertRaises(ValidationError):
                AuthSettings(google_client_id="configured", google_client_secret=SecretStr(""))


class PrivateWorkspaceTests(HostedCase):
    def test_distinct_accounts_never_read_or_mutate_each_others_data(self):
        first = self.register()
        entry = self.entry()
        saved = self.client.post("/api/workspace/history", json=HISTORY).json()
        other = self.other()
        second = self.register(other, "second@example.com")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(other.get("/api/dataset").json()["total"], 0)
        self.assertEqual(other.get("/api/workspace/history").json()["entries"], [])
        for response in (
            other.patch(f"/api/dataset/{entry['id']}", json={"text": "Stolen"}),
            other.delete(f"/api/dataset/{entry['id']}"),
            other.get(f"/api/workspace/history/{saved['id']}"),
        ):
            self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)

    def test_parallel_user_contexts_are_isolated(self):
        self.register()
        other = self.other()
        self.register(other, "second@example.com")
        def save(pair):
            client, number = pair
            return client.post("/api/dataset", json={"text": f"Phrase {number}"}).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(save, [(self.client if number % 2 else other, number) for number in range(12)]))
        self.assertEqual(results, [201] * 12)
        first = self.client.get("/api/dataset").json()["entries"]
        second = other.get("/api/dataset").json()["entries"]
        self.assertEqual((len(first), len(second)), (6, 6))
        self.assertFalse({row["id"] for row in first} & {row["id"] for row in second})

    def test_workspace_initialization_does_not_block_the_asgi_event_loop(self):
        self.register()
        initializer_threads = []
        event_loop_threads = []

        async def observe_event_loop(function, *args, **kwargs):
            event_loop_threads.append(threading.get_ident())
            return await run_in_threadpool(function, *args, **kwargs)

        def initialize(*args, **kwargs):
            initializer_threads.append(threading.get_ident())
            return WorkspaceStore(*args, **kwargs)

        with patch("backend.workspaces.WorkspaceStore", side_effect=initialize), \
                patch("backend.auth.run_in_threadpool", side_effect=observe_event_loop):
            response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(initializer_threads), 1)
        self.assertTrue(event_loop_threads)
        self.assertNotIn(initializer_threads[0], event_loop_threads)

    def test_projects_are_per_request_and_private(self):
        self.register()
        initial = self.entry(text="General phrase")
        project = self.client.post("/api/workspace/projects", json={"name": "Client A"}).json()
        self.client.headers["X-Mboa-Project"] = project["id"]
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(self.client.get(f"/api/dataset/{initial['id']}/audio").status_code, 404)
        self.entry(text="Project phrase")
        other = self.other()
        self.register(other, "second@example.com")
        other.headers["X-Mboa-Project"] = project["id"]
        self.assertEqual(other.get("/api/dataset").status_code, 404)
        self.client.headers["X-Mboa-Project"] = "default"
        self.assertEqual(self.client.get("/api/dataset").json()["entries"][0]["text"], "General phrase")
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{project['id']}").status_code, 409)
        self.assertEqual(self.client.delete("/api/workspace/projects/default").status_code, 409)

    def test_account_management_remains_available_after_selected_project_is_deleted(self):
        self.register()
        project = self.client.post("/api/workspace/projects", json={"name": "Temporary project"}).json()
        self.client.headers["X-Mboa-Project"] = project["id"]
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{project['id']}").status_code, 204)
        projects = self.client.get("/api/workspace/projects")
        self.assertEqual(projects.status_code, 200, projects.text)
        self.assertEqual([item["id"] for item in projects.json()["projects"]], ["default"])
        self.assertEqual(self.client.get("/api/workspace/backups").status_code, 200)
        self.assertEqual(self.client.get("/api/dataset").status_code, 404)

    def test_saved_work_persists_and_is_explicit(self):
        user = self.register()
        self.assertEqual(self.client.get("/api/workspace/history").json()["entries"], [])
        saved = self.client.post("/api/workspace/history", json=HISTORY)
        self.assertEqual(saved.status_code, 201, saved.text)
        identifier = saved.json()["id"]
        self.assertEqual(self.client.get(f"/api/workspace/history/{identifier}").json()["content"], HISTORY["content"])
        self.assertEqual(self.client.patch(f"/api/workspace/history/{identifier}", json={"name": "Renamed"}).status_code, 200)
        self.assertEqual(WorkspaceStore(self.root, user["id"]).histories()[0]["title"], "Renamed")
        self.assertEqual(self.client.delete(f"/api/workspace/history/{identifier}").status_code, 204)
        self.assert_no_outbound_http()

    def test_revisions_restore_deleted_entries_as_unreviewed(self):
        self.register()
        entry = self.entry(review_status="approved")
        self.assertEqual(self.client.delete(f"/api/dataset/{entry['id']}").status_code, 204)
        state = self.client.get("/api/workspace/revisions").json()
        deleted = next(row for row in state["revisions"] if row["action"] == "delete")
        restored = self.client.post(
            f"/api/workspace/revisions/{deleted['id']}/restore",
            json={"expected_version": state["workspace_version"]},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()["entry"]["review_status"], "unreviewed")
        self.assertEqual(self.client.post(f"/api/workspace/revisions/{deleted['id']}/restore",
                                         json={"expected_version": state["workspace_version"]}).status_code, 409)

    def test_legacy_files_are_not_imported_or_modified(self):
        self.legacy_directory().mkdir()
        dataset.append_entry(synthetic_entry(text="Legacy-only synthetic expression"))
        path = Path(dataset.DATASET_PATH)
        before = path.read_bytes()
        self.register()
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.entry()
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)
        self.assertEqual(path.read_bytes(), before)

    def test_missing_legacy_files_are_not_created(self):
        directory = self.legacy_directory()
        self.assertFalse(directory.exists())
        self.register()
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.entry()
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)
        self.assertFalse(directory.exists())

    def test_audio_upload_and_range_read_are_private(self):
        self.register()
        response = self.client.post("/api/dataset/audio", data={"fields": json.dumps({"text": "Voice note"})},
                                    files={"file": ("voice.wav", wav_bytes(), "audio/wav")})
        self.assertEqual(response.status_code, 201, response.text)
        identifier = response.json()["id"]
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.get(f"/api/dataset/{identifier}/audio").status_code, 404)
        audio = self.client.get(f"/api/dataset/{identifier}/audio", headers={"Range": "bytes=0-9"})
        self.assertEqual(audio.status_code, 206)
        self.assertEqual(audio.content, wav_bytes()[:10])


class WorkspaceBackupTests(HostedCase):
    def test_snapshot_preview_restore_roundtrip_and_safety_copy(self):
        self.register()
        self.entry()
        self.client.post("/api/workspace/history", json=HISTORY)
        saved = self.client.post("/api/workspace/backups")
        self.assertEqual(saved.status_code, 201, saved.text)
        identifier = saved.json()["id"]
        archive = self.client.get(f"/api/workspace/backups/{identifier}/download")
        self.assertEqual(archive.status_code, 200)
        self.entry(text="After backup")
        preview = self.client.post("/api/workspace/backups/preview", files={"file": ("backup.zip", archive.content)})
        self.assertEqual(preview.status_code, 200, preview.text)
        state = preview.json()
        payload = {"token": state["token"], "expected_version": state["workspace_version"], "confirmation": "REPLACE"}
        restored = self.client.post("/api/workspace/backups/restore", json=payload)
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()["pre_restore_backup_id"])
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)
        self.assertEqual(len(self.client.get("/api/workspace/history").json()["entries"]), 1)
        self.assertEqual(self.client.post("/api/workspace/backups/restore", json=payload).status_code, 400)

    def test_backup_ids_and_preview_tokens_are_owner_scoped(self):
        self.register()
        saved = self.client.post("/api/workspace/backups").json()
        archive = self.client.get(f"/api/workspace/backups/{saved['id']}/download").content
        preview = self.client.post("/api/workspace/backups/preview", files={"file": ("backup.zip", archive)}).json()
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.get(f"/api/workspace/backups/{saved['id']}/download").status_code, 404)
        self.assertEqual(other.post("/api/workspace/backups/restore", json={
            "token": preview["token"], "expected_version": 0, "confirmation": "REPLACE",
        }).status_code, 400)

    def test_corrupt_and_traversal_archives_do_not_change_live_data(self):
        self.register()
        self.entry()
        for name in ("../escape", "C:\\escape", "audio/../../escape", "workspace.sqlite3"):
            output = io.BytesIO()
            with zipfile.ZipFile(output, "w") as archive:
                archive.writestr(name, b"untrusted")
                archive.writestr("manifest.json", "{}")
            response = self.client.post("/api/workspace/backups/preview", files={"file": ("backup.zip", output.getvalue())})
            self.assertEqual(response.status_code, 422, response.text)
        response = self.client.post("/api/workspace/backups/preview", files={"file": ("backup.zip", b"not zip")})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)

    def test_changes_after_preview_prevent_restoration(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        backup = snapshot(store)
        data = (store.root / "backups" / f"{backup['id']}.zip").read_bytes()
        info = preview_backup(store, data)
        self.entry()
        with self.assertRaises(CollectionError) as error:
            restore_backup(store, BackupRestore(token=info["token"], expected_version=info["workspace_version"], confirmation="REPLACE"))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(store.load_all()), 1)

    def test_restore_transaction_failure_preserves_live_entries(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        self.entry()
        snapshot_data = snapshot(store)
        raw = (store.root / "backups" / f"{snapshot_data['id']}.zip").read_bytes()
        self.entry(text="Must remain")
        info = preview_backup(store, raw)
        before = store.load_all()
        with patch.object(store, "import_document", side_effect=OSError("injected storage fault")), self.assertRaises(OSError):
            restore_backup(store, BackupRestore(token=info["token"], expected_version=info["workspace_version"], confirmation="REPLACE"))
        self.assertEqual(store.load_all(), before)

    def test_automatic_backup_is_due_only_once_and_retains_manual_backups(self):
        self.register()
        manual = self.client.post("/api/workspace/backups").json()
        self.assertEqual(self.client.patch("/api/workspace/backups/settings", json={
            "automatic": True, "interval_hours": 24, "keep_last": 1,
        }).status_code, 200)
        self.assertEqual(maintenance_cycle(self.root), 1)
        self.assertEqual(maintenance_cycle(self.root), 0)
        catalog = self.client.get("/api/workspace/backups").json()
        self.assertIn(manual["id"], [item["id"] for item in catalog["backups"]])
        self.assertEqual(sum(item["kind"] == "automatic" for item in catalog["backups"]), 1)
        self.assertGreater(catalog["state"]["last_success"], 0)

    def test_tampered_manifest_and_duplicate_entries_are_rejected(self):
        user = self.register()
        self.entry()
        store = WorkspaceStore(self.root, user["id"])
        saved = snapshot(store)
        raw = (store.root / "backups" / f"{saved['id']}.zip").read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as original:
            files = {name: original.read(name) for name in original.namelist()}
        for kind in ("checksum", "case_collision", "missing_data"):
            with self.subTest(kind=kind):
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w") as archive:
                    for name, content in files.items():
                        if kind == "missing_data" and name == "workspace.json":
                            continue
                        if kind == "checksum" and name == "workspace.json":
                            content += b" "
                        archive.writestr(name, content)
                    if kind == "case_collision":
                        archive.writestr("WORKSPACE.JSON", files["workspace.json"])
                with self.assertRaises(CollectionError):
                    validate_archive(output.getvalue())
        self.assertEqual(len(store.load_all()), 1)

    def test_archive_size_boundary_is_inclusive(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        saved = snapshot(store)
        raw = (store.root / "backups" / f"{saved['id']}.zip").read_bytes()
        with patch("backend.workspace_backups.MAX_ARCHIVE", len(raw)):
            self.assertEqual(validate_archive(raw)[0]["format"], 2)
        with patch("backend.workspace_backups.MAX_ARCHIVE", len(raw) - 1), self.assertRaises(CollectionError) as error:
            validate_archive(raw)
        self.assertEqual(error.exception.status_code, 413)

    def test_missing_revision_media_stops_backup_before_publication(self):
        user = self.register()
        response = self.client.post("/api/dataset/audio", data={"fields": json.dumps({"text": "Recorded term"})},
                                    files={"file": ("voice.wav", wav_bytes(), "audio/wav")})
        self.assertEqual(response.status_code, 201, response.text)
        entry = response.json()
        self.assertEqual(self.client.delete(f"/api/dataset/{entry['id']}").status_code, 204)
        store = WorkspaceStore(self.root, user["id"])
        (store.audio_dir / entry["audio_filename"]).unlink()
        response = self.client.post("/api/workspace/backups")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.client.get("/api/workspace/backups").json()["backups"], [])


class BackupMaintenanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_storage_scan_failure_is_logged_and_the_next_cycle_still_runs(self):
        stop = asyncio.Event()
        attempts = []

        async def cycle(_function, _directory):
            attempts.append(True)
            if len(attempts) == 1:
                raise OSError("Synthetic directory read failure")
            stop.set()
            return 0

        async def immediate_wait(awaitable, *, timeout):
            if stop.is_set():
                return await awaitable
            awaitable.close()
            raise TimeoutError()

        with patch("backend.workspace_backups.run_in_threadpool", side_effect=cycle), \
                patch("backend.workspace_backups.asyncio.wait_for", side_effect=immediate_wait), \
                self.assertLogs("backend.workspace_backups", level="ERROR") as captured:
            await maintain_backups(Path("unused-synthetic-path"), stop)
        self.assertEqual(len(attempts), 2)
        self.assertIn("OSError", captured.output[0])


class GoogleSignInTests(HostedCase):
    def setUp(self):
        super().setUp()
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk = json.loads(RSAAlgorithm.to_jwk(self.key.public_key()))
        jwk.update(kid="test-key", alg="RS256", use="sig")
        self.jwks = {"keys": [jwk]}
        self.claims = {}
        self.network = []
        self.provider_responses: dict[str, httpx.Response] = {}
        self.settings.google_client_id = "test-google-client"
        self.settings.google_client_secret = SecretStr("test-secret-not-real")
        app = create_app(
            Settings(), auth_settings=self.settings,
            mailer=lambda address, subject, text: self.mail.append((address, text)),
            auth_transport=httpx.MockTransport(self.google),
        )
        self.client = self.stack.enter_context(TestClient(app, headers={"Origin": "http://testserver"}))
        self.app = app
        self.store = app.state.auth_store

    def google(self, request):
        self.network.append(request)
        if request.url.path in self.provider_responses:
            return self.provider_responses[request.url.path]
        if request.url.path == "/token":
            return httpx.Response(200, json={"id_token": jwt.encode(self.claims, self.key, algorithm="RS256", headers={"kid": "test-key"})})
        return httpx.Response(200, json=self.jwks)

    def start(self, email="google@example.com", *, link=False):
        response = self.client.get("/api/auth/google/start" + ("?link=true" if link else ""), follow_redirects=False)
        self.assertEqual(response.status_code, 302, response.text)
        parameters = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(parameters["code_challenge_method"], ["S256"])
        self.claims = {
            "iss": "https://accounts.google.com", "aud": "test-google-client", "sub": "google-subject",
            "email": email, "email_verified": True, "nonce": parameters["nonce"][0],
            "iat": int(time.time()), "exp": int(time.time()) + 300, "name": "Google user",
        }
        return parameters["state"][0]

    def callback(self, state, client=None):
        return (client or self.client).get("/api/auth/google/callback", params={"state": state, "code": "fake-code"}, follow_redirects=False)

    def test_google_sign_in_validates_tokens_and_creates_private_account(self):
        state = self.start()
        self.assertEqual(self.callback(state).status_code, 303)
        session = self.client.get("/api/auth/session").json()
        self.assertEqual(session["user"]["email"], "google@example.com")
        self.assertTrue(session["user"]["google_linked"])
        self.assertEqual(self.callback(state).status_code, 400)

    def test_cross_browser_state_is_rejected_without_a_provider_call(self):
        state = self.start()
        self.assertEqual(self.callback(state, self.other()).status_code, 400)
        self.assertEqual(self.network, [])

    def test_google_client_rejection_is_actionable_without_logging_credentials(self):
        state = self.start()
        self.provider_responses["/token"] = httpx.Response(401, json={
            "error": "invalid_client",
            "error_description": self.settings.google_client_secret.get_secret_value(),
            "id_token": "private-identity-token",
        })
        with self.assertLogs("backend.auth", level="WARNING") as captured:
            response = self.callback(state)
        self.assertEqual(response.status_code, 502)
        self.assertIn("client ID and client secret", response.json()["detail"])
        logged = "\n".join(captured.output)
        self.assertIn("stage=token_exchange", logged)
        self.assertIn("status=401", logged)
        self.assertIn("error=invalid_client", logged)
        for private in ("test-secret-not-real", "private-identity-token", "fake-code", state):
            self.assertNotIn(private, logged + response.text)
        self.assertEqual([request.url.path for request in self.network], ["/token"])
        self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_google_rejected_code_requires_a_fresh_attempt(self):
        state = self.start()
        self.provider_responses["/token"] = httpx.Response(400, json={"error": "invalid_grant"})
        with self.assertLogs("backend.auth", level="WARNING") as captured:
            response = self.callback(state)
        self.assertEqual(response.status_code, 502)
        self.assertIn("Start a new Google sign-in", response.json()["detail"])
        self.assertIn("error=invalid_grant", "\n".join(captured.output))
        self.assertEqual(self.callback(state).status_code, 400)
        self.assertEqual([request.url.path for request in self.network], ["/token"])
        self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_google_signing_key_failure_is_distinguished_from_client_rejection(self):
        state = self.start()
        self.provider_responses["/oauth2/v3/certs"] = httpx.Response(
            503, json={"error": "temporarily_unavailable"},
        )
        with self.assertLogs("backend.auth", level="WARNING") as captured:
            response = self.callback(state)
        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily unavailable", response.json()["detail"])
        self.assertIn("stage=signing_keys", "\n".join(captured.output))
        self.assertIn("status=503", "\n".join(captured.output))
        self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_google_unknown_error_payloads_are_never_exposed(self):
        for failure, marker in (
            (httpx.Response(400, json={"error": "private-provider-value"}), "unrecognized"),
            (httpx.Response(400, text="private-provider-value"), "invalid_json"),
            (httpx.Response(400, json=["private-provider-value"]), "unrecognized"),
        ):
            with self.subTest(marker=marker):
                state = self.start()
                self.provider_responses["/token"] = failure
                with self.assertLogs("backend.auth", level="WARNING") as captured:
                    response = self.callback(state)
                self.assertEqual(response.status_code, 502)
                logged = "\n".join(captured.output)
                self.assertIn("error=" + marker, logged)
                self.assertNotIn("private-provider-value", logged + response.text)
                self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_google_nonce_audience_issuer_expiry_and_verified_email_are_required(self):
        for change in (
            {"nonce": "wrong"}, {"aud": "someone-else"}, {"iss": "https://attacker.example"},
            {"exp": 1}, {"email_verified": False},
        ):
            with self.subTest(change=change):
                state = self.start()
                self.claims.update(change)
                self.assertEqual(self.callback(state).status_code, 502)
                self.assertIsNone(self.client.get("/api/auth/session").json()["user"])

    def test_google_never_implicitly_links_an_existing_email_account(self):
        self.register(email="google@example.com")
        self.client.post("/api/auth/logout")
        state = self.start()
        response = self.callback(state)
        self.assertEqual(response.status_code, 303)
        self.assertIn("google-link-required", response.headers["location"])
        self.assertIsNone(self.client.get("/api/auth/session").json()["user"])
        self.login(self.client, "google@example.com")
        user_id = self.client.get("/api/auth/session").json()["user"]["id"]
        state = self.start(link=True)
        self.assertEqual(self.callback(state).status_code, 303)
        self.assertEqual(self.client.get("/api/auth/session").json()["user"]["id"], user_id)


if __name__ == "__main__":
    unittest.main()
