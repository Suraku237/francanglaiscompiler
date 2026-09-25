import unittest

from compiler.lexer.tokenizer import analyze_sentence
from compiler.parser.analysis import left_recursive_nonterminals
from compiler.parser.service import analyze_grammar, parse_analysis
from compiler.parser.yaounde import GRAMMAR, LIMITATIONS, RATIONALE
from compiler.tests.test_parser import bounded_language, token_stream
from compiler.tests.yaounde_cases import CORPUS_CASES


class YaoundeGrammarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis = analyze_grammar(GRAMMAR)

    def parse(self, text):
        return parse_analysis(self.analysis, [token._asdict() for token in analyze_sentence(text)["tokens"]])

    def test_every_collected_statement_has_verified_categories_and_a_genuine_parse(self):
        self.assertEqual(len(CORPUS_CASES), 12)
        self.assertEqual(len({case.text for case in CORPUS_CASES}), 12)
        for case in CORPUS_CASES:
            with self.subTest(text=case.text):
                tokens = analyze_sentence(case.text)["tokens"]
                self.assertEqual(tuple(token.category for token in tokens), case.categories)
                result = self.parse(case.text)
                self.assertEqual(result["accepted"], case.accepted, result["error"])
                self.assertTrue(result["trace"])
                if case.accepted:
                    self.assertEqual(result["consumed"], len(tokens))
                    self.assertIsNone(result["error"])
                    self.assertEqual(result["trace"][-1]["action"], "Accept: input fully consumed.")
                else:
                    self.assertEqual(result["consumed"], 5)
                    self.assertIn("lookahead UNKNOWN at token 6", result["error"])
        self.assertEqual(sum(case.accepted for case in CORPUS_CASES), 10)

    def test_real_transformations_produce_a_conflict_free_ll1_grammar(self):
        self.assertTrue(self.analysis["is_ll1"])
        self.assertEqual(self.analysis["conflicts"], [])
        self.assertEqual(left_recursive_nonterminals(self.analysis["original"]), ["Nominal"])
        self.assertEqual(left_recursive_nonterminals(self.analysis["transformed"]), [])
        self.assertEqual([step["operation"] for step in self.analysis["steps"]], [
            "eliminate_direct_left_recursion", "left_factor",
        ])
        self.assertEqual(self.analysis["first"]["Utterance"], ["FRENCH_FUNCTION_WORD", "NOUN", "VERB"])
        self.assertEqual(self.analysis["follow"]["Utterance"], ["$"])
        self.assertEqual(set(self.analysis["table"]["Utterance"]), {"FRENCH_FUNCTION_WORD", "NOUN", "VERB"})
        self.assertNotIn("UNKNOWN", self.analysis["terminals"])
        self.assertTrue(RATIONALE)
        self.assertIn("not a full grammar", LIMITATIONS)

    def test_original_and_transformed_bounded_languages_match_an_independent_oracle(self):
        original = bounded_language(self.analysis["original"], "Utterance", 4)
        transformed = bounded_language(self.analysis["transformed"], "Utterance", 4)
        self.assertEqual(original, transformed)
        self.assertGreater(len(original), 12)
        for categories in sorted(original):
            with self.subTest(categories=categories):
                self.assertTrue(parse_analysis(self.analysis, token_stream(*categories))["accepted"])

    def test_unseen_combinations_generalize_beyond_the_twelve_sentences(self):
        for text in (
            "je go au march\u00e9", "go", "mon combi came", "pere je go",
            "je suis kass", "go le taco", "le taxi go", "je go and come",
            "je suis back au school", "go au quartier shoua le kako",
        ):
            with self.subTest(text=text):
                self.assertNotIn(text, {case.text for case in CORPUS_CASES})
                self.assertTrue(self.parse(text)["accepted"])
                self.assertTrue(self.parse(text + ".")["accepted"])

    def test_known_but_unsupported_orders_are_rejected_not_just_unknown_words(self):
        for text in (
            "", "taxi", "taxi taxi", "je taxi", "je kass go", "go le", "go and",
            "je le go", "wanda", "je go ! !", "go 12", "free go",
        ):
            with self.subTest(text=text):
                self.assertNotIn("UNKNOWN", [token.category for token in analyze_sentence(text)["tokens"]])
                self.assertFalse(self.parse(text)["accepted"])
        self.assertFalse(self.parse("go +")["accepted"])
        self.assertFalse(self.parse("je go zqxyl")["accepted"])

    def test_corpus_fixture_cannot_certify_or_silently_rewrite_fieldwork(self):
        self.assertEqual(CORPUS_CASES[0].text, "J'ai n'est pas tchop depuis bayar")
        self.assertEqual(CORPUS_CASES[7].text, "Ont a cote la light depuis le shap")
        rejected = [case for case in CORPUS_CASES if not case.accepted]
        self.assertEqual([case.text.split()[5] for case in rejected], ["n'ais", "alli"])
        for case in CORPUS_CASES:
            self.assertTrue(case.reason)
