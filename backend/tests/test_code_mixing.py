from unittest.mock import patch

from backend.tests.test_analyzer_history import AnalyzerHistoryCase
from backend.tests.test_api import ApiTestCase
from compiler.lexer import tokenizer


class CodeMixingApiTests(AnalyzerHistoryCase, ApiTestCase):
    def test_live_saved_and_corpus_analysis_use_the_same_language_evidence(self):
        text = "  Je go au march\u00e9.\t"
        created = self.client.post("/api/dataset", json={"text": text, "entry_type": "Sentence"})
        self.assertEqual(created.status_code, 201, created.text)
        before = self.client.get("/api/dataset").json()
        grammar = "S -> FRENCH_FUNCTION_WORD VERB FRENCH_FUNCTION_WORD NOUN PUNCTUATION"
        direct = self.client.post("/api/analyze", json={"text": text})
        pure = self.client.post("/api/analyzer/analyze", json={"text": text, "grammar": grammar})
        self.assertEqual(direct.status_code, 200, direct.text)
        self.assertEqual(pure.status_code, 200, pure.text)
        saved = self.record(text, grammar)
        expected = ["Je ... go", "go ... au"]
        self.assertEqual(direct.json()["code_mixed_spans"], expected)
        self.assertEqual(pure.json()["lexical"]["code_mixed_spans"], expected)
        self.assertEqual(pure.json()["corpus"]["lexical"]["statements"][0]["code_mixed_spans"], expected)
        self.assertEqual(saved["lexical"]["code_mixed_spans"], expected)
        self.assertEqual(saved["text"], text)
        self.assertTrue(saved["parse"]["accepted"])
        self.assertTrue(saved["approval"]["accepted"])
        self.assertEqual(saved["metadata"]["matching_entries"], 1)
        self.assertEqual(self.client.get("/api/dataset").json(), before)
        self.assertEqual(self.report()["summary"]["total"], 1)

    def test_new_language_detection_does_not_recompute_historical_snapshots(self):
        text = "Je go au march\u00e9."
        grammar = "S -> FRENCH_FUNCTION_WORD VERB FRENCH_FUNCTION_WORD NOUN PUNCTUATION"
        with patch.object(tokenizer, "word_languages", return_value=frozenset()):
            historical = self.record(text, grammar)
        self.assertEqual(historical["lexical"]["code_mixed_spans"], [])
        current = self.record(text, grammar)
        self.assertEqual(current["lexical"]["code_mixed_spans"], ["Je ... go", "go ... au"])
        reopened = self.make_client().get(f"/api/analyzer/tests/{historical['id']}")
        self.assertEqual(reopened.status_code, 200, reopened.text)
        self.assertEqual(reopened.json(), historical)
        self.assertNotEqual(historical["id"], current["id"])

    def test_recognized_french_forms_do_not_rewrite_historical_unknown_verdicts(self):
        original = tokenizer.classify_token

        def previous_classifier(text, learned_lexicon=None):
            return "UNKNOWN" if text == "j'ai" else original(text, learned_lexicon)

        with patch.object(tokenizer, "classify_token", side_effect=previous_classifier):
            historical = self.record("j'ai", "S -> VERB")
        current = self.record("j'ai", "S -> VERB")
        self.assertFalse(historical["approval"]["accepted"])
        self.assertFalse(historical["parse"]["accepted"])
        self.assertTrue(current["approval"]["accepted"])
        self.assertTrue(current["parse"]["accepted"])
        self.assertEqual(self.client.get(f"/api/analyzer/tests/{historical['id']}").json(), historical)
        self.assertEqual(self.report()["summary"]["accepted"], 1)
        self.assertEqual(self.report()["grammar_summary"]["accepted"], 1)
