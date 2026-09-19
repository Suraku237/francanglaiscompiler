import json
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from backend import dictionary
from backend.collection import CollectionError
from backend.tests.test_api import ApiTestCase, generated
from data_collector import dataset


class DictionaryLoadingTests(unittest.TestCase):
    def test_both_supplied_files_load_without_losing_senses_or_provenance(self):
        entries = dictionary.load_dictionary()
        self.assertEqual(Counter(entry.source_document for entry in entries), {
            "camfranglais.md": 143, "extra_lexicon.md": 36,
        })
        self.assertEqual(len({entry.id for entry in entries}), 179)
        self.assertTrue(all(entry.language == "francanglais" for entry in entries))
        self.assertTrue(all(entry.source_line > 0 and entry.topic and entry.origin for entry in entries))
        self.assertEqual(len([entry for entry in entries if entry.text.casefold() == "wanda"]), 2)
        self.assertEqual(len([entry for entry in entries if entry.text == "nyoxer"]), 2)
        self.assertEqual(next(entry.english_gloss for entry in entries if entry.text == "tchop"), "to eat")
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
        self.assertEqual((first.total, first.matched, len(first.entries)), (179, 179, 25))
        self.assertTrue({entry.id for entry in first.entries}.isdisjoint(entry.id for entry in second.entries))
        self.assertEqual(dictionary.list_dictionary("  TCHOP  ", 0, 25).entries[0].english_gloss, "to eat")
        self.assertEqual(dictionary.list_dictionary("motorcycle rider", 0, 25).entries[0].text, "motard")
        self.assertEqual(dictionary.list_dictionary("pasho", 0, 25).entries[0].text, "pater / pasho")
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
    def lookup(self, text, **changes):
        return self.client.post("/api/translate", json={
            "text": text, "source_language": "francanglais", "target_language": "en",
            "allow_ai": False, **changes,
        })

    def test_dictionary_lookup_is_paginated_read_only_and_independent_of_collection(self):
        with patch.object(dataset, "load_all", side_effect=AssertionError("reference lookup must not read corpus")):
            response = self.client.get("/api/dictionary", params={"query": "pasho", "limit": 1})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual((result["total"], result["matched"], len(result["entries"])), (179, 1, 1))
        self.assertEqual(result["entries"][0]["text"], "pater / pasho")
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"query": "x" * 201}):
            self.assertEqual(self.client.get("/api/dictionary", params=params).status_code, 422)
        self.assertEqual(self.client.post("/api/dictionary", json={"text": "not fieldwork"}).status_code, 405)
        self.assertEqual(self.requests, [])

    def test_exact_supplied_words_and_aliases_work_without_ai_and_do_not_save(self):
        offline = self.make_client("")
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
                response = offline.post("/api/translate", json={
                    "text": word, "source_language": "francanglais", "target_language": "en", "allow_ai": False,
                })
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()
                self.assertEqual(result["translation"], expected)
                self.assertEqual((result["origin"], result["model"]), ("dictionary", "local-dictionary"))
                exact = [item for item in result["evidence"] if item["match_type"] == "exact"]
                self.assertTrue(exact)
                self.assertTrue(all(item["source"] == "dictionary" for item in exact))
                self.assertTrue(all(item["source_document"] and item["source_line"] for item in exact))
                self.assertTrue(all(item["french_gloss"] == "" for item in exact))
                self.assertIn("not collected fieldwork", result["note"])
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)
        self.assertEqual(self.client.get("/api/dataset").json()["total"], 0)
        self.assertEqual(self.requests, [])

    def test_exact_reverse_gloss_works_but_partial_definition_does_not(self):
        response = self.lookup("a motorcycle taxi rider", source_language="en", target_language="francanglais")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["translation"], "motard")
        self.assertEqual(self.lookup("motorcycle rider", source_language="en", target_language="francanglais").status_code, 422)
        self.assertEqual(self.requests, [])

    def test_missing_french_pidgin_and_sentence_gaps_are_not_invented(self):
        for text, changes in (
            ("tchop", {"target_language": "fr"}),
            ("tchop", {"source_language": "pidgin"}),
            ("mbom tchop motard", {}),
        ):
            with self.subTest(text=text, changes=changes):
                response = self.lookup(text, **changes)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.requests, [])

    def test_conflicting_senses_are_preserved_and_identical_glosses_are_not_ambiguous(self):
        response = self.lookup("wanda")
        self.assertEqual(response.status_code, 422)
        response = self.lookup("wanda", allow_ai=True)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["origin"], "ai_with_sources")
        self.assertTrue(any("Ambiguous" in warning for warning in result["coverage"]["warnings"]))
        self.assertEqual(len([item for item in result["evidence"] if item["text"].casefold() == "wanda"]), 2)
        self.assertEqual(self.lookup("nyoxer").status_code, 200)

    def test_dictionary_toggle_skips_all_reads_and_collection_toggle_is_independent(self):
        with patch.object(dictionary, "load_dictionary", side_effect=AssertionError("must not read dictionary")):
            self.assertEqual(self.lookup("tchop", use_dictionary=False).status_code, 422)
        with patch.object(dataset, "load_all", side_effect=AssertionError("must not read collection")):
            response = self.lookup("tchop", use_dataset=False)
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.requests, [])

    def test_english_only_references_do_not_veto_approved_french_or_approve_new_rows(self):
        self.client.post("/api/dataset", json={
            "text": "tchop", "language": "francanglais", "review_status": "approved",
            "french_gloss": "manger", "english_gloss": "to eat",
        })
        response = self.lookup("tchop", target_language="fr")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((response.json()["translation"], response.json()["origin"]), ("manger", "dataset"))
        response = self.lookup("tchop")
        self.assertEqual(response.json()["origin"], "local_sources")
        created = self.client.post("/api/dataset", json={"text": "motard", "english_gloss": "wrong fixture"})
        self.assertEqual(created.json()["review_status"], "unreviewed")
        self.assertEqual(self.lookup("motard").json()["translation"], "a motorcycle taxi rider")
        self.assertEqual(self.requests, [])

    def test_conflict_with_approved_collection_is_not_silently_overwritten(self):
        self.client.post("/api/dataset", json={
            "text": "tchop", "language": "francanglais", "review_status": "approved", "english_gloss": "fixture-food",
        })
        self.assertEqual(self.lookup("tchop").status_code, 422)
        self.assertEqual(self.lookup("tchop", use_dictionary=False).json()["translation"], "fixture-food")

    def test_reference_load_failures_are_visible_and_retryable(self):
        with patch.object(dictionary, "DICTIONARY_PATHS", (Path("missing-reference-fixture.md"),)):
            with self.assertLogs("backend.dictionary", level="ERROR"):
                for route, payload in (("/api/dictionary", None), ("/api/translate", {
                    "text": "tchop", "source_language": "francanglais", "target_language": "en",
                })):
                    response = self.client.get(route) if payload is None else self.client.post(route, json=payload)
                    self.assertEqual(response.status_code, 503, response.text)
                    self.assertNotIn("missing-reference-fixture", response.text)
        self.assertEqual(self.lookup("tchop").status_code, 200)
        self.assertEqual(self.requests, [])

    def test_chat_labels_reference_evidence_and_honours_its_toggle(self):
        self.provider_body = generated("A suggestion grounded in a dictionary entry.")
        payload = {"message": "Explain motard", "use_dataset": False, "source_language": "francanglais", "target_language": "en"}
        response = self.client.post("/api/chat", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["origin"], "ai_with_sources")
        self.assertTrue(result["evidence"])
        self.assertTrue(all(item["source"] == "dictionary" for item in result["evidence"]))
        sent = json.loads(self.requests[-1].content)
        self.assertIn("not human-approved fieldwork", sent["systemInstruction"]["parts"][0]["text"])
        supplied = sent["contents"][-1]["parts"][1]["text"].split("\n")[1]
        self.assertEqual(json.loads(supplied), result["evidence"])
        response = self.client.post("/api/chat", json={**payload, "use_dictionary": False})
        self.assertEqual(response.json()["evidence"], [])

    def test_ai_translation_receives_reference_evidence_when_collection_is_off(self):
        response = self.lookup("motard demain", use_dataset=False, allow_ai=True)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["origin"], "ai_with_sources")
        self.assertTrue(result["evidence"])
        sent = json.loads(self.requests[-1].content)
        supplied = sent["contents"][0]["parts"][1]["text"].split("\n")[1]
        self.assertEqual(json.loads(supplied), result["evidence"])


if __name__ == "__main__":
    unittest.main()
