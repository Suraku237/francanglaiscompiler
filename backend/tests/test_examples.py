import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import examples
from backend.collection import CollectionError
from backend.gemini import enabled_evidence
from backend.grounding import retrieve
from backend.schemas import ChatRequest, Evidence, TranslationRequest
from backend.tests.test_api import ApiTestCase
from data_collector import dataset


class PracticeLoaderTests(unittest.TestCase):
    def test_real_source_has_26_bilingual_constructed_rows(self):
        rows = examples.load_examples()
        self.assertEqual(len(rows), 26)
        self.assertEqual(len({row.id for row in rows}), 26)
        self.assertTrue(all(row.constructed and row.french_gloss and row.english_gloss for row in rows))
        self.assertEqual(rows[0].text, "Mon mbom, tu es where?")
        self.assertEqual(rows[0].french_gloss, "Mon pote, tu es o\u00f9 ?")
        self.assertEqual(rows[0].source_line, 2)
        self.assertEqual(rows[-1].source_line, 27)

    def test_search_both_meanings_and_paginate(self):
        first = examples.list_examples("", 0, 25)
        last = examples.list_examples("", 25, 25)
        self.assertEqual((first.total, first.matched, len(first.entries), len(last.entries)), (26, 26, 25, 1))
        self.assertEqual(examples.list_examples("motorcycle rider", 0, 25).entries[0].text, "Au chek point, le motard a montre son papier.")
        self.assertTrue(examples.list_examples("manger avant", 0, 25).matched)

    def test_missing_or_malformed_source_is_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "examples.csv"
            with patch.object(examples, "EXAMPLES_PATH", path):
                for content in (None, "", "text,notes\nsomething,unknown\n"):
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    with self.subTest(content=content), self.assertRaises(CollectionError) as result:
                        examples.load_examples()
                    self.assertEqual(result.exception.status_code, 503)

    def test_competing_exact_senses_are_never_silently_chosen(self):
        original = examples.load_examples()[0]
        conflicting = original.model_copy(update={"id": "examples:conflict", "french_gloss": "Different meaning"})
        result = retrieve([], original.text, "francanglais", "fr", examples=[original, conflicting])
        self.assertTrue(result.ambiguous)
        self.assertIsNone(result.exact_translation)

    def test_provider_checks_examples_switch_independently_for_both_requests(self):
        row = examples.load_examples()[0]
        example = Evidence(
            id=row.id, text=row.text, language=row.language, french_gloss=row.french_gloss,
            english_gloss=row.english_gloss, match_type="exact", source="examples",
        )
        for request in (TranslationRequest(text=row.text), ChatRequest(message=row.text)):
            self.assertEqual(enabled_evidence([example], request), [])
            selected = request.model_copy(update={"use_examples": True, "use_dataset": False, "use_dictionary": False})
            self.assertEqual(enabled_evidence([example], selected), [example])


class PracticeApiTests(ApiTestCase):
    include_academic = True

    def test_sources_are_opt_in_and_do_not_write_collection(self):
        dataset.ensure_dataset_file()
        before = Path(dataset.DATASET_PATH).read_bytes()
        response = self.client.get("/api/examples?limit=100")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 26)
        row = response.json()["entries"][0]
        base = {
            "text": row["text"], "source_language": "francanglais", "target_language": "fr",
            "allow_ai": False, "use_dictionary": False, "use_dataset": False,
        }
        self.assertEqual(self.client.post("/api/translate", json=base).status_code, 422)
        for target, field in (("fr", "french_gloss"), ("en", "english_gloss")):
            local = self.client.post("/api/translate", json={**base, "target_language": target, "use_examples": True})
            self.assertEqual(local.status_code, 200, local.text)
            body = local.json()
            self.assertEqual(body["translation"], row[field])
            self.assertEqual(body["origin"], "examples")
            self.assertEqual(body["model"], "local-examples")
            self.assertIn("Constructed", body["note"])
            self.assertEqual(body["evidence"][0]["source"], "examples")
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assertEqual(self.requests, [])

    def test_reverse_requires_complete_supplied_meaning(self):
        row = examples.load_examples()[0]
        response = self.client.post("/api/translate", json={
            "text": row.french_gloss, "source_language": "fr", "target_language": "francanglais",
            "use_examples": True, "use_dataset": False, "use_dictionary": False, "allow_ai": False,
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["translation"], row.text)
        response = self.client.post("/api/translate", json={
            "text": "My guy", "source_language": "en", "target_language": "francanglais",
            "use_examples": True, "use_dataset": False, "use_dictionary": False, "allow_ai": False,
        })
        self.assertEqual(response.status_code, 422)

    def test_invalid_pagination_and_unavailable_source(self):
        for query in ("offset=-1", "limit=0", "limit=101", "query=" + "x" * 201):
            self.assertEqual(self.client.get("/api/examples?" + query).status_code, 422)
        with patch.object(examples, "EXAMPLES_PATH", self.directory / "missing.csv"):
            self.assertEqual(self.client.get("/api/examples").status_code, 503)

    def test_chat_does_not_send_unselected_examples(self):
        self.provider_body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "Unreviewed test reply"}]}}]}
        row = examples.load_examples()[0]
        payload = {"message": row.text, "use_dataset": False, "use_dictionary": False}
        for selected in (False, True):
            response = self.client.post("/api/chat", json={**payload, "use_examples": selected})
            self.assertEqual(response.status_code, 200, response.text)
            body = json.loads(self.requests[-1].content)
            self.assertEqual(row.id in json.dumps(body), selected)
            if selected:
                self.assertEqual(response.json()["origin"], "ai_with_sources")
