import unittest

from tools.build_report_evidence import (
    ROOT, compute_evidence, render_fragments, tex, write_or_check,
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

    def test_latex_escaping_preserves_raw_quotes_and_special_characters(self) -> None:
        self.assertEqual(tex("n'ais & 50%_x"), r"n'ais \& 50\%\_x")
        self.assertEqual(tex(r"\input{x}"), r"\textbackslash{}input\{x\}")
        self.assertIn("n'ais", render_fragments(self.evidence)["tokens-c.tex"])

    def test_committed_evidence_matches_fresh_computation(self) -> None:
        result = write_or_check(ROOT, check=True)
        self.assertEqual(result["generated_files"], 20)
        self.assertEqual(result["tokens"], 81)


if __name__ == "__main__":
    unittest.main()
