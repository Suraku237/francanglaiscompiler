"""Manual review, raw metadata, and learned-lexer regressions use synthetic entries."""

import csv
from pathlib import Path
from unittest.mock import patch

from backend.tests.test_api import ApiTestCase
from compiler.lexer.lexicon import TERMINAL_CATEGORIES
from compiler.lexer.tokenizer import analyze_sentence
from data_collector import dataset


class CollectionReviewTests(ApiTestCase):
    def add(self, text="zandolo", **fields):
        response = self.client.post("/api/dataset", json={
            "text": text, "language": "francanglais", "review_status": "approved",
            "entry_type": "Word", "french_gloss": "amour-test", "english_gloss": "test-love",
            **fields,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_invalid_review_metadata_is_rejected_and_metadata_lists_actual_values(self):
        for invalid in ({"language": "en"}, {"review_status": "trusted"}, {"lexical_category": "*"}):
            self.assertEqual(self.client.post("/api/dataset", json={"text": "x", **invalid}).status_code, 422)
        metadata = self.client.get("/api/metadata").json()
        self.assertEqual(metadata["lexical_categories"], list(TERMINAL_CATEGORIES))
        self.assertEqual(metadata["dataset_languages"], ["francanglais", "pidgin", "mixed", "unspecified"])
        self.assert_no_outbound_http()

    def test_defaults_are_unreviewed_and_analysis_never_approves_or_saves(self):
        created = self.client.post("/api/dataset", json={"text": "untrusted", "english_gloss": "Manual meaning"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["language"], "francanglais")
        self.assertEqual(created.json()["review_status"], "unreviewed")
        self.assertEqual(created.json()["lexical_category"], "")
        before = Path(dataset.DATASET_PATH).read_bytes()
        response = self.client.post("/api/analyze", json={"text": "untrusted"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assert_no_outbound_http()

    def test_storage_failures_in_lexer_are_visible_and_sanitized(self):
        with patch.object(dataset, "load_all", side_effect=OSError("private path")):
            response = self.client.post("/api/analyze", json={"text": "hello"})
        self.assertEqual(response.status_code, 500, response.text)
        self.assertNotIn("private path", response.text)
        self.assert_no_outbound_http()

    def test_language_only_patch_collision_and_original_metadata_preservation(self):
        text = "  Exact n\u2019éko text  "
        first = self.add(text, notes="  Original\nnotes  ")
        second = self.add(text, language="pidgin")
        collision = self.client.patch(f"/api/dataset/{second['id']}", json={"language": "francanglais"})
        self.assertEqual(collision.status_code, 409)
        changed = self.client.patch(f"/api/dataset/{first['id']}", json={"lexical_category": "NOUN"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["text"], text)
        self.assertEqual(changed.json()["notes"], "  Original\nnotes  ")
        self.assertEqual(changed.json()["id"], first["id"])
        self.assertEqual(changed.json()["timestamp"], first["timestamp"])

    def test_pre_review_csv_migrates_in_memory_and_only_explicit_save_rewrites(self):
        path = Path(dataset.DATASET_PATH)
        entry = {name: "" for name in dataset.PRE_REVIEW_FIELDNAMES}
        entry.update(id="old", text="  Older n\u2019éko  ", notes="original\nnotes", timestamp="old-time")
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=dataset.PRE_REVIEW_FIELDNAMES)
            writer.writeheader()
            writer.writerow(entry)
        before = path.read_bytes()
        response = self.client.get("/api/dataset")
        self.assertEqual(response.status_code, 200, response.text)
        migrated = response.json()["entries"][0]
        self.assertEqual(migrated["language"], "unspecified")
        self.assertEqual(migrated["review_status"], "unreviewed")
        self.assertEqual(migrated["lexical_category"], "")
        self.assertEqual(path.read_bytes(), before)
        self.client.patch("/api/dataset/old", json={"language": "pidgin"})
        saved = dataset.load_all()[0]
        self.assertEqual({key: saved[key] for key in entry}, entry)
        self.assertEqual(saved["language"], "pidgin")
        self.assertEqual(saved["review_status"], "unreviewed")
        with path.open(encoding="utf-8", newline="") as handle:
            self.assertEqual(next(csv.reader(handle)), dataset.FIELDNAMES)

    def test_desktop_missing_and_empty_fields_save_safe_defaults(self):
        entry = {name: "" for name in dataset.PRE_REVIEW_FIELDNAMES}
        entry.update(id="desktop", text="Legacy raw text", notes="keep", timestamp="keep")
        dataset.append_entry(entry)
        dataset.update_entry("desktop", {"language": "", "review_status": "", "lexical_category": "BAD"})
        saved = dataset.load_all()[0]
        self.assertEqual(saved["language"], "unspecified")
        self.assertEqual(saved["review_status"], "unreviewed")
        self.assertEqual(saved["lexical_category"], "")
        self.assertEqual(saved["notes"], "keep")

    def test_human_approval_teaches_lexer_and_unreviewing_reverts(self):
        entry = self.add("zandolo", lexical_category="NOUN", review_status="unreviewed")
        self.assertEqual(analyze_sentence("zandolo")["tokens"][0].category, "UNKNOWN")
        endpoint = "/api/analyze"
        self.assertEqual(self.client.post(endpoint, json={"text": "zandolo"}).json()["tokens"][0]["category"], "UNKNOWN")
        self.client.patch(f"/api/dataset/{entry['id']}", json={"review_status": "approved"})
        self.assertEqual(self.client.post(endpoint, json={"text": "zandolo"}).json()["tokens"][0]["category"], "NOUN")
        self.assertEqual(analyze_sentence("zandolo")["tokens"][0].category, "UNKNOWN")
        self.client.patch(f"/api/dataset/{entry['id']}", json={"review_status": "unreviewed"})
        self.assertEqual(self.client.post(endpoint, json={"text": "zandolo"}).json()["tokens"][0]["category"], "UNKNOWN")
