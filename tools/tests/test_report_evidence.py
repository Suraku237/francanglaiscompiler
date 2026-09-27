import unittest
import tempfile
from pathlib import Path

from compiler.lexer.tokenizer import tokenize
from tools.build_report_evidence import (
    ROOT, compute_evidence, render_fragments, source_fingerprint, tex, write_or_check,
)


class CourseworkEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.evidence = compute_evidence(ROOT)

    def test_exact_corpus_and_unknown_failures(self) -> None:
        results = self.evidence["results"]
        self.assertEqual(len(results), 12)
        self.assertEqual(self.evidence["statistics"]["total_tokens"], 81)
        self.assertEqual(len(self.evidence["statistics"]["frequencies"]), 55)
        self.assertEqual(sum(entry["parse"]["accepted"] for entry in results), 10)
        rejected = [entry for entry in results if not entry["parse"]["accepted"]]
        self.assertEqual([entry["lexical"]["tokens"][5]["text"] for entry in rejected], ["n'ais", "alli"])
        self.assertTrue(all(entry["parse"]["consumed"] == 5 for entry in rejected))
        self.assertTrue(all("at token 6" in entry["parse"]["error"] for entry in rejected))

    def test_complete_conflict_free_table_and_real_transformations(self) -> None:
        grammar = self.evidence["grammar"]
        self.assertEqual(len(grammar["nonterminals"]), 12)
        self.assertEqual(sum(len(alternatives) for alternatives in grammar["transformed"].values()), 39)
        self.assertEqual(sum(len(row) for row in grammar["table"].values()), 47)
        self.assertEqual(grammar["conflicts"], [])
        self.assertTrue(grammar["is_ll1"])
        self.assertEqual([step["operation"] for step in grammar["steps"]], [
            "eliminate_direct_left_recursion", "left_factor",
        ])
        self.assertNotIn("UNKNOWN", grammar["terminals"])
        rendered = render_fragments(self.evidence)["ll1-table.tex"]
        self.assertEqual(sum(rendered.count(f"P{index:02d}") for index in range(1, 40)), 47)

    def test_boundary_controls_keep_vocabulary_and_grammar_separate(self) -> None:
        controls = self.evidence["controls"]
        self.assertEqual(len(controls), 7)
        self.assertTrue(controls[0]["vocabulary_accepted"])
        self.assertFalse(controls[0]["accepted"])
        self.assertTrue(controls[3]["accepted"])
        self.assertFalse(controls[4]["accepted"])
        self.assertTrue(controls[5]["vocabulary_accepted"])
        self.assertFalse(controls[5]["accepted"])

    def test_language_statistics_and_phrase_nonmatches_are_not_invented(self) -> None:
        results = self.evidence["results"]
        self.assertEqual(sum(len(entry["lexical"]["code_mixed_spans"]) for entry in results), 26)
        self.assertTrue(all(not entry["lexical"]["verb_phrases"] for entry in results))
        self.assertTrue(all(not entry["lexical"]["slang_expressions"] for entry in results))
        self.assertEqual(self.evidence["statistics"]["variations"], [{
            "normalized": "j'ai",
            "forms": [{"text": "J'ai", "count": 1}, {"text": "j'ai", "count": 1}],
        }])

    def test_documented_lexer_controls_preserve_token_boundaries(self) -> None:
        controls = self.evidence["lexer_controls"]
        self.assertEqual(len(controls), 8)
        self.assertEqual([entry["tokens"] for entry in controls], [
            ["j'ai"], ["go-slow"], ["a", "-"], ["3.14"],
            ["3", "."], [".", "5"], ["-", "5"], ["_", "x"],
        ])
        self.assertIn(r"\tablehead", render_fragments(self.evidence)["lexer-controls.tex"])

    def test_unicode_word_class_keeps_the_dfa_joiner_edges_disjoint(self) -> None:
        for joiner in ("'", "\u2018", "\u2019", "-"):
            with self.subTest(joiner=joiner):
                self.assertEqual(tokenize("a" + joiner), ["a", joiner])
                self.assertEqual(tokenize(joiner + "a"), [joiner, "a"])
        for word in ("e\u0301", "a\u02bc", "\u02bca", "\u02bc\u0301"):
            with self.subTest(word=word):
                self.assertEqual(tokenize(word), [word])
        self.assertEqual(tokenize("a--b"), ["a", "-", "-", "b"])

    def test_documented_pushdown_transitions_match_every_recorded_trace(self) -> None:
        table = self.evidence["grammar"]["table"]
        for entry in [*self.evidence["results"], *self.evidence["controls"]]:
            trace = entry["parse"]["trace"]
            for before, after in zip(trace, trace[1:]):
                with self.subTest(case=entry["id"], action=before["action"]):
                    if before["action"].startswith("Apply "):
                        production = table[before["stack"][-1]][before["remaining"][0]]
                        self.assertEqual(after["stack"], before["stack"][:-1] + list(reversed(production)))
                        self.assertEqual(after["remaining"], before["remaining"])
                    elif before["action"].startswith("Match "):
                        self.assertEqual(before["stack"][-1], before["remaining"][0])
                        self.assertEqual(after["stack"], before["stack"][:-1])
                        self.assertEqual(after["remaining"], before["remaining"][1:])
                    else:
                        self.fail(f"Unexpected intermediate parse action: {before['action']}")
            if entry["parse"]["accepted"]:
                self.assertEqual(trace[-1]["stack"], ["$"])
                self.assertEqual(trace[-1]["remaining"], ["$"])
                self.assertTrue(trace[-1]["action"].startswith("Accept:"))
            else:
                self.assertTrue(trace[-1]["action"].startswith("Reject:"))

    def test_latex_escaping_preserves_raw_quotes_and_special_characters(self) -> None:
        self.assertEqual(tex("n'ais & 50%_x"), r"n'ais \& 50\%\_x")
        self.assertEqual(tex(r"\input{x}"), r"\textbackslash{}input\{x\}")
        self.assertIn("n'ais", render_fragments(self.evidence)["tokens-c.tex"])

    def test_source_hashes_are_stable_across_git_line_endings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="report-source-hash-") as temporary:
            source = Path(temporary) / "source.txt"
            source.write_bytes(b"first\nsecond\n")
            expected = source_fingerprint(source)
            source.write_bytes(b"\xef\xbb\xbffirst\r\nsecond\r\n")
            self.assertEqual(source_fingerprint(source), expected)
            source.write_bytes(b"first\nchanged\n")
            self.assertNotEqual(source_fingerprint(source), expected)

    def test_committed_evidence_matches_fresh_computation(self) -> None:
        result = write_or_check(ROOT, check=True)
        self.assertEqual(result["generated_files"], 21)
        self.assertEqual(result["tokens"], 81)
        self.assertEqual(result["lexer_controls"], 8)


if __name__ == "__main__":
    unittest.main()
