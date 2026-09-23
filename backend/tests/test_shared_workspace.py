import copy
import hashlib
import io
import json
import sqlite3
import wave
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from PIL import Image

from backend import analyzer_history, coursework_store
from backend.analyzer_models import AnalyzerTestRequest
from backend.collection import CollectionError
from backend.shared_workspace import SharedWorkspaceStore
from backend.tests.test_hosted import HISTORY, HostedCase
from backend.workspace_backups import maintenance_cycle, set_metadata
from backend.workspaces import HistoryInput, WorkspaceStore
from data_collector import dataset
from data_collector.tests.support import synthetic_entry


def wav_content(sample: int = 0) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(sample.to_bytes(2, "little", signed=True) * 80)
    return output.getvalue()


def archive_document(document: dict) -> bytes:
    content = json.dumps(document).encode()
    manifest = {"format": 1, "files": {"workspace.json": hashlib.sha256(content).hexdigest()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("workspace.json", content)
        archive.writestr("manifest.json", json.dumps(manifest))
    return output.getvalue()


class SharedWorkspaceTests(HostedCase):
    def record(self, client=None, *, request_id=None, text="taxi", grammar="S -> NOUN"):
        response = (client or self.client).post("/api/analyzer/tests", json={
            "request_id": request_id or str(uuid4()), "text": text, "grammar": grammar,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_every_screen_reads_one_workspace_but_accounts_and_ownership_remain_distinct(self):
        owner = self.register()
        entry = self.entry(text="sharedterm", entry_type="Word", lexical_category="NOUN", review_status="approved")
        saved = self.record(text="sharedterm")
        other = self.other()
        other_user = self.register(other, "second@example.com")
        shared = other.get("/api/workspace/projects").json()
        self.assertEqual(shared["registered_users"], 2)
        self.assertTrue(shared["shared"])
        self.assertEqual([item["id"] for item in shared["projects"]], ["default"])
        self.assertEqual(shared["projects"][0]["name"], "Shared workspace")
        self.assertNotIn("email", json.dumps(shared))
        visible = other.get("/api/dataset").json()["entries"]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["id"], entry["id"])
        self.assertEqual(visible[0]["ownership"], {
            "owner_id": owner["id"], "owner_name": "Test user", "can_edit": False,
        })
        self.assertTrue(entry["ownership"]["can_edit"])
        self.assertEqual(other.get("/api/analyzer").json()["stats"]["total"], 1)
        inspected = other.get(f"/api/analyzer/tests/{saved['id']}").json()
        self.assertEqual(inspected["text"], saved["text"])
        self.assertFalse(inspected["ownership"]["can_edit"])
        self.assertEqual(self.record(other, text="sharedterm")["lexical"]["tokens"], [
            {"text": "sharedterm", "category": "NOUN"},
        ])
        for client in (self.client, other):
            report = client.get("/api/analyzer/tests").json()
            self.assertEqual(report["summary"]["total"], 2)
            self.assertEqual(report["statistics"]["total_tokens"], 2)
            self.assertEqual({item["ownership"]["owner_id"] for item in report["tests"]}, {owner["id"], other_user["id"]})
        for path in ("/api/dictionary", "/api/examples", "/api/metadata"):
            self.assertEqual(self.client.get(path).json(), other.get(path).json())
        self.assertEqual(other.get("/api/auth/session").json()["user"]["id"], other_user["id"])
        self.assertEqual(self.client.get("/api/auth/session").json()["user"]["id"], owner["id"])
        self.assertEqual(other.post("/api/auth/logout").status_code, 204)
        self.assertEqual(other.get("/api/dataset").status_code, 401)
        self.login(other, "second@example.com")
        self.assertEqual(other.get("/api/analyzer/tests").json()["summary"]["total"], 2)
        self.assertEqual(other.get("/api/dataset").json()["total"], 1)

    def test_collection_audio_revisions_and_legacy_history_are_creator_protected(self):
        self.register()
        audio = wav_content()
        response = self.client.post("/api/dataset/audio", data={"fields": json.dumps({"text": "recorded phrase"})},
                                    files={"file": ("voice.wav", audio, "audio/wav")})
        self.assertEqual(response.status_code, 201, response.text)
        entry = response.json()
        saved = self.client.post("/api/workspace/history", json=HISTORY).json()
        revisions = self.client.get("/api/workspace/revisions").json()
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.get(f"/api/dataset/{entry['id']}/audio").content, audio)
        self.assertEqual(other.get(f"/api/workspace/history/{saved['id']}").json()["content"], HISTORY["content"])
        for response in (
            other.patch(f"/api/dataset/{entry['id']}", json={"text": entry["text"]}),
            other.patch(f"/api/dataset/{entry['id']}", json={"review_status": "approved"}),
            other.delete(f"/api/dataset/{entry['id']}"),
            other.patch(f"/api/dataset/{entry['id']}/audio", files={
                "fields": (None, '{"review_status":"unreviewed"}'), "remove_audio": (None, "true"),
            }),
            other.patch(f"/api/workspace/history/{saved['id']}", json={"name": "Changed"}),
            other.delete(f"/api/workspace/history/{saved['id']}"),
            other.post(f"/api/workspace/revisions/{revisions['revisions'][0]['id']}/restore", json={
                "expected_version": revisions["workspace_version"],
            }),
        ):
            self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(self.client.patch(f"/api/dataset/{entry['id']}", json={"notes": "Creator edit"}).status_code, 200)
        self.assertEqual(other.get("/api/dataset").json()["entries"][0]["notes"], "Creator edit")
        self.assertEqual(self.client.delete(f"/api/dataset/{entry['id']}").status_code, 204)
        self.assertEqual(other.get("/api/dataset").json()["total"], 0)
        rejected = other.post("/api/dataset", json={"text": "new", "ownership": entry["ownership"]})
        self.assertEqual(rejected.status_code, 422)

    def test_grammar_has_one_creator_while_everyone_can_test_local_drafts(self):
        owner = self.register()
        state = self.client.get("/api/analyzer").json()
        self.assertEqual(state["grammar_ownership"], {"owner_id": None, "owner_name": "", "can_edit": True})
        saved = self.client.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"})
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["grammar_ownership"]["owner_id"], owner["id"])
        other = self.other()
        self.register(other, "second@example.com")
        self.assertFalse(other.get("/api/analyzer").json()["grammar_ownership"]["can_edit"])
        self.assertEqual(other.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"}).status_code, 403)
        profile = coursework_store.default_project().model_dump()
        self.assertEqual(other.put("/api/coursework/project", json=profile).status_code, 403)
        test = self.record(other, text="veux", grammar="S -> VERB")
        self.assertTrue(test["parse"]["accepted"])
        self.assertEqual(self.client.get("/api/analyzer").json()["grammar"], "S -> NOUN")
        self.assertEqual(self.client.put("/api/analyzer/grammar", json={"grammar": "S -> VERB"}).status_code, 200)

    def test_parallel_creators_and_retry_keys_do_not_overwrite_each_other(self):
        first = self.register()
        other = self.other()
        second = self.register(other, "second@example.com")
        request_id = str(uuid4())
        payload = {"request_id": request_id, "text": "taxi", "grammar": "S -> NOUN"}
        with ThreadPoolExecutor(max_workers=4) as executor:
            replies = list(executor.map(
                lambda client: client.post("/api/analyzer/tests", json=payload),
                [self.client, other, self.client, other],
            ))
        self.assertEqual([reply.status_code for reply in replies], [200] * 4)
        records = [reply.json() for reply in replies]
        self.assertEqual(records[0], records[2])
        self.assertEqual(records[1], records[3])
        self.assertNotEqual(records[0]["id"], records[1]["id"])
        self.assertEqual({record["ownership"]["owner_id"] for record in records}, {first["id"], second["id"]})
        self.assertEqual(other.get("/api/analyzer/tests").json()["summary"]["total"], 2)
        conflict = self.client.post("/api/analyzer/tests", json={**payload, "text": "veux"})
        self.assertEqual(conflict.status_code, 409)
        self.client.headers["X-Mboa-Project"] = str(uuid4())
        self.assertEqual(self.client.get("/api/analyzer/tests").json()["summary"]["total"], 2)
        self.assertEqual(self.client.post("/api/workspace/projects", json={"name": "Hidden"}).status_code, 409)

    def test_first_grammar_save_is_atomic_between_accounts(self):
        self.register()
        other = self.other()
        self.register(other, "second@example.com")
        with ThreadPoolExecutor(max_workers=2) as executor:
            replies = list(executor.map(
                lambda client: client.put("/api/analyzer/grammar", json={"grammar": "S -> NOUN"}),
                (self.client, other),
            ))
        self.assertEqual(sorted(reply.status_code for reply in replies), [200, 403])
        for client, reply in zip((self.client, other), replies):
            self.assertEqual(client.get("/api/analyzer").json()["grammar_ownership"]["can_edit"], reply.status_code == 200)

    def test_combining_large_collections_does_not_block_manual_analyzer_or_saved_statistics(self):
        self.register()
        entries = [
            synthetic_entry(id=str(uuid4()), text=f"Collected statement {number}", entry_type="Sentence")
            for number in range(501)
        ]
        with patch.object(dataset, "load_all", return_value=entries):
            state = self.client.get("/api/analyzer")
            self.assertEqual(state.status_code, 200, state.text)
            self.assertEqual(state.json()["stats"], {"total": 501, "sentences": 501})
            self.assertTrue(self.record()["parse"]["accepted"])
        report = self.client.get("/api/analyzer/tests").json()
        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(report["statistics"]["total_tokens"], 1)

    def test_bulk_storage_update_rolls_back_if_any_changed_entry_has_another_creator(self):
        owner = self.register()
        self.entry(text="First entry")
        other = self.other()
        self.register(other, "second@example.com")
        self.entry(other, text="Second entry")
        store = SharedWorkspaceStore(self.root, owner["id"], "Test user")
        before = store.export_document()
        entries = store.load_all()
        for entry in entries:
            entry["notes"] = "Unauthorized bulk overwrite"
        with self.assertRaises(CollectionError) as failure:
            store.save_all(entries)
        self.assertEqual(failure.exception.status_code, 403)
        self.assertEqual(store.export_document(), before)

    def test_backup_restore_cannot_delete_reassign_or_edit_someone_elses_data(self):
        owner = self.register()
        first = self.entry(text="First author's record")
        store = SharedWorkspaceStore(self.root, owner["id"], "Test user")
        before_other = store.export_document()
        other = self.other()
        self.register(other, "second@example.com")
        second = self.entry(other, text="Second author's record")
        current = store.export_document()
        candidates = [before_other]
        forged = copy.deepcopy(current)
        target = next(row for row in forged["ownership"] if row["record_id"] == second["id"])
        target["owner_id"] = owner["id"]
        candidates.append(forged)
        changed = copy.deepcopy(current)
        row = next(row for row in changed["entries"] if row["id"] == second["id"])
        fields = json.loads(row["data"])
        fields["text"] = "Overwritten"
        row["data"] = json.dumps(fields)
        candidates.append(changed)
        for document in candidates:
            preview = self.client.post("/api/workspace/backups/preview", files={
                "file": ("backup.zip", archive_document(document)),
            })
            self.assertEqual(preview.status_code, 200, preview.text)
            state = preview.json()
            restored = self.client.post("/api/workspace/backups/restore", json={
                "token": state["token"], "expected_version": state["workspace_version"], "confirmation": "REPLACE",
            })
            self.assertEqual(restored.status_code, 403, restored.text)
            self.assertEqual(store.export_document(), current)
        self.assertEqual(self.client.get("/api/workspace/backups").json()["backups"], [])
        self.assertEqual({row["id"] for row in other.get("/api/dataset").json()["entries"]}, {first["id"], second["id"]})

    def test_backup_and_settings_deletion_permissions_do_not_follow_visibility(self):
        self.register()
        self.entry()
        backup = self.client.post("/api/workspace/backups").json()
        settings = {"automatic": True, "interval_hours": 168, "keep_last": 3}
        self.assertEqual(self.client.patch("/api/workspace/backups/settings", json=settings).status_code, 200)
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.get(f"/api/workspace/backups/{backup['id']}/download").status_code, 200)
        self.assertEqual(other.delete(f"/api/workspace/backups/{backup['id']}").status_code, 403)
        self.assertEqual(other.patch("/api/workspace/backups/settings", json=settings).status_code, 403)
        self.assertEqual(self.client.delete(f"/api/workspace/backups/{backup['id']}").status_code, 204)


class SharedMigrationTests(HostedCase):
    @staticmethod
    def record_legacy(store: WorkspaceStore, request_id: str, text: str, grammar: str) -> dict:
        with dataset.use_storage(store), coursework_store.use_storage(store), store.lock():
            return analyzer_history.record_test(AnalyzerTestRequest(
                request_id=request_id, text=text, grammar=grammar,
            )).model_dump()

    def test_all_accounts_and_projects_migrate_once_with_collisions_raw_text_and_media_preserved(self):
        first = self.register()
        other = self.other()
        second = self.register(other, "second@example.com")
        first_store = WorkspaceStore(self.root, first["id"])
        second_store = WorkspaceStore(self.root, second["id"])
        project = first_store.change_project("Old second project")["id"]
        project_store = WorkspaceStore(self.root, first["id"], project)
        entry_id = str(uuid4())
        filename = "b" * 32 + ".wav"
        raw = "  exact\tcollection source\r\n"
        for store, text, sample in ((first_store, raw, 1), (second_store, "Another account's source", 2)):
            (store.audio_dir / filename).write_bytes(wav_content(sample))
            store.append_entry(synthetic_entry(id=entry_id, text=text, audio_filename=filename))
            store.save_history(HistoryInput.model_validate(HISTORY))
        project_store.append_entry(synthetic_entry(id=str(uuid4()), text="In the former extra project"))
        profile = coursework_store.default_project()
        first_store.save_coursework(profile.model_copy(update={"grammar": "S -> NOUN", "discussion": "Keep original"}))
        second_store.save_coursework(profile.model_copy(update={"grammar": "S -> VERB", "discussion": "Keep second"}))
        request_id = str(uuid4())
        snapshots = [
            self.record_legacy(first_store, request_id, "taxi", "S -> NOUN"),
            self.record_legacy(project_store, request_id, "veux", "S -> VERB"),
            self.record_legacy(second_store, request_id, "taxi veux", "S -> NOUN VERB"),
        ]
        source_bytes = {store.path: store.path.read_bytes() for store in (first_store, second_store)}
        response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 200, response.text)
        entries = response.json()["entries"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(len({entry["id"] for entry in entries}), 3)
        self.assertEqual({entry["text"] for entry in entries}, {raw, "Another account's source", "In the former extra project"})
        for entry in entries:
            if entry["audio_filename"]:
                sample = 1 if entry["text"] == raw else 2
                self.assertEqual(other.get(f"/api/dataset/{entry['id']}/audio").content, wav_content(sample))
        report = other.get("/api/analyzer/tests").json()
        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(report["statistics"]["total_tokens"], 4)
        self.assertEqual(len({entry["id"] for entry in report["tests"]}), 3)
        self.assertEqual([entry["text"] for entry in report["tests"]], [snapshot["text"] for snapshot in reversed(snapshots)])
        for summary in report["tests"]:
            record = other.get(f"/api/analyzer/tests/{summary['id']}").json()
            original = next(snapshot for snapshot in snapshots if snapshot["text"] == record["text"])
            self.assertEqual({key: value for key, value in record.items() if key not in ("id", "ownership")},
                             {key: value for key, value in original.items() if key != "id"})
        shared = SharedWorkspaceStore(self.root, first["id"])
        self.assertEqual(len(shared.export_document()["legacy_profiles"]), 2)
        self.assertEqual(len(shared.histories()), 2)
        self.assertEqual(len(shared.revisions()), 3)
        for path, content in source_bytes.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(len(SharedWorkspaceStore(self.root, second["id"]).load_all()), 3)
        self.assertEqual(other.get("/api/analyzer/tests").json()["summary"]["total"], 3)
        ambiguous = self.client.post("/api/analyzer/tests", json={
            "request_id": request_id, "text": "taxi", "grammar": "S -> NOUN",
        })
        self.assertEqual(ambiguous.status_code, 409)

    def test_failed_migration_rolls_back_and_retry_does_not_duplicate_data(self):
        owner = self.register()
        source = WorkspaceStore(self.root, owner["id"])
        filename = "c" * 32 + ".wav"
        (source.audio_dir / filename).write_bytes(wav_content(3))
        source.append_entry(synthetic_entry(id=str(uuid4()), audio_filename=filename))
        original = source.path.read_bytes()
        with patch.object(WorkspaceStore, "bump", side_effect=sqlite3.OperationalError("injected migration failure")):
            response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 503, response.text)
        shared_root = self.root / "shared-workspace"
        with closing(sqlite3.connect(shared_root / "workspace.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM entries").fetchone()[0], 0)
            self.assertIsNone(db.execute("SELECT value FROM meta WHERE key='shared:initialized'").fetchone())
        self.assertEqual(list((shared_root / "audio").iterdir()), [])
        self.assertEqual(source.path.read_bytes(), original)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)
        self.assertEqual(source.path.read_bytes(), original)

    def test_missing_legacy_audio_is_reported_without_partial_import(self):
        owner = self.register()
        source = WorkspaceStore(self.root, owner["id"])
        filename = "d" * 32 + ".wav"
        source.append_entry(synthetic_entry(id=str(uuid4()), audio_filename=filename))
        response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("recording", response.json()["detail"])
        (source.audio_dir / filename).write_bytes(wav_content())
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 1)

    def test_existing_automatic_backup_schedules_cover_the_combined_workspace(self):
        owner = self.register()
        other = self.other()
        second = self.register(other, "second@example.com")
        first_store = WorkspaceStore(self.root, owner["id"])
        second_store = WorkspaceStore(self.root, second["id"])
        set_metadata(first_store, "backup:settings", {"automatic": True, "interval_hours": 168, "keep_last": 5})
        set_metadata(second_store, "backup:settings", {"automatic": True, "interval_hours": 24, "keep_last": 2})
        originals = {store.path: store.path.read_bytes() for store in (first_store, second_store)}
        self.assertEqual(self.client.get("/api/workspace/backups").json()["settings"], {
            "automatic": True, "interval_hours": 24, "keep_last": 5,
        })
        self.assertEqual(maintenance_cycle(self.root), 1)
        self.assertEqual(maintenance_cycle(self.root), 0)
        self.assertEqual(len(self.client.get("/api/workspace/backups").json()["backups"]), 1)
        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)

    def test_combined_legacy_screenshots_remain_readable_and_backup_compatible(self):
        first = self.register()
        other = self.other()
        second = self.register(other, "second@example.com")
        stores = (WorkspaceStore(self.root, first["id"]), WorkspaceStore(self.root, second["id"]))
        output = io.BytesIO()
        Image.new("RGB", (20, 20), color="green").save(output, format="PNG")
        image = output.getvalue()
        for number in range(7):
            stores[number % 2].save_coursework_screenshot(uuid4().hex, f"Original screenshot {number}", image)
        state = self.client.get("/api/coursework")
        self.assertEqual(state.status_code, 200, state.text)
        store = SharedWorkspaceStore(self.root, first["id"], "Test user")
        screenshots = store.list_coursework_screenshots()
        self.assertEqual(len(screenshots), 7)
        for screenshot in screenshots:
            self.assertEqual(other.get(f"/api/coursework/screenshots/{screenshot['id']}").content, image)
        backup = self.client.post("/api/workspace/backups")
        self.assertEqual(backup.status_code, 201, backup.text)
