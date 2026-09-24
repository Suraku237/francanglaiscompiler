import json
import sqlite3
from contextlib import closing
from unittest.mock import patch

from backend import analyzer
from backend.tests.test_analyzer_history import AnalyzerHistoryCase
from backend.tests.test_api import ApiTestCase
from compiler.lexer import tokenizer


class VocabularyApprovalTests(AnalyzerHistoryCase, ApiTestCase):
    def test_recognized_slang_and_other_categories_pass_independently_of_grammar(self):
        for text in ("je wanda", "sec souvent", "mbindi", "taxi taxi", "12 !", "", " \t\r\n"):
            with self.subTest(text=text):
                saved = self.record(text, "S -> VERB")
                self.assertEqual(saved["approval"], {
                    "basis": "no_unknown_tokens", "accepted": True, "unknown_count": 0,
                })
                self.assertFalse(saved["parse"]["accepted"])
                self.assertEqual(saved["text"], text)
        slang = self.record("je wanda", "S -> FRENCH_FUNCTION_WORD SLANG")
        self.assertEqual(slang["lexical"]["tokens"][-1]["category"], "SLANG")
        self.assertTrue(slang["approval"]["accepted"])
        self.assertTrue(slang["parse"]["accepted"])

    def test_unknown_tokens_fail_even_when_the_cfg_accepts_them(self):
        for text, grammar, count in (
            ("zqxyl", "S -> UNKNOWN", 1),
            ("  zqxyl ZQXYL\t", "S -> UNKNOWN UNKNOWN", 2),
            ("+", "S -> UNKNOWN", 1),
        ):
            with self.subTest(text=text):
                saved = self.record(text, grammar)
                self.assertEqual(saved["approval"], {
                    "basis": "no_unknown_tokens", "accepted": False, "unknown_count": count,
                })
                self.assertTrue(saved["parse"]["accepted"])
                self.assertEqual(saved["text"], text)

    def test_vocabulary_and_grammar_totals_and_summary_verdicts_are_separate(self):
        saved = [
            self.record("taxi", "S -> VERB"),
            self.record("wanda", "S -> NOUN"),
            self.record("mbindi", "S -> NOUN"),
            self.record("zqxyl", "S -> UNKNOWN"),
        ]
        report = self.report()
        self.assertEqual(report["approval_basis"], "no_unknown_tokens")
        self.assertEqual(report["summary"], {
            "total": 4, "accepted": 3, "rejected": 1, "acceptance_rate": 75.0,
        })
        self.assertEqual(report["grammar_summary"], {
            "total": 4, "accepted": 1, "rejected": 3, "acceptance_rate": 25.0,
        })
        summaries = {item["id"]: item for item in report["tests"]}
        for record in saved:
            summary = summaries[record["id"]]
            self.assertEqual(summary["accepted"], record["approval"]["accepted"])
            self.assertEqual(summary["unknown_count"], record["approval"]["unknown_count"])
            self.assertEqual(summary["grammar_accepted"], record["parse"]["accepted"])
            self.assertEqual(summary["grammar_error"], record["parse"]["error"])
            self.assertEqual(summary["error"] is None, record["approval"]["accepted"])

    def test_approval_is_derived_from_saved_categories_without_changing_stored_snapshots(self):
        saved = self.record("wanda", "S -> NOUN")
        path = self.directory / "coursework" / "analyzer-tests.sqlite3"
        with closing(sqlite3.connect(path)) as db:
            before = db.execute("SELECT data FROM analyzer_tests WHERE id=?", (saved["id"],)).fetchone()[0]
        self.assertNotIn("approval", json.loads(before))
        with patch.object(analyzer, "analyze_manual", side_effect=AssertionError("Do not recompute")), \
                patch.object(tokenizer, "analyze_sentence", side_effect=AssertionError("Do not reclassify")):
            reopened = self.make_client().get(f"/api/analyzer/tests/{saved['id']}")
            self.assertEqual(reopened.status_code, 200, reopened.text)
            self.assertEqual(reopened.json(), saved)
            self.assertEqual(self.report()["summary"]["accepted"], 1)
            self.assertEqual(self.report()["grammar_summary"]["accepted"], 0)
        with closing(sqlite3.connect(path)) as db:
            after = db.execute("SELECT data FROM analyzer_tests WHERE id=?", (saved["id"],)).fetchone()[0]
        self.assertEqual(after, before)

    def test_pure_analyzer_also_separates_vocabulary_from_cfg_without_saving_a_test(self):
        response = self.client.post("/api/analyzer/analyze", json={"text": "je wanda", "grammar": "S -> NOUN"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["approval"]["accepted"])
        self.assertFalse(response.json()["parse"]["accepted"])
        self.assertEqual(self.report()["summary"]["total"], 0)
