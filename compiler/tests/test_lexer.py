import unittest

from compiler.lexer.frequency import compute_frequencies, variation_report
from compiler.lexer.tokenizer import (
    Token,
    analyze_sentence,
    classify_token,
    find_verb_phrases,
    normalize_text,
    tokenize,
)
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

    def test_decomposed_accents_match_without_rewriting_raw_tokens(self):
        raw = ["MARCHÉ", "MARCHE\u0301", "électricité", "e\u0301lectricite\u0301"]
        self.assertEqual(tokenize(" ".join(raw)), raw)
        result = analyze_sentence(" ".join(raw))
        self.assertEqual([token.text for token in result["tokens"]], raw)
        self.assertEqual([token.category for token in result["tokens"]], ["NOUN"] * 4)

    def test_combining_diacritical_blocks_attach_only_to_preceding_letters(self):
        for mark in ("\u0301", "\u1ab0", "\u1dc0", "\u20d0", "\ufe20"):
            with self.subTest(mark=mark):
                self.assertEqual(tokenize(f"x{mark}y {mark}"), [f"x{mark}y", mark])
                self.assertEqual(classify_token(mark), "UNKNOWN")

    def test_apostrophe_variants_and_accents_match_reviewed_words_exactly(self):
        for apostrophe in ("'", "\u2018", "\u2019", "\u02bc"):
            raw = f"N{apostrophe}E\u0301KO"
            with self.subTest(apostrophe=apostrophe):
                self.assertEqual(tokenize(raw), [raw])
                self.assertEqual(analyze_sentence(raw, {"n'éko": "SLANG"})["tokens"], [Token(raw, "SLANG")])
        self.assertEqual(analyze_sentence("n'eko", {"n'éko": "SLANG"})["tokens"][0].category, "UNKNOWN")

    def test_normalization_preserves_accents_and_raw_text(self):
        raw = "  N\u2019E\u0301KO\tTaxi  "
        self.assertEqual(normalize_text(raw), "n'éko taxi")
        self.assertEqual(raw, "  N\u2019E\u0301KO\tTaxi  ")
        self.assertNotEqual(normalize_text("n'éko"), normalize_text("n'eko"))

    def test_structural_rules_match_the_entire_token(self):
        for raw in ("12\n", "!\n", "12x", " 12"):
            with self.subTest(raw=raw):
                self.assertEqual(classify_token(raw), "UNKNOWN")
        self.assertEqual(classify_token("12.5"), "NUMBER")
        self.assertEqual(classify_token("!?"), "PUNCTUATION")

    def test_category_priority_and_heuristic_labels_remain_conservative(self):
        expected = {
            "dey": "PIDGIN_MARKER",
            "wahala": "PIDGIN_MARKER",
            "on": "FRENCH_FUNCTION_WORD",
            "generator": "NOUN",
            "walking": "ENGLISH_VERB_LIKE",
            "imaginer": "FRENCH_VERB_LIKE",
            "unlistedword": "UNKNOWN",
        }
        for raw, category in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(classify_token(raw), category)

    def test_reviewed_annotations_are_fresh_and_never_leak_between_calls(self):
        learned = {"syntheticnoun": "NOUN"}
        self.assertEqual(analyze_sentence("syntheticnoun", learned)["tokens"][0].category, "NOUN")
        learned["syntheticnoun"] = "VERB"
        self.assertEqual(analyze_sentence("syntheticnoun", learned)["tokens"][0].category, "VERB")
        self.assertEqual(analyze_sentence("syntheticnoun", {})["tokens"][0].category, "UNKNOWN")
        self.assertEqual(analyze_sentence("syntheticnoun")["tokens"][0].category, "UNKNOWN")

    def test_reviewed_decomposed_single_word_uses_one_normalized_key(self):
        learned = build_lexicon([{
            "text": "N\u2019E\u0301KO", "entry_type": "Word", "review_status": "approved",
            "language": "francanglais", "lexical_category": "SLANG",
        }])
        self.assertEqual(learned, {"n'éko": "SLANG"})
        self.assertEqual(analyze_sentence("n'éko", learned)["tokens"][0].category, "SLANG")


class PhraseAnnotationTests(unittest.TestCase):
    def test_source_case_spacing_and_order_are_preserved(self):
        raw = "COME down, DROP\tME! don \u00a0 REFUSE. dey\r\nfor front."
        self.assertEqual(find_verb_phrases(raw), [
            "COME down", "DROP\tME", "don \u00a0 REFUSE", "dey\r\nfor front",
        ])

    def test_repeated_occurrences_are_not_deduplicated(self):
        self.assertEqual(find_verb_phrases("DROP me; drop me."), ["DROP me", "drop me"])

    def test_accented_intermediate_words_preserve_raw_unicode(self):
        for raw in ("HALA me RÉSEAU money", "HALA me RE\u0301SEAU money"):
            with self.subTest(raw=raw):
                self.assertEqual(find_verb_phrases(raw), [raw])
                self.assertEqual(len(analyze_sentence(raw)["tokens"]), 4)

    def test_casefold_expansion_before_phrase_does_not_shift_raw_slice(self):
        self.assertEqual(find_verb_phrases("ß DROP me"), ["DROP me"])

    def test_accented_words_are_not_confused_with_unaccented_phrase_literals(self):
        for raw in ("drop mé", "drop me\u0301", "don refusé", "don refuse\u0301"):
            with self.subTest(raw=raw):
                self.assertEqual(find_verb_phrases(raw), [])

    def test_unicode_ignorecase_does_not_override_accent_preserving_casefold(self):
        for raw in ("don SPOİL", "don spoıl"):
            with self.subTest(raw=raw):
                self.assertEqual(find_verb_phrases(raw), [])
        self.assertEqual(find_verb_phrases("don SPOIL"), ["don SPOIL"])

    def test_phrases_do_not_start_or_end_inside_apostrophe_or_hyphen_tokens(self):
        for raw in ("pre-drop me", "drop me-post", "n'drop me", "drop me’s", "drop, me"):
            with self.subTest(raw=raw):
                self.assertEqual(find_verb_phrases(raw), [])

    def test_hala_pattern_retains_its_three_intermediate_word_bound(self):
        for count in range(4):
            raw = "hala me " + "x " * count + "money"
            with self.subTest(count=count):
                self.assertEqual(find_verb_phrases(raw), [raw])
        self.assertEqual(find_verb_phrases("hala me a b c d money"), [])

    def test_annotations_do_not_rewrite_or_replace_individual_tokens(self):
        result = analyze_sentence("DROP\tME")
        self.assertEqual(set(result), {"tokens", "code_mixed_spans", "verb_phrases"})
        self.assertEqual(result["verb_phrases"], ["DROP\tME"])
        self.assertEqual(result["tokens"], [Token("DROP", "VERB"), Token("ME", "UNKNOWN")])
        self.assertEqual(Token._fields, ("text", "category"))


class FrequencyTests(unittest.TestCase):
    def test_single_use_iterators_count_both_spellings_and_categories(self):
        tokens = analyze_sentence("taxi go taxi")["tokens"]
        self.assertEqual(compute_frequencies(iter(tokens)), compute_frequencies(tokens))
        by_text, by_category = compute_frequencies(iter(tokens))
        self.assertEqual(by_text, {"taxi": 2, "go": 1})
        self.assertEqual(by_category, {"NOUN": 2, "VERB": 1})
        self.assertEqual(variation_report(by_text, 1), [("taxi", 2)])

    def test_frequency_keys_remain_raw_lowercase_variations(self):
        raw = ["MARCHÉ", "marché", "marche\u0301"]
        by_text, by_category = compute_frequencies(analyze_sentence(" ".join(raw))["tokens"])
        self.assertEqual(by_text, {"marché": 2, "marche\u0301": 1})
        self.assertEqual(by_category, {"NOUN": 3})

    def test_empty_iterator_produces_empty_counters(self):
        self.assertEqual(compute_frequencies(iter(())), ({}, {}))


if __name__ == "__main__":
    unittest.main()
