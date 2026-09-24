import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from backend import dictionary
from backend.collection import CollectionError
from backend.tests.test_api import ApiTestCase
from data_collector import dataset


class DictionaryLoadingTests(unittest.TestCase):
    def test_csv_and_distinct_legacy_senses_load_without_losing_provenance(self):
        entries = dictionary.load_dictionary()
        self.assertEqual(Counter(entry.source_document for entry in entries), {
            "full_lexicon_classified.csv": 878, "camfranglais.md": 59, "extra_lexicon.md": 1,
        })
        self.assertEqual(len({entry.id for entry in entries}), 938)
        self.assertEqual(Counter(entry.language for entry in entries), {"francanglais": 260, "fr": 316, "en": 362})
        self.assertTrue(all(entry.source_line > 0 and entry.topic and entry.origin for entry in entries))
        self.assertEqual(len([entry for entry in entries if entry.text.casefold() == "wanda"]), 2)
        self.assertEqual(len([entry for entry in entries if entry.text == "nyoxer"]), 2)
        self.assertEqual(next(entry.english_gloss for entry in entries if "tchop" in entry.aliases), "to eat")
        self.assertEqual(next(entry.english_gloss for entry in entries if entry.text == "motard"),
                         "a motorcycle taxi rider")

    def test_documented_aliases_optional_wording_and_punctuation(self):
        self.assertEqual(dictionary.headword_aliases("pater / pasho"), ["pater", "pasho"])
        self.assertEqual(dictionary.headword_aliases("Na wa (oh)"), ["Na wa (oh)", "Na wa", "Na wa oh"])
        self.assertEqual(dictionary.headword_aliases("Ekie!"), ["Ekie!", "Ekie"])
        self.assertEqual(dictionary.headword_aliases("n’éko"), ["n’éko"])

    def test_search_covers_headwords_english_meanings_and_pagination(self):
        first = dictionary.list_dictionary("", 0, 25)
        second = dictionary.list_dictionary("", 25, 25)
        self.assertEqual((first.total, first.matched, len(first.entries)), (938, 938, 25))
        self.assertTrue({entry.id for entry in first.entries}.isdisjoint(entry.id for entry in second.entries))
        self.assertEqual(dictionary.list_dictionary("  TCHOP  ", 0, 25).entries[0].english_gloss, "to eat")
        self.assertEqual(dictionary.list_dictionary("motorcycle rider", 0, 25).entries[0].text, "motard")
        self.assertEqual(dictionary.list_dictionary("pasho", 0, 25).entries[0].text, "pater / pasho / pere")
        self.assertEqual(dictionary.list_dictionary("nonexistent-fixture", 0, 25).matched, 0)

    def test_malformed_sources_fail_instead_of_silently_discarding_rows(self):
        valid = "## Words\n| Camfranglais | English meaning | Origin |\n|---|---|---|\n| **mbom** | friend | local |\n"
        for malformed in (
            "", valid.replace("|---|---|---|\n", ""),
            valid.replace(" | friend |", " | |"),
            valid.replace("**mbom**", "** **"),
            valid.replace("**mbom**", "mbom"),
            valid + "| **broken** | missing column |\n",
        ):
            with self.subTest(source=malformed):
                with self.assertRaises(ValueError):
                    dictionary.parse_dictionary(malformed, "fixture.md")

    def test_missing_or_unreadable_dictionary_is_an_explicit_service_error(self):
        with patch.object(dictionary, "DICTIONARY_PATHS", (Path("missing-dictionary-fixture.md"),)):
            with self.assertLogs("backend.dictionary", level="ERROR"):
                with self.assertRaises(CollectionError) as context:
                    dictionary.load_dictionary()
        self.assertEqual(context.exception.status_code, 503)


class DictionaryApiTests(ApiTestCase):
    def test_dictionary_lookup_is_paginated_read_only_and_independent_of_collection(self):
        with patch.object(dataset, "load_all", side_effect=AssertionError("reference lookup must not read corpus")):
            response = self.client.get("/api/dictionary", params={"query": "pasho", "limit": 1})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["total"], result["matched"], len(result["entries"])), (938, 2, 1))
        self.assertEqual(result["entries"][0]["text"], "pater / pasho / pere")
        self.assertEqual(result["entries"][0]["part_of_speech"], "noun")
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"query": "x" * 201}):
            self.assertEqual(self.client.get("/api/dictionary", params=params).status_code, 422)
        self.assertEqual(self.client.post("/api/dictionary", json={"text": "not fieldwork"}).status_code, 405)
        self.assert_no_outbound_http()

    def test_supplied_words_and_aliases_keep_meanings_and_provenance_without_saving(self):
        self.client.get("/api/dataset")
        before = Path(dataset.DATASET_PATH).read_bytes()
        for word, expected in (
            ("tchop", "to eat"),
            ("MOTARD", "a motorcycle taxi rider"),
            ("pasho", "father; dad"),
            ("Na wa oh", "Expression of astonishment or dismay"),
            ("Ekie", "Exclamation of surprise or disbelief"),
        ):
            with self.subTest(word=word):
                response = self.client.get("/api/dictionary", params={"query": word})
                self.assertEqual(response.status_code, 200, response.text)
                entries = response.json()["entries"]
                self.assertTrue(any(item["english_gloss"] == expected for item in entries))
                self.assertTrue(all(item["source_document"] and item["source_line"] for item in entries))
                self.assertTrue(all("french_gloss" not in item for item in entries))
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assert_no_outbound_http()

    def test_both_conflicting_and_repeated_supplied_senses_remain_visible(self):
        for word in ("wanda", "nyoxer"):
            with self.subTest(word=word):
                response = self.client.get("/api/dictionary", params={"query": word})
                self.assertEqual(response.status_code, 200, response.text)
                matches = [item for item in response.json()["entries"] if item["text"].casefold() == word]
                self.assertEqual(len(matches), 2)
                self.assertEqual(len({item["id"] for item in matches}), 2)

    def test_reference_reads_do_not_override_manual_meanings_or_approve_new_rows(self):
        self.client.post("/api/dataset", json={
            "text": "tchop", "language": "francanglais", "review_status": "approved",
            "french_gloss": "manger", "english_gloss": "fixture-food",
        })
        before = Path(dataset.DATASET_PATH).read_bytes()
        reference = self.client.get("/api/dictionary", params={"query": "tchop"})
        self.assertEqual(reference.status_code, 200, reference.text)
        self.assertEqual(reference.json()["entries"][0]["english_gloss"], "to eat")
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        manual = self.client.get("/api/dataset").json()["entries"][0]
        self.assertEqual((manual["english_gloss"], manual["french_gloss"], manual["review_status"]),
                         ("fixture-food", "manger", "approved"))
        created = self.client.post("/api/dataset", json={"text": "motard", "english_gloss": "wrong fixture"})
        self.assertEqual(created.json()["review_status"], "unreviewed")
        self.assertEqual(self.client.get("/api/dictionary", params={"query": "motard"}).json()["entries"][0]["english_gloss"],
                         "a motorcycle taxi rider")
        self.assert_no_outbound_http()

    def test_reference_load_failures_are_visible_and_retryable(self):
        with patch.object(dictionary, "DICTIONARY_PATHS", (Path("missing-reference-fixture.md"),)):
            with self.assertLogs("backend.dictionary", level="ERROR"):
                response = self.client.get("/api/dictionary")
                self.assertEqual(response.status_code, 503, response.text)
                self.assertNotIn("missing-reference-fixture", response.text)
        self.assertEqual(self.client.get("/api/dictionary", params={"query": "tchop"}).status_code, 200)
        self.assert_no_outbound_http()


if __name__ == "__main__":
    unittest.main()
