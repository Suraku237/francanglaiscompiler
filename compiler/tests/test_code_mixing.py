import unittest

from compiler.lexer.languages import word_languages
from compiler.lexer.reference import reference_languages
from compiler.lexer.tokenizer import Token, analyze_sentence, classify_token


class CodeMixingTests(unittest.TestCase):
    def spans(self, text):
        return analyze_sentence(text)["code_mixed_spans"]

    def test_content_verbs_and_nouns_supply_language_evidence(self):
        self.assertEqual(self.spans("Je go au march\u00e9."), ["Je ... go", "go ... au"])
        self.assertEqual(self.spans("le school"), ["le ... school"])
        self.assertEqual(self.spans("money pour acheter"), ["money ... pour"])

    def test_all_three_supported_languages_are_compared(self):
        self.assertEqual(self.spans("je go dey"), ["je ... go", "go ... dey"])
        self.assertEqual(self.spans("le combi came au school"), [
            "le ... combi", "combi ... came", "came ... au", "au ... school",
        ])

    def test_ambiguous_part_of_speech_can_have_unambiguous_language(self):
        self.assertEqual(classify_token("back"), "AMBIGUOUS")
        self.assertEqual(word_languages("back", "AMBIGUOUS"), {"EN"})
        self.assertEqual(self.spans("je suis back du school"), [
            "suis ... back", "back ... du", "du ... school",
        ])

    def test_category_priority_does_not_force_the_language_of_homographs(self):
        self.assertEqual(classify_token("on"), "FRENCH_FUNCTION_WORD")
        self.assertEqual(classify_token("a"), "ENGLISH_FUNCTION_WORD")
        self.assertEqual(word_languages("on", "FRENCH_FUNCTION_WORD"), {"FR", "EN"})
        self.assertEqual(word_languages("a", "ENGLISH_FUNCTION_WORD"), {"FR", "EN"})
        for text in ("I go on the road", "the small car", "on me a car", "je suis au quartier"):
            with self.subTest(text=text):
                self.assertEqual(self.spans(text), [])

    def test_ambiguous_words_do_not_move_a_more_specific_endpoint(self):
        self.assertEqual(self.spans("je on go"), ["je ... go"])
        self.assertEqual(self.spans("on go au"), ["go ... au"])
        self.assertEqual(self.spans("car dey"), ["car ... dey"])

    def test_unknowns_and_numbers_do_not_invent_a_language(self):
        result = analyze_sentence("je zqxyl 12 go")
        self.assertEqual(result["code_mixed_spans"], ["je ... go"])
        self.assertEqual([token.category for token in result["tokens"]], [
            "FRENCH_FUNCTION_WORD", "UNKNOWN", "NUMBER", "VERB",
        ])
        self.assertEqual(word_languages("alli", "UNKNOWN"), set())
        self.assertEqual(self.spans("alli zqxyl"), [])

    def test_sentence_boundaries_do_not_become_code_switches(self):
        for punctuation in ".!?":
            self.assertEqual(self.spans(f"je{punctuation} go"), [])
        self.assertEqual(self.spans("je, go"), ["je ... go"])

    def test_raw_spelling_apostrophes_accents_and_repetition_are_preserved(self):
        raw = "  J\u2019AI\tGO au MARCHE\u0301! je go je go"
        result = analyze_sentence(raw)
        self.assertEqual(result["tokens"][:4], [
            Token("J\u2019AI", "VERB"), Token("GO", "VERB"),
            Token("au", "FRENCH_FUNCTION_WORD"), Token("MARCHE\u0301", "NOUN"),
        ])
        self.assertEqual(result["code_mixed_spans"], [
            "J\u2019AI ... GO", "GO ... au", "je ... go", "go ... je", "je ... go",
        ])
        self.assertEqual(set(result), {"tokens", "code_mixed_spans", "verb_phrases"})

    def test_reference_language_evidence_is_immutable_and_not_derived_from_any_etymology(self):
        languages = reference_languages()
        self.assertEqual(languages["me"], {"EN", "FR"})
        self.assertEqual(languages["came"], {"EN"})
        self.assertEqual(languages["combi"], {"PID"})
        self.assertNotIn("cote", languages)
        self.assertNotIn("yamo", languages)
        self.assertTrue(all(" " not in word for word in languages))
        self.assertIsInstance(languages["me"], frozenset)

    def test_language_evidence_does_not_change_existing_explicit_categories(self):
        expected = {
            "go": "VERB", "tchop": "NOUN", "veux": "VERB", "dey": "PIDGIN_MARKER",
            "small": "PIDGIN_MARKER", "a": "ENGLISH_FUNCTION_WORD", "on": "FRENCH_FUNCTION_WORD",
            "mbindi": "AMBIGUOUS", "back": "AMBIGUOUS", "free": "AMBIGUOUS",
        }
        for word, category in expected.items():
            with self.subTest(word=word):
                self.assertEqual(analyze_sentence(word)["tokens"], [Token(word, category)])


class CollectedFrenchFormTests(unittest.TestCase):
    def test_clear_observed_forms_are_recognized_without_correcting_the_text(self):
        expected = {
            "J'ai": "VERB", "n\u2019est": "VERB", "suis": "VERB", "Ont": "VERB",
            "ca": "FRENCH_FUNCTION_WORD", "\u00e7a": "FRENCH_FUNCTION_WORD",
            "francais": "NOUN", "fran\u00e7ais": "NOUN", "pied": "NOUN",
        }
        for word, category in expected.items():
            with self.subTest(word=word):
                self.assertEqual(analyze_sentence(word)["tokens"], [Token(word, category)])
                self.assertEqual(word_languages(word, category), {"FR"})

    def test_uncertain_forms_stay_unknown(self):
        for word in ("n'ais", "n\u2019ais", "alli", "francaiss", "suisx"):
            with self.subTest(word=word):
                self.assertEqual(analyze_sentence(word)["tokens"], [Token(word, "UNKNOWN")])
        self.assertEqual(classify_token("n'ai"), "VERB")

    def test_reviewed_words_still_have_priority_over_the_supplement(self):
        self.assertEqual(analyze_sentence("suis", {"suis": "NOUN"})["tokens"], [Token("suis", "NOUN")])
