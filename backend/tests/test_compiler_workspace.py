import asyncio
import base64
import copy
import csv
import hashlib
import io
import json
import random
import sqlite3
import unittest
import zipfile
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi.testclient import TestClient
from filelock import Timeout
from PIL import Image

from backend import coursework, coursework_export, coursework_store
from backend.collection import CollectionError
from backend.config import Settings
from backend.coursework_models import ProjectProfile, ScreenshotRequest
from backend.main import create_app
from backend.tests.test_hosted import HostedCase
from backend.web import JSON_REQUEST_LIMIT, SCREENSHOT_REQUEST_LIMIT
from backend.workspace_backups import validate_archive
from backend.shared_workspace import SharedWorkspaceStore as WorkspaceStore
from backend.workspaces import WorkspaceStore as LegacyWorkspaceStore
from compiler.parser.service import DEFAULT_GRAMMAR
from data_collector import dataset
from data_collector.tests.support import synthetic_entry


class CompilerHostedCase(HostedCase):
    def setUp(self):
        super().setUp()
        self.legacy_coursework = self.root / "legacy-coursework"
        self.stack.enter_context(patch.object(coursework_store, "PROJECT_DIR", self.legacy_coursework))

    @staticmethod
    def profile(**changes):
        return {
            "group_members": ["", "", ""], "grammar": DEFAULT_GRAMMAR.strip(),
            "manual_transcription_confirmed": False, "grammar_rationale": "",
            "discussion": "", "collection_method": "", "limitations": "", **changes,
        }

    def save_profile(self, client=None, **changes):
        response = (client or self.client).put("/api/coursework/project", json=self.profile(**changes))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def image_bytes(image_format="PNG", color="green", size=(100, 60)):
        output = io.BytesIO()
        Image.new("RGB", size, color=color).save(output, format=image_format)
        return output.getvalue()

    @staticmethod
    def image_url(content, mime="png"):
        return f"data:image/{mime};base64," + base64.b64encode(content).decode("ascii")

    def screenshot(self, name="Working parser", *, client=None, content=None, mime="png"):
        response = (client or self.client).post("/api/coursework/screenshots", json={
            "name": name, "data_url": self.image_url(content if content is not None else self.image_bytes(), mime),
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def project(self, name="Separate fieldwork"):
        response = self.client.post("/api/workspace/projects", json={"name": name})
        self.assertEqual(response.status_code, 409, response.text)
        return str(uuid4())

    def backup(self):
        response = self.client.post("/api/workspace/backups")
        self.assertEqual(response.status_code, 201, response.text)
        download = self.client.get(f"/api/workspace/backups/{response.json()['id']}/download")
        self.assertEqual(download.status_code, 200, download.text if download.status_code != 200 else "")
        return download.content

    def preview(self, content):
        response = self.client.post("/api/workspace/backups/preview", files={"file": ("workspace.zip", content)})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def restore(self, preview):
        return self.client.post("/api/workspace/backups/restore", json={
            "token": preview["token"], "expected_version": preview["workspace_version"], "confirmation": "REPLACE",
        })

    @staticmethod
    def archive_document(document):
        content = json.dumps(document, ensure_ascii=False).encode("utf-8")
        manifest = {"format": 1, "files": {"workspace.json": hashlib.sha256(content).hexdigest()}}
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("workspace.json", content)
            archive.writestr("manifest.json", json.dumps(manifest))
        return output.getvalue()

    def export(self, client=None):
        client = client or self.client
        user = client.get("/api/auth/session").json()["user"]
        store = WorkspaceStore(self.root, user["id"], user["display_name"])
        with dataset.use_storage(store), coursework_store.use_storage(store), dataset.dataset_lock():
            content = coursework_export.export_bundle()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return {name: archive.read(name) for name in archive.namelist()}


class HostedCourseworkTests(CompilerHostedCase):
    def test_default_coursework_and_references_require_authentication(self):
        image_id = "a" * 32
        for path in ("/api/coursework", "/api/coursework/export", "/api/examples",
                     f"/api/coursework/screenshots/{image_id}"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)
        for response in (
            self.client.put("/api/coursework/project", json=self.profile()),
            self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"}),
            self.client.post("/api/coursework/parse", json={"grammar": "S -> NOUN", "text": "taxi"}),
            self.client.post("/api/coursework/screenshots", json={"name": "Capture", "data_url": self.image_url(self.image_bytes())}),
            self.client.delete(f"/api/coursework/screenshots/{image_id}"),
        ):
            self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(self.client.get("/api/health").json(), {"status": "ok", "mode": "compiler"})

    def test_authenticated_compiler_has_no_generation_routes_service_or_outbound_http(self):
        self.register()
        self.assertFalse(hasattr(self.app.state, "gemini"))
        specification = self.client.get("/openapi.json").json()
        self.assertEqual(self.client.get("/api/coursework/export").status_code, 404)
        self.assertNotIn("/api/coursework/export", specification["paths"])
        for path, payload in (
            ("/api/translate", {"text": "PRIVATE expression"}),
            ("/api/chat", {"message": "PRIVATE question"}),
            ("/api/imports/suggest", {"text": "PRIVATE source"}),
            ("/api/coursework/explain", {"grammar": "S -> NOUN", "text": "PRIVATE"}),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.post(path, json=payload).status_code, 404)
                self.assertNotIn(path, specification["paths"])
        for name in ("TranslationRequest", "ChatRequest", "CourseworkExplainRequest", "SuggestedEntry", "Evidence"):
            self.assertNotIn(name, specification["components"]["schemas"])
        self.assertEqual(self.client.post("/api/analyze", json={"text": "taxi"}).status_code, 200)
        self.assertEqual(self.client.post("/api/coursework/parse", json={"grammar": "S -> NOUN", "text": "taxi"}).status_code, 200)
        self.assertEqual(self.client.post("/api/imports/preview", files={"file": ("fieldwork.txt", b"  Raw wording  ")}).status_code, 200)
        self.assert_no_outbound_http()

    def test_blank_defaults_and_synthetic_references_do_not_invent_fieldwork(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        state = self.client.get("/api/coursework").json()
        self.assertEqual(state["project"], self.profile())
        self.assertEqual((state["stats"]["total"], state["stats"]["sentences"]), (0, 0))
        self.assertEqual(state["screenshots"], [])
        statuses = {row["id"]: row["status"] for row in state["requirements"]}
        self.assertEqual(statuses["data"], "needs_input")
        for name in ("topics", "report", "presentation"):
            self.assertEqual(statuses[name], "review")
        self.assertEqual(self.client.get("/api/metadata").json()["categories"], dataset.CATEGORIES)
        references = self.client.get("/api/examples", params={"limit": 100}).json()
        self.assertEqual(references["total"], 26)
        self.assertTrue(all(entry["constructed"] for entry in references["entries"]))
        self.assertEqual(self.client.get("/api/dictionary").json()["total"], 938)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(store.export_document()["coursework"], [])
        self.assertEqual(store.version, version)
        self.assertFalse(self.legacy_coursework.exists())
        self.assert_no_outbound_http()

    def test_coursework_mutations_and_analysis_enforce_csrf_and_origin(self):
        user = self.register()
        saved = self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        for headers in ({"X-CSRF-Token": ""}, {"Origin": "https://attacker.example"}):
            with self.subTest(headers=headers):
                for response in (
                    self.client.put("/api/coursework/project", json=self.profile(grammar="S -> NOUN"), headers=headers),
                    self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"}, headers=headers),
                    self.client.post("/api/coursework/parse", json={"grammar": "S -> NOUN", "text": "taxi"}, headers=headers),
                    self.client.post("/api/coursework/screenshots", json={"name": "No save", "data_url": self.image_url(self.image_bytes())}, headers=headers),
                    self.client.delete(saved["url"], headers=headers),
                ):
                    self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(store.version, version)
        self.assertEqual(self.client.get(saved["url"]).status_code, 200)
        self.assertEqual(self.client.get("/api/coursework").json()["project"], self.profile())

    def test_shared_profile_and_grammar_keep_creator_and_survive_application_restart(self):
        first = self.register()
        saved = self.save_profile(
            group_members=["Amina", "Benoit", "Chantal"], grammar="S -> NOUN",
            grammar_rationale="A manually chosen noun rule.", discussion="First account only.",
        )
        other = self.other()
        second = self.register(other, "second@example.com")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(other.get("/api/coursework").json()["project"], saved)
        self.assertEqual(other.put("/api/coursework/project", json=self.profile(grammar="S -> VERB")).status_code, 403)
        self.assertEqual(self.client.get("/api/coursework").json()["project"], saved)
        app = create_app(Settings(), auth_settings=self.settings,
                         mailer=lambda address, _subject, text: self.mail.append((address, text)))
        reopened = self.stack.enter_context(TestClient(app, headers={"Origin": "http://testserver"}))
        self.login(reopened)
        self.assertEqual(reopened.get("/api/coursework").json()["project"], saved)
        stored = WorkspaceStore(self.root, first["id"]).load_coursework()
        self.assertEqual(stored, ProjectProfile(**saved))

    def test_profiles_corpora_screenshots_and_offline_exports_share_one_snapshot(self):
        self.register()
        first_profile = self.save_profile(grammar="S -> NOUN", discussion="Shared retained discussion")
        first_entry = self.entry(text="taxi")
        first_image = self.screenshot("FIRST_PRIVATE_CAPTURE")
        first_png = self.client.get(first_image["url"]).content
        self.assertEqual(parse_qs(urlsplit(first_image["url"]).query), {"project": ["default"]})
        second_project = self.project()
        self.client.headers["X-Mboa-Project"] = second_project
        self.assertEqual(self.client.get("/api/coursework").json()["project"], first_profile)
        second_entry = self.entry(text="waka")
        second_image = self.screenshot("SECOND_PRIVATE_CAPTURE", content=self.image_bytes(color="blue"))
        second_png = self.client.get(second_image["url"]).content
        self.assertEqual(parse_qs(urlsplit(second_image["url"]).query), {"project": ["default"]})
        for project_id in ("default", second_project):
            with self.subTest(project=project_id):
                self.client.headers["X-Mboa-Project"] = project_id
                state = self.client.get("/api/coursework").json()
                self.assertEqual(state["project"], first_profile)
                self.assertEqual(state["stats"]["total"], 2)
                self.assertEqual(state["screenshots"], [first_image, second_image])
                analysis = self.client.post("/api/coursework/analyze", json={"grammar": first_profile["grammar"]}).json()
                self.assertEqual([row["id"] for row in analysis["tests"]], [first_entry["id"], second_entry["id"]])
                exported = self.export()
                self.assertEqual(json.loads(exported["artifacts/project.json"]), first_profile)
                rows = list(csv.DictReader(io.StringIO(exported["artifacts/dataset.csv"].decode("utf-8-sig"))))
                self.assertEqual([row["id"] for row in rows], [first_entry["id"], second_entry["id"]])
                self.assertEqual(exported["source/data_collector/dataset.csv"], exported["artifacts/dataset.csv"])
                self.assertEqual(exported["screenshots/analyzer-1.png"], first_png)
                self.assertEqual(exported["screenshots/analyzer-2.png"], second_png)
        self.client.headers["X-Mboa-Project"] = second_project
        self.assertEqual(self.client.get(f"/api/coursework/screenshots/{first_image['id']}").status_code, 200)
        self.client.headers.pop("X-Mboa-Project")
        self.assertEqual(self.client.get(second_image["url"]).content, second_png)
        other = self.other()
        self.register(other, "second@example.com")
        for image in (first_image, second_image):
            self.assertEqual(other.get(image["url"]).status_code, 200)
            self.assertEqual(other.delete(image["url"]).status_code, 403)
        shared = self.export(other)
        self.assertEqual(json.loads(shared["artifacts/project.json"]), first_profile)
        self.assertEqual(shared["artifacts/dataset.csv"], exported["artifacts/dataset.csv"])
        self.assertEqual(shared["screenshots/analyzer-1.png"], first_png)
        self.assert_no_outbound_http()

    def test_shared_reviewed_annotations_feed_every_accounts_lexer_and_parser(self):
        self.register()
        entry = self.entry(text="zandolo", entry_type="Word", lexical_category="NOUN", review_status="approved")
        request = {"grammar": "S -> NOUN", "text": "zandolo"}
        parsed = self.client.post("/api/coursework/parse", json=request).json()
        self.assertEqual(parsed["tokens"], [{"text": "zandolo", "category": "NOUN"}])
        self.assertTrue(parsed["parse"]["accepted"])
        second_project = self.project()
        self.client.headers["X-Mboa-Project"] = second_project
        learned = self.client.post("/api/coursework/parse", json=request).json()
        self.assertEqual(learned["tokens"], [{"text": "zandolo", "category": "NOUN"}])
        self.assertTrue(learned["parse"]["accepted"])
        analysis = self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"}).json()
        self.assertEqual([row["id"] for row in analysis["tests"]], [entry["id"]])
        self.assertEqual(analysis["summary"]["accepted"], 1)
        self.client.headers["X-Mboa-Project"] = "default"
        analysis = self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"}).json()
        self.assertEqual([row["id"] for row in analysis["tests"]], [entry["id"]])
        self.assertEqual(analysis["summary"]["accepted"], 1)
        other = self.other()
        self.register(other, "second@example.com")
        self.assertTrue(other.post("/api/coursework/parse", json=request).json()["parse"]["accepted"])
        self.assertEqual(other.patch(f"/api/dataset/{entry['id']}", json={"lexical_category": "VERB"}).status_code, 403)

    def test_raw_words_and_provenance_survive_collection_analysis_export_and_backup(self):
        self.register()
        raw = {
            "text": " \tLe TAXI don refuse.\r\nn’éko d'argent ?  ",
            "notes": "  Original note\r\nSecond line\t ",
            "source_location": "  Campus café  ", "contributor": "  Original collector  ",
            "english_gloss": "  Their exact English gloss  ", "french_gloss": "  Où est le taxi ?  ",
            "language": "mixed", "category": "Campus Life",
        }
        entry = self.entry(**raw)
        stored_values = {
            **raw, "source_location": raw["source_location"].strip(), "contributor": raw["contributor"].strip(),
        }
        for key, value in stored_values.items():
            self.assertEqual(entry[key], value, key)
        revised_provenance = {
            "source_location": " \tUpdated collection place  ", "contributor": "  Updated collector\t ",
        }
        response = self.client.patch(f"/api/dataset/{entry['id']}", json=revised_provenance)
        self.assertEqual(response.status_code, 200, response.text)
        entry = response.json()
        stored_values.update({key: value.strip() for key, value in revised_provenance.items()})
        for key, value in stored_values.items():
            self.assertEqual(entry[key], value, key)
        result = self.client.post("/api/coursework/analyze", json={"grammar": DEFAULT_GRAMMAR}).json()
        self.assertEqual(result["lexical"]["statements"][0]["text"], raw["text"])
        self.assertEqual(result["tests"][0]["text"], raw["text"])
        exported = self.export()
        for name in ("artifacts/dataset.csv", "source/data_collector/dataset.csv"):
            row = next(csv.DictReader(io.StringIO(exported[name].decode("utf-8-sig"), newline="")))
            self.assertEqual(row, {key: value for key, value in entry.items() if key != "ownership"})
        document, _ = validate_archive(self.backup())
        self.assertEqual(json.loads(document["entries"][0]["data"]), {key: value for key, value in entry.items() if key != "ownership"})
        self.assertEqual(self.client.get("/api/dataset").json()["entries"], [entry])
        self.assert_no_outbound_http()

    def test_legacy_collection_profile_and_screenshots_are_never_inherited_or_modified(self):
        legacy = self.legacy_directory()
        legacy.mkdir()
        dataset.append_entry(synthetic_entry(text="LEGACY_PRIVATE_FIELDWORK"))
        coursework_store.save_project(ProjectProfile(**self.profile(grammar="S -> VERB", discussion="LEGACY_PRIVATE_PROFILE")))
        legacy_image = coursework_store.add_screenshot(ScreenshotRequest(
            name="LEGACY_PRIVATE_IMAGE", data_url=self.image_url(self.image_bytes()),
        ))
        before = {path: path.read_bytes() for directory in (legacy, self.legacy_coursework)
                  for path in directory.rglob("*") if path.is_file()}
        self.register()
        state = self.client.get("/api/coursework").json()
        self.assertEqual(state["project"], self.profile())
        self.assertEqual(state["stats"]["total"], 0)
        self.assertEqual(state["screenshots"], [])
        self.assertEqual(self.client.get(legacy_image["url"]).status_code, 404)
        self.entry(text="New private corpus")
        self.save_profile(grammar="S -> NOUN")
        self.screenshot("New private image")
        self.assertEqual({path: path.read_bytes() for directory in (legacy, self.legacy_coursework)
                          for path in directory.rglob("*") if path.is_file()}, before)

    def test_hosted_writes_use_sqlite_without_creating_missing_legacy_directories(self):
        legacy = self.legacy_directory()
        user = self.register()
        self.assertEqual(self.client.get("/api/coursework").status_code, 200)
        saved = self.save_profile(grammar="S -> NOUN")
        image = self.screenshot()
        self.entry(text="taxi")
        self.export()
        self.assertFalse(legacy.exists())
        self.assertFalse(self.legacy_coursework.exists())
        with WorkspaceStore(self.root, user["id"]).connection() as db:
            profile = db.execute("SELECT project_id,data FROM coursework").fetchone()
            stored_image = db.execute("SELECT id,project_id,name,content FROM screenshots").fetchone()
        self.assertEqual(profile["project_id"], "default")
        self.assertEqual(json.loads(profile["data"]), saved)
        self.assertEqual(stored_image["id"], image["id"])
        self.assertEqual(stored_image["project_id"], "default")
        self.assertEqual(base64.b64decode(stored_image["content"]), self.client.get(image["url"]).content)

    def test_readiness_requires_human_authenticity_confirmation_not_reference_counts(self):
        self.register()
        self.client.get("/api/examples")
        self.client.get("/api/dictionary")
        self.assertEqual(self.client.get("/api/coursework").json()["stats"]["sentences"], 0)
        for index in range(10):
            self.entry(text=f"Synthetic manual-fieldwork fixture {index}", category="Other")
        self.entry(text="Word only", entry_type="Word")
        fields = {"group_members": ["Amina", "Benoit", "Chantal"], "collection_method": "Documented manual collection."}
        self.save_profile(**fields)
        state = self.client.get("/api/coursework").json()
        self.assertEqual((state["stats"]["total"], state["stats"]["sentences"]), (11, 10))
        requirements = {row["id"]: row for row in state["requirements"]}
        self.assertEqual(requirements["data"]["status"], "needs_input")
        self.save_profile(**fields, manual_transcription_confirmed=True)
        state = self.client.get("/api/coursework").json()
        requirements = {row["id"]: row for row in state["requirements"]}
        self.assertEqual(requirements["data"]["status"], "ready")
        self.assertEqual(len(state["stats"]["missing_topics"]), 10)
        self.assertEqual(requirements["topics"]["status"], "review")
        self.assertIn("does not require", requirements["topics"]["detail"])
        for index in range(10, 16):
            self.entry(text=f"Synthetic manual-fieldwork fixture {index}", category="Other")
        state = self.client.get("/api/coursework").json()
        self.assertEqual(state["stats"]["sentences"], 16)
        self.assertEqual(next(row for row in state["requirements"] if row["id"] == "data")["status"], "needs_input")
        self.assertTrue(state["project"]["manual_transcription_confirmed"])

    def test_profile_validation_and_storage_errors_preserve_last_saved_grammar(self):
        user = self.register()
        original = self.save_profile(grammar="S -> NOUN")
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        for changes in (
            {"grammar": "S -> MISSING"}, {"grammar": "x" * 12001},
            {"group_members": ["One"]}, {"group_members": ["One", "one", "Three"]},
            {"unrecognized": "not accepted"},
        ):
            response = self.client.put("/api/coursework/project", json={**original, **changes})
            self.assertEqual(response.status_code, 422, response.text)
        with patch.object(WorkspaceStore, "save_coursework", side_effect=sqlite3.OperationalError("PRIVATE storage path")):
            response = self.client.put("/api/coursework/project", json=self.profile(grammar="S -> VERB"))
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("PRIVATE", response.text)
        with patch.object(WorkspaceStore, "load_coursework", side_effect=Timeout("PRIVATE.lock")):
            response = self.client.get("/api/coursework")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(store.version, version)
        self.assertEqual(self.client.get("/api/coursework").json()["project"], original)

    def test_computed_coursework_and_export_hold_the_workspace_snapshot_lock(self):
        self.register()
        self.entry(text="taxi")
        self.save_profile(grammar="S -> NOUN")
        self.screenshot()
        lock_checks = []
        lexical_report = coursework.lexical_report
        build_report = coursework_export.build_report

        def observe_analysis(entries):
            lock_checks.append(("lexical", dataset.dataset_lock().is_locked))
            return lexical_report(entries)

        def observe_export(*args, **kwargs):
            lock_checks.append(("report", dataset.dataset_lock().is_locked))
            return build_report(*args, **kwargs)

        with patch.object(coursework, "lexical_report", side_effect=observe_analysis), \
                patch.object(coursework_export, "build_report", side_effect=observe_export):
            response = self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["summary"]["accepted"], 1)
            exported = self.export()
        self.assertIn(b"taxi", exported["artifacts/dataset.csv"])
        self.assertEqual(lock_checks, [("lexical", True), ("lexical", True), ("report", True)])

    def test_profiles_and_screenshots_prevent_deletion_of_nonempty_projects(self):
        self.register()
        profile_project = self.project("Only a profile")
        self.client.headers["X-Mboa-Project"] = profile_project
        self.save_profile()
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{profile_project}").status_code, 409)
        image_project = self.project("Only a screenshot")
        self.client.headers["X-Mboa-Project"] = image_project
        image = self.screenshot()
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{image_project}").status_code, 409)
        self.assertEqual(self.client.delete(image["url"]).status_code, 204)
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{image_project}").status_code, 409)
        empty_project = self.project("Read-only defaults")
        self.client.headers["X-Mboa-Project"] = empty_project
        self.assertEqual(self.client.get("/api/coursework").status_code, 200)
        self.assertEqual(self.client.delete(f"/api/workspace/projects/{empty_project}").status_code, 409)


class HostedScreenshotTests(CompilerHostedCase):
    def test_jpeg_is_normalized_to_private_png_and_deletion_is_persistent(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        image = self.screenshot("Capture of actual test run", content=self.image_bytes("JPEG"), mime="jpeg")
        self.assertRegex(image["id"], r"^[a-f0-9]{32}$")
        self.assertGreater(store.version, version)
        response = self.client.get(image["url"])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        with Image.open(io.BytesIO(response.content)) as png:
            self.assertEqual(png.format, "PNG")
            self.assertEqual(png.info["Title"], "Capture of actual test run")
            self.assertEqual(png.size, (100, 60))
        version = store.version
        self.assertEqual(self.client.delete(image["url"]).status_code, 204)
        self.assertGreater(store.version, version)
        self.assertEqual(self.client.get(image["url"]).status_code, 404)
        self.assertEqual(self.client.get("/api/coursework").json()["screenshots"], [])
        self.assert_no_outbound_http()

    def test_authenticated_png_between_one_and_two_mib_is_accepted_and_backed_up(self):
        self.register()
        output = io.BytesIO()
        pixels = random.Random(4110).randbytes(640 * 640 * 3)
        Image.frombytes("RGB", (640, 640), pixels).save(output, format="PNG")
        content = output.getvalue()
        self.assertGreater(len(content), 1024 * 1024)
        self.assertLess(len(content), 2 * 1024 * 1024)
        encoded = json.dumps({"name": "Large genuine-format fixture", "data_url": self.image_url(content)}).encode()
        self.assertGreater(len(encoded), JSON_REQUEST_LIMIT)
        self.assertLess(len(encoded), SCREENSHOT_REQUEST_LIMIT)
        response = self.client.post("/api/coursework/screenshots", content=encoded,
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 201, response.text)
        image = response.json()
        png = self.client.get(image["url"]).content
        self.assertLessEqual(len(png), coursework_store.MAX_IMAGE_BYTES)
        document, _ = validate_archive(self.backup())
        self.assertEqual(base64.b64decode(document["screenshots"][0]["content"], validate=True), png)
        with Image.open(io.BytesIO(png)) as restored:
            self.assertEqual(restored.tobytes(), pixels)

    def test_authentic_screenshot_endpoint_rejects_oversized_declared_and_chunked_bodies(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        declared = self.client.post("/api/coursework/screenshots", content=b"x" * (SCREENSHOT_REQUEST_LIMIT + 1))
        self.assertEqual(declared.status_code, 413, declared.text)

        def chunks():
            yield b'{"name":"Oversized","data_url":"'
            yield b"x" * SCREENSHOT_REQUEST_LIMIT
            yield b'"}'

        streamed = self.client.post("/api/coursework/screenshots", content=chunks(),
                                    headers={"Content-Type": "application/json"})
        self.assertEqual(streamed.status_code, 413, streamed.text)
        self.assertEqual(store.version, version)
        self.assertEqual(store.export_document()["screenshots"], [])

    def test_oversized_stream_is_bounded_and_sends_one_413_without_mutation(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        path = "/api/coursework/screenshots"
        request = self.client.build_request("POST", path, headers={"Content-Type": "application/json"})
        prefix = b'{"name":"Oversized","data_url":"data:image/png;base64,'
        chunks = [
            prefix, b"x" * (SCREENSHOT_REQUEST_LIMIT - len(prefix)), b"x", b'"}',
        ]
        received = []
        sent = []
        scope = {
            "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1", "method": "POST", "scheme": "http",
            "path": path, "raw_path": path.encode("ascii"), "query_string": b"", "root_path": "",
            "headers": [(name.lower(), value) for name, value in request.headers.raw
                        if name.lower() != b"content-length"],
            "client": ("testclient", 50000), "server": ("testserver", 80), "state": {},
        }

        async def receive():
            index = len(received)
            if index == len(chunks):
                return {"type": "http.disconnect"}
            received.append(chunks[index])
            return {"type": "http.request", "body": chunks[index], "more_body": index < len(chunks) - 1}

        async def send(message):
            sent.append(message.copy())

        async def execute():
            await asyncio.wait_for(self.app(scope, receive, send), timeout=10)

        asyncio.run(execute())
        self.assertEqual(len(received), 3, "The body tail must not be drained after the size limit is crossed.")
        starts = [message for message in sent if message["type"] == "http.response.start"]
        self.assertEqual([message["status"] for message in starts], [413])
        bodies = [message for message in sent if message["type"] == "http.response.body"]
        self.assertEqual(len(bodies), 1, "A downstream parser error must not emit a second response.")
        self.assertFalse(bodies[0].get("more_body", False))
        self.assertIn("size", json.loads(bodies[0]["body"])["detail"].lower())
        self.assertEqual(store.export_document(), before)
        saved = self.screenshot("Valid request after rejected stream")
        self.assertEqual(self.client.get(saved["url"]).status_code, 200)

    def test_invalid_data_names_and_ids_never_create_or_delete_screenshots(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        image = self.screenshot()
        version = store.version
        for payload in (
            {"name": "", "data_url": self.image_url(self.image_bytes())},
            {"name": " " * 3, "data_url": self.image_url(self.image_bytes())},
            {"name": "x" * 121, "data_url": self.image_url(self.image_bytes())},
            {"name": "Wrong type", "data_url": "data:text/html;base64,PHNjcmlwdD4="},
            {"name": "Bad base64", "data_url": "data:image/png;base64,AAAAA"},
            {"name": "Not an image", "data_url": self.image_url(b"not an image")},
            {"name": "Truncated", "data_url": self.image_url(self.image_bytes()[:40])},
            {"name": "Disguised GIF", "data_url": self.image_url(self.image_bytes("GIF"))},
            {"name": "Extra field", "data_url": self.image_url(self.image_bytes()), "project": "other"},
        ):
            with self.subTest(name=payload["name"]):
                response = self.client.post("/api/coursework/screenshots", json=payload)
                self.assertEqual(response.status_code, 422, response.text)
        for image_id in ("not-a-valid-id", "f" * 31, "f" * 33, image["id"].upper(), "a" * 32, "..%5Coutside"):
            with self.subTest(image_id=image_id):
                path = f"/api/coursework/screenshots/{image_id}"
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.client.delete(path).status_code, 404)
        self.assertEqual(store.version, version)
        self.assertEqual(self.client.get("/api/coursework").json()["screenshots"], [image])

    def test_image_byte_normalization_and_resolution_limits_are_explicit(self):
        user = self.register()
        store = WorkspaceStore(self.root, user["id"])
        content = self.image_bytes()
        payload = {"name": "x" * 120, "data_url": self.image_url(content)}
        for limit in (len(content) - 1, len(content) + 1):
            with self.subTest(limit=limit), patch.object(coursework_store, "MAX_IMAGE_BYTES", limit):
                response = self.client.post("/api/coursework/screenshots", json=payload)
            self.assertEqual(response.status_code, 413, response.text)
        oversized = self.image_bytes(size=(4001, 3000))
        response = self.client.post("/api/coursework/screenshots", json={
            "name": "Too many pixels", "data_url": self.image_url(oversized),
        })
        self.assertEqual(response.status_code, 413, response.text)
        self.assertIn("resolution", response.json()["detail"].lower())
        self.assertEqual(store.export_document()["screenshots"], [])
        self.assertEqual(store.version, 1)

    def test_screenshot_count_limit_is_shared_and_creator_deletion_releases_capacity(self):
        self.register()
        images = [self.screenshot(f"Capture {index}") for index in range(coursework_store.MAX_SCREENSHOTS)]
        response = self.client.post("/api/coursework/screenshots", json={
            "name": "One too many", "data_url": self.image_url(self.image_bytes()),
        })
        self.assertEqual(response.status_code, 422, response.text)
        second = self.project()
        self.client.headers["X-Mboa-Project"] = second
        response = self.client.post("/api/coursework/screenshots", json={
            "name": "Still full", "data_url": self.image_url(self.image_bytes()),
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get("/api/coursework").json()["screenshots"], images)
        self.client.headers["X-Mboa-Project"] = "default"
        self.assertEqual(self.client.delete(images[0]["url"]).status_code, 204)
        self.screenshot("Replacement capture")
        self.assertEqual(len(self.client.get("/api/coursework").json()["screenshots"]), coursework_store.MAX_SCREENSHOTS)

    def test_screenshot_storage_failures_are_sanitized_and_do_not_claim_success(self):
        user = self.register()
        image = self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        version = store.version
        cases = (
            ("save_coursework_screenshot", lambda: self.client.post("/api/coursework/screenshots", json={
                "name": "Not saved", "data_url": self.image_url(self.image_bytes()),
            })),
            ("read_coursework_screenshot", lambda: self.client.get(image["url"])),
            ("delete_coursework_screenshot", lambda: self.client.delete(image["url"])),
        )
        for method, request in cases:
            with self.subTest(method=method), patch.object(
                WorkspaceStore, method, side_effect=sqlite3.OperationalError("PRIVATE database path"),
            ):
                response = request()
            self.assertEqual(response.status_code, 500, response.text)
            self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(store.version, version)
        self.assertEqual(self.client.get("/api/coursework").json()["screenshots"], [image])


class CourseworkBackupTests(CompilerHostedCase):
    def test_shared_backup_roundtrips_coursework_and_screenshots_without_new_projects(self):
        user = self.register()
        self.save_profile(grammar="S -> NOUN", discussion="Original default profile.")
        self.entry(text="taxi")
        default_image = self.screenshot("Default capture")
        second_project = self.project()
        self.client.headers["X-Mboa-Project"] = second_project
        second_profile = self.save_profile(grammar="S -> VERB", discussion="Original second profile.")
        self.entry(text="waka")
        second_image = self.screenshot("Second capture", content=self.image_bytes(color="blue"))
        store = WorkspaceStore(self.root, user["id"])
        expected = store.export_document()
        content = self.backup()
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(json.loads(archive.read("manifest.json"))["format"], 1)
            self.assertEqual(json.loads(archive.read("workspace.json")), expected)
        self.assertEqual(expected["format"], 4)
        self.assertEqual(len(expected["coursework"]), 1)
        self.assertEqual(len(expected["screenshots"]), 2)
        changed = self.save_profile(grammar="S -> NOUN", discussion="After backup.")
        self.assertEqual(self.client.delete(second_image["url"]).status_code, 204)
        new_image = self.screenshot("After backup capture")
        self.project("After backup project")
        other = self.other()
        self.register(other, "second@example.com")
        self.assertEqual(other.put("/api/coursework/project", json=self.profile(discussion="Denied")).status_code, 403)
        preview = self.preview(content)
        self.assertEqual(preview["counts"]["coursework"], 1)
        self.assertEqual(preview["counts"]["screenshots"], 2)
        self.assertEqual(preview["counts"]["projects"], 1)
        response = self.restore(preview)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["counts"], preview["counts"])
        actual = store.export_document()
        self.assertGreater(actual["version"], expected["version"])
        for key in ("projects", "entries", "history", "revisions", "coursework", "screenshots"):
            self.assertEqual(actual[key], expected[key], key)
        for project_id, profile, image in (
            ("default", second_profile, default_image), (second_project, second_profile, second_image),
        ):
            self.client.headers["X-Mboa-Project"] = project_id
            self.assertEqual(self.client.get("/api/coursework").json()["project"], profile)
            self.assertEqual(self.client.get(image["url"]).status_code, 200)
        self.assertEqual(self.client.get(new_image["url"]).status_code, 404)
        self.assertEqual(other.get("/api/coursework").json()["project"], second_profile)
        safety = self.client.get(f"/api/workspace/backups/{response.json()['pre_restore_backup_id']}/download")
        safety_document, _ = validate_archive(safety.content)
        self.assertIn(new_image["id"], [row["id"] for row in safety_document["screenshots"]])
        self.assertIn(changed, [json.loads(row["data"]) for row in safety_document["coursework"]])

    def test_every_profile_and_screenshot_mutation_invalidates_a_backup_preview(self):
        user = self.register()
        self.save_profile(grammar="S -> NOUN")
        image = self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        operations = (
            lambda: self.save_profile(grammar="S -> VERB"),
            lambda: self.screenshot("New screenshot"),
            lambda: self.client.delete(image["url"]),
        )
        for operation in operations:
            preview = self.preview(self.backup())
            operation()
            current = store.export_document()
            self.assertGreater(current["version"], preview["workspace_version"])
            response = self.restore(preview)
            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(store.export_document(), current)

    def test_reads_analysis_and_failed_mutations_do_not_invalidate_preview(self):
        user = self.register()
        self.save_profile(grammar="S -> NOUN")
        self.entry(text="taxi")
        image = self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        preview = self.preview(self.backup())
        self.client.get("/api/coursework")
        self.client.get(image["url"])
        self.export()
        self.assertEqual(self.client.post("/api/coursework/analyze", json={"grammar": "S -> NOUN"}).status_code, 200)
        self.assertEqual(self.client.post("/api/coursework/parse", json={"grammar": "S -> NOUN", "text": "taxi"}).status_code, 200)
        self.assertEqual(self.client.put("/api/coursework/project", json=self.profile(grammar="S -> MISSING")).status_code, 422)
        self.assertEqual(self.client.post("/api/coursework/screenshots", json={"name": "Invalid", "data_url": "bad"}).status_code, 422)
        self.assertEqual(self.client.delete("/api/coursework/screenshots/" + "f" * 32).status_code, 404)
        self.assertEqual(store.version, preview["workspace_version"])
        response = self.restore(preview)
        self.assertEqual(response.status_code, 200, response.text)

    def test_format1_normalization_remains_available_without_replacing_shared_data(self):
        user = self.register()
        entry = self.entry(text="Legacy format entry")
        self.save_profile(grammar="S -> NOUN", discussion="Existing new-format profile.")
        image = self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        before = store.export_document()
        legacy = {key: value for key, value in store.export_document().items()
                  if key not in ("coursework", "screenshots", "analyzer_tests", "ownership", "test_requests", "legacy_profiles")}
        legacy["format"] = 1
        original = copy.deepcopy(legacy)
        normalized = LegacyWorkspaceStore.validate_document(legacy)
        self.assertEqual(legacy, original)
        self.assertEqual(normalized["format"], 3)
        self.assertEqual(normalized["analyzer_tests"], [])
        self.assertEqual(normalized["coursework"], [])
        self.assertEqual(normalized["screenshots"], [])
        for key in ("projects", "entries", "history", "revisions"):
            self.assertEqual(normalized[key], legacy[key])
        response = self.client.post("/api/workspace/backups/preview", files={
            "file": ("legacy.zip", self.archive_document(legacy)),
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(store.export_document(), before)
        self.assertEqual(self.client.get(image["url"]).status_code, 200)
        self.assertEqual(self.client.get("/api/dataset").json()["entries"], [entry])
        self.assertEqual(store.export_document()["format"], 4)

    def test_invalid_new_backup_records_are_rejected_without_mutating_live_data(self):
        user = self.register()
        self.save_profile(grammar="S -> NOUN")
        self.screenshot()
        store = WorkspaceStore(self.root, user["id"])
        original = store.export_document()
        mutations = (
            lambda doc: doc["coursework"][0].update(project_id=str(uuid4())),
            lambda doc: doc["coursework"].append(copy.deepcopy(doc["coursework"][0])),
            lambda doc: doc["coursework"][0].update(data="{broken"),
            lambda doc: doc["coursework"][0].update(data=json.dumps(self.profile(grammar="S -> MISSING"))),
            lambda doc: doc["coursework"][0].update(unrecognized="field"),
            lambda doc: doc["screenshots"][0].update(project_id=str(uuid4())),
            lambda doc: doc["screenshots"][0].update(id="../outside"),
            lambda doc: doc["screenshots"][0].update(content="not base64"),
            lambda doc: doc["screenshots"][0].update(content=base64.b64encode(b"not PNG").decode()),
            lambda doc: doc["screenshots"][0].update(content=base64.b64encode(self.image_bytes("JPEG")).decode()),
            lambda doc: doc["screenshots"][0].update(name=" "),
            lambda doc: doc["screenshots"][0].update(name="x" * 121),
            lambda doc: doc["screenshots"].append(copy.deepcopy(doc["screenshots"][0])),
            lambda doc: doc["screenshots"][0].update(unrecognized="field"),
            lambda doc: doc.pop("coursework"),
            lambda doc: doc.update(format=1),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                invalid = copy.deepcopy(original)
                mutate(invalid)
                with self.assertRaises(CollectionError) as failure:
                    WorkspaceStore.validate_document(invalid)
                self.assertEqual(failure.exception.status_code, 422)
                response = self.client.post("/api/workspace/backups/preview", files={
                    "file": ("invalid.zip", self.archive_document(invalid)),
                })
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(store.export_document(), original)


if __name__ == "__main__":
    unittest.main()
