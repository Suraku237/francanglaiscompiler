import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import examples
from backend.collection import CollectionError
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
        with tempfile.TemporaryDirectory(prefix=".examples-test-", dir=Path(__file__).parent) as temporary:
            path = Path(temporary) / "examples.csv"
            with patch.object(examples, "EXAMPLES_PATH", path):
                for content in (None, "", "text,notes\nsomething,unknown\n"):
                    if content is not None:
                        path.write_text(content, encoding="utf-8")
                    with self.subTest(content=content), self.assertRaises(CollectionError) as result:
                        examples.load_examples()
                    self.assertEqual(result.exception.status_code, 503)

    def test_competing_supplied_senses_are_not_discarded(self):
        original = examples.load_examples()[0]
        conflicting = original.model_copy(update={"id": "examples:conflict", "french_gloss": "Different meaning"})
        with patch.object(examples, "load_examples", return_value=[original, conflicting]):
            result = examples.list_examples(original.text, 0, 25)
        self.assertEqual(result.matched, 2)
        self.assertEqual([entry.french_gloss for entry in result.entries],
                         [original.french_gloss, conflicting.french_gloss])


class PracticeApiTests(ApiTestCase):
    include_academic = True

    def test_examples_are_labeled_synthetic_and_never_become_collected_fieldwork(self):
        dataset.ensure_dataset_file()
        before = Path(dataset.DATASET_PATH).read_bytes()
        response = self.client.get("/api/examples?limit=100")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 26)
        self.assertTrue(all(row["constructed"] for row in response.json()["entries"]))
        self.assertTrue(all(row["french_gloss"] and row["english_gloss"] for row in response.json()["entries"]))
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(self.client.get("/api/coursework").json()["stats"]["total"], 0)
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assert_no_outbound_http()

    def test_read_only_search_and_pagination_do_not_read_the_collection(self):
        with patch.object(dataset, "load_all", side_effect=AssertionError("Examples are independent references")):
            first = self.client.get("/api/examples", params={"limit": 25}).json()
            last = self.client.get("/api/examples", params={"offset": 25, "limit": 25}).json()
            searched = self.client.get("/api/examples", params={"query": "motorcycle rider"}).json()
        self.assertEqual((len(first["entries"]), len(last["entries"])), (25, 1))
        self.assertTrue({row["id"] for row in first["entries"]}.isdisjoint(row["id"] for row in last["entries"]))
        self.assertEqual(searched["entries"][0]["text"], "Au chek point, le motard a montre son papier.")
        self.assertEqual(self.client.post("/api/examples", json={"text": "not fieldwork"}).status_code, 405)
        self.assert_no_outbound_http()

    def test_invalid_pagination_and_unavailable_source(self):
        for query in ("offset=-1", "limit=0", "limit=101", "query=" + "x" * 201):
            self.assertEqual(self.client.get("/api/examples?" + query).status_code, 422)
        with patch.object(examples, "EXAMPLES_PATH", self.directory / "missing.csv"):
            self.assertEqual(self.client.get("/api/examples").status_code, 503)
