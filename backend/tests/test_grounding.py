"""Synthetic fixtures exercise grounding; no examples are added to the real CSV."""

import csv
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import SecretStr

from backend.config import Settings
from backend.gemini import GeminiService
from backend.grounding import MAX_CANDIDATES, MAX_EVIDENCE, MAX_EVIDENCE_CHARACTERS, evidence_json, retrieve
from backend.schemas import Evidence
from backend.tests.test_api import ApiTestCase, generated
from compiler.lexer.lexicon import TERMINAL_CATEGORIES
from compiler.lexer.tokenizer import analyze_sentence
from data_collector import dataset


class MediaGenerationContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_accepts_inline_media_without_translation_schema(self):
        sent = []

        def respond(request: httpx.Request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json=generated("Extracted test text"))

        contents = [{
            "role": "user",
            "parts": [
                {"text": "Extract this test media."},
                {"inline_data": {"mime_type": "image/png", "data": "dGVzdA=="}},
            ],
        }]
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            service = GeminiService(Settings(gemini_api_key=SecretStr("test-key")), client)
            self.assertEqual(await service._generate(contents, "Read supplied media.", structured=False), "Extracted test text")
        self.assertEqual(sent[0]["contents"], contents)
        self.assertNotIn("responseSchema", sent[0]["generationConfig"])


class GroundingTests(ApiTestCase):
    def add(self, text="zandolo", **fields):
        response = self.client.post("/api/dataset", json={
            "text": text, "language": "francanglais", "review_status": "approved",
            "entry_type": "Word", "french_gloss": "amour-test", "english_gloss": "test-love",
            **fields,
        })
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_all_four_directions_for_each_local_language_work_offline(self):
        offline = self.make_client("")
        for language in ("francanglais", "pidgin"):
            entry = self.add(text=f"expression {language}", language=language, entry_type="Sentence",
                             french_gloss="Une phrase de test.", english_gloss="A test sentence.")
            for standard, gloss in (("fr", "french_gloss"), ("en", "english_gloss")):
                for source, target, text, expected in (
                    (standard, language, entry[gloss], entry["text"]),
                    (language, standard, entry["text"], entry[gloss]),
                ):
                    with self.subTest(source=source, target=target):
                        response = offline.post("/api/translate", json={
                            "text": text, "source_language": source, "target_language": target,
                            "allow_ai": False,
                        })
                        self.assertEqual(response.status_code, 200, response.text)
                        result = response.json()
                        self.assertEqual(result["translation"], expected)
                        self.assertEqual(result["model"], "local-dataset")
                        self.assertEqual(result["origin"], "dataset")
                        self.assertEqual(result["target_language"], target)
                        self.assertEqual(result["evidence"][0]["id"], entry["id"])
                        self.assertEqual(result["evidence"][0]["match_type"], "exact")
                        self.assertEqual(result["coverage"]["unmatched_terms"], [])
        self.assertEqual(self.requests, [])

    def test_same_language_validation_and_all_new_metadata_values(self):
        for language in ("fr", "en", "francanglais", "pidgin"):
            self.assertEqual(self.translate(source_language=language, target_language=language).status_code, 422)
        for invalid in ({"language": "en"}, {"review_status": "trusted"}, {"lexical_category": "*"}):
            self.assertEqual(self.client.post("/api/dataset", json={"text": "x", **invalid}).status_code, 422)
        metadata = self.client.get("/api/metadata").json()
        self.assertEqual(metadata["lexical_categories"], list(TERMINAL_CATEGORIES))
        self.assertEqual(metadata["dataset_languages"], ["francanglais", "pidgin", "mixed", "unspecified"])
        self.assertEqual(self.requests, [])

    def test_defaults_are_unreviewed_and_ai_calls_never_save(self):
        created = self.client.post("/api/dataset", json={"text": "untrusted", "english_gloss": "The taxi refused."})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["language"], "francanglais")
        self.assertEqual(created.json()["review_status"], "unreviewed")
        self.assertEqual(created.json()["lexical_category"], "")
        before = Path(dataset.DATASET_PATH).read_bytes()
        response = self.translate()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["origin"], "ai")
        self.assertEqual(response.json()["evidence"], [])
        self.assertIn("manual review", response.json()["note"])
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)

    def test_unreviewed_mixed_and_legacy_language_rows_never_ground(self):
        for text, language, review in (
            ("draft", "francanglais", "unreviewed"),
            ("mixed", "mixed", "approved"),
            ("unknown-language", "unspecified", "approved"),
        ):
            self.add(text, language=language, review_status=review, english_gloss="The taxi refused.")
        response = self.translate(allow_ai=False)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.requests, [])

    def test_ambiguity_uses_labeled_ai_or_explicit_422(self):
        first = self.add("first meaning", english_gloss="one source")
        second = self.add("second meaning", english_gloss="one source")
        before = Path(dataset.DATASET_PATH).read_bytes()
        no_ai = self.translate(text="one source", allow_ai=False)
        self.assertEqual(no_ai.status_code, 422)
        self.assertEqual(self.requests, [])
        response = self.translate(text="one source")
        result = response.json()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(result["origin"], "ai_with_dataset")
        self.assertEqual({item["id"] for item in result["evidence"]}, {first["id"], second["id"]})
        self.assertTrue(any("Ambiguous" in warning for warning in result["coverage"]["warnings"]))
        self.assertEqual(Path(dataset.DATASET_PATH).read_bytes(), before)

    def test_ambiguity_scan_is_not_limited_to_top_candidates(self):
        entry = self.add("one", english_gloss="same")
        entries = [{**entry, "id": str(index)} for index in range(MAX_CANDIDATES + 5)]
        entries.append({**entry, "id": "conflict", "text": "different"})
        result = retrieve(entries, "same", "en", "francanglais")
        self.assertTrue(result.ambiguous)
        self.assertIsNone(result.exact_translation)
        self.assertLessEqual(len(result.evidence), MAX_EVIDENCE)

    def test_exact_duplicate_alignments_are_unambiguous_and_missing_targets_are_not(self):
        first = self.add("first", english_gloss="same", french_gloss="identique")
        self.add("second", english_gloss="same", french_gloss="identique")
        response = self.translate(text="same", target_language="fr", allow_ai=False)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["translation"], "identique")
        self.client.patch(f"/api/dataset/{first['id']}", json={"french_gloss": "", "review_status": "approved"})
        self.assertEqual(self.translate(text="same", target_language="fr", allow_ai=False).status_code, 422)

    def test_word_for_word_and_phrase_overlap_are_not_sentence_translation(self):
        self.add("localalpha", english_gloss="alpha")
        self.add("localbeta", english_gloss="beta")
        self.add("local phrase", entry_type="Phrase", english_gloss="alpha beta")
        self.assertEqual(self.translate(text="alpha beta gamma", allow_ai=False).status_code, 422)
        self.assertEqual(self.requests, [])
        response = self.translate(text="alpha beta gamma")
        result = response.json()
        self.assertEqual(result["origin"], "ai_with_dataset")
        self.assertEqual(result["coverage"]["matched_terms"], ["alpha", "beta"])
        self.assertEqual(result["coverage"]["unmatched_terms"], ["gamma"])
        self.assertTrue(any(item["match_type"] == "phrase" for item in result["evidence"]))
        self.assertTrue(any("not a complete sentence" in warning for warning in result["coverage"]["warnings"]))

    def test_no_substring_or_accent_conflation_and_unicode_apostrophe_equivalence(self):
        self.add("n\u2019éko", english_gloss="test")
        for text in ("n'eko", "prefixn'éko", "n'éko-suffix"):
            with self.subTest(text=text):
                response = self.translate(text=text, source_language="francanglais", target_language="en")
                self.assertEqual(response.json()["evidence"], [])
        response = self.translate(
            text="N'E\u0301KO", source_language="francanglais", target_language="en", allow_ai=False
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["origin"], "dataset")
        self.assertEqual(response.json()["evidence"][0]["text"], "n\u2019éko")

    def test_pidgin_and_francanglais_same_expression_do_not_cross_contaminate(self):
        self.add("same", language="francanglais", english_gloss="first")
        pidgin = self.add("same", language="pidgin", english_gloss="second")
        response = self.translate(text="same", source_language="pidgin", target_language="en", allow_ai=False)
        self.assertEqual(response.json()["translation"], "second")
        self.assertEqual([item["id"] for item in response.json()["evidence"]], [pidgin["id"]])

    def test_evidence_is_relevant_private_metadata_free_and_actually_supplied(self):
        relevant = self.add("fixture", english_gloss="overlap",
                            notes="PRIVATE NOTES", source_location="PRIVATE LOCATION", contributor="PRIVATE PERSON")
        unrelated = self.add("unrelated", english_gloss="elsewhere")
        response = self.translate(text="overlap gap")
        evidence = response.json()["evidence"]
        self.assertEqual([item["id"] for item in evidence], [relevant["id"]])
        self.assertEqual(set(evidence[0]), {"id", "text", "language", "french_gloss", "english_gloss", "match_type"})
        sent = json.loads(self.requests[-1].content)
        encoded = json.dumps(sent)
        self.assertNotIn("PRIVATE", encoded)
        self.assertNotIn(unrelated["id"], encoded)
        self.assertEqual(sent["contents"][0]["parts"][0]["text"], "overlap gap")
        supplied = sent["contents"][0]["parts"][1]["text"].split("\n")[1]
        self.assertEqual(json.loads(supplied), evidence)
        self.assertNotIn("PRIVATE", json.dumps(evidence))

    def test_evidence_and_prompt_budgets(self):
        entry = self.add("base", english_gloss="overlap")
        entries = [
            {**entry, "id": f"candidate-{index}", "text": f"fixture-{index} " + "q" * 3800}
            for index in range(100)
        ]
        with patch.object(dataset, "load_all", return_value=entries):
            response = self.translate(text="overlap unknown")
        self.assertEqual(response.status_code, 200, response.text)
        evidence = [Evidence.model_validate(item) for item in response.json()["evidence"]]
        self.assertLessEqual(len(evidence), MAX_EVIDENCE)
        self.assertLessEqual(len(evidence_json(evidence)), MAX_EVIDENCE_CHARACTERS)
        self.assertLess(len(self.requests[-1].content), 25000)
        self.assertTrue(any("budget" in warning for warning in response.json()["coverage"]["warnings"]))

    def test_dataset_disabled_never_reads_or_discloses_and_no_ai_is_an_error(self):
        self.add("private fixture", english_gloss="The taxi refused.")
        with patch.object(dataset, "load_all", side_effect=AssertionError("must not read")):
            response = self.translate(use_dataset=False)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["origin"], "ai")
            self.assertEqual(response.json()["evidence"], [])
            self.assertNotIn("private fixture", self.requests[-1].content.decode())
            self.assertEqual(self.translate(use_dataset=False, allow_ai=False).status_code, 422)
            self.provider_body = generated("An AI suggestion.")
            chat = self.client.post("/api/chat", json={"message": "private fixture", "use_dataset": False})
            self.assertEqual(chat.status_code, 200, chat.text)
            self.assertEqual(chat.json()["evidence"], [])

    def test_storage_failures_in_translation_chat_and_lexer_are_visible(self):
        with patch.object(dataset, "load_all", side_effect=OSError("private path")):
            for endpoint, payload in (
                ("/api/translate", {"text": "hello"}),
                ("/api/chat", {"message": "hello"}),
                ("/api/analyze", {"text": "hello"}),
            ):
                response = self.client.post(endpoint, json=payload)
                self.assertEqual(response.status_code, 500, response.text)
                self.assertNotIn("private path", response.text)
        self.assertEqual(self.requests, [])

    def test_chat_uses_recent_user_context_and_only_selected_actual_evidence(self):
        relevant = self.add("zandolo")
        self.add("other-fixture", english_gloss="elsewhere")
        self.provider_body = generated("Suggested wording; source imaginary-999 is not a real citation.")
        response = self.client.post("/api/chat", json={
            "message": "Another example please?", "language": "fr",
            "source_language": "francanglais", "target_language": "en",
            "history": [
                {"role": "user", "content": "Explain zandolo"},
                {"role": "assistant", "content": "Previous AI answer."},
            ],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["origin"], "ai_with_dataset")
        self.assertEqual([item["id"] for item in response.json()["evidence"]], [relevant["id"]])
        sent = json.loads(self.requests[-1].content)
        supplied = sent["contents"][-1]["parts"][1]["text"].split("\n")[1]
        self.assertEqual(json.loads(supplied), response.json()["evidence"])
        instruction = sent["systemInstruction"]["parts"][0]["text"]
        self.assertIn("Nigerian Pidgin", instruction)
        self.assertIn("French", instruction)
        self.assertIn("unverified AI suggestion", instruction)

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
