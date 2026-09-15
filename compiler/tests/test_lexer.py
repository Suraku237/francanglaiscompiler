import unittest

from compiler.lexer.tokenizer import analyze_sentence, tokenize
from compiler.lexer.learned import build_lexicon


class LexerCoverageTests(unittest.TestCase):
    def test_raw_unicode_and_curly_apostrophes_are_preserved(self):
        self.assertEqual(tokenize("O\u00f9 j\u2019ai \u014bga"), ["O\u00f9", "j\u2019ai", "\u014bga"])

    def test_symbols_are_not_silently_discarded_before_parsing(self):
        tokens = analyze_sentence("taxi \U0001f600 +")["tokens"]
        self.assertEqual([token.text for token in tokens], ["taxi", "\U0001f600", "+"])
        self.assertEqual([token.category for token in tokens], ["NOUN", "UNKNOWN", "UNKNOWN"])

    def test_original_phrases_and_numbers_still_work(self):
        result = analyze_sentence("Le taxi don refuse. drop me 12.5")
        self.assertEqual(result["tokens"][0].category, "FRENCH_FUNCTION_WORD")
        self.assertEqual(result["tokens"][-1].category, "NUMBER")
        self.assertIn("don refuse", result["verb_phrases"])
        self.assertIn("drop me", result["verb_phrases"])

    def test_only_reviewed_single_words_with_unambiguous_categories_teach(self):
        def entry(text, **changes):
            return {
                "text": text, "entry_type": "Word", "review_status": "approved",
                "language": "francanglais", "lexical_category": "NOUN", **changes,
            }

        learned = build_lexicon([
            entry("zandolo"),
            entry("draftword", review_status="unreviewed"),
            entry("oldword", language="unspecified"),
            entry("mixedword", language="mixed"),
            entry("sentenceword inside", entry_type="Sentence"),
            entry("two words"),
            entry("conflictword"),
            entry("conflictword", language="pidgin", lexical_category="VERB"),
            entry("wildcardword", lexical_category="*"),
        ])
        self.assertEqual(learned, {"zandolo": "NOUN"})
        self.assertEqual(analyze_sentence("zandolo")["tokens"][0].category, "UNKNOWN")
        result = analyze_sentence("zandolo draftword sentenceword conflictword +", learned)
        self.assertEqual([token.category for token in result["tokens"]], ["NOUN"] + ["UNKNOWN"] * 4)

    def test_learned_words_use_exact_normalized_keys_and_structural_rules_still_win(self):
        learned = {"n'éko": "SLANG", "12": "NOUN", "!": "VERB", "*": "NOUN"}
        result = analyze_sentence("N\u2019ÉKO n'eko 12 ! other", learned)
        self.assertEqual(
            [token.category for token in result["tokens"]],
            ["SLANG", "UNKNOWN", "NUMBER", "PUNCTUATION", "FRENCH_VERB_LIKE"],
        )


if __name__ == "__main__":
    unittest.main()
