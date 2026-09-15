"""Test suite. Run with:  python -m unittest discover -s tests -t .

The test cases are drawn from the corpus, so a failure here means the analyzer has
regressed on real data rather than on an invented example.
"""

import unittest

from fca.analysis import analyse
from fca.generate import Generator
from fca.grammar import load_grammar
from fca.langid import profile
from fca.lexer import Lexer
from fca.lexicon import load_lexicon, normalize
from fca.parser import LL1Parser
from fca.regexspec import scan
from fca.tokens import Cat, Lang
from fca.transformations import left_factor, remove_left_recursion
from fca.translate import Translator
from fca.cli import CORPUS_FILE, GRAMMAR_FILE, RAW_GRAMMAR_FILE, REJECTS_FILE, read_corpus

LEXICON = load_lexicon()
LEXER = Lexer(LEXICON)
GRAMMAR = load_grammar(GRAMMAR_FILE)
ANALYSIS = analyse(GRAMMAR)
PARSER = LL1Parser(GRAMMAR, ANALYSIS)
TRANSLATOR = Translator(LEXICON, LEXER)


def cats(text):
    return [t.cat for t in LEXER.tokenize(text)]


def english(text):
    return TRANSLATOR.translate(text).english


class TestLexicon(unittest.TestCase):
    def test_both_dictionaries_loaded(self):
        for lang in (Lang.CAMFRANGLAIS, Lang.FRENCH):
            self.assertGreater(LEXICON.count(lang), 100, lang)

    def test_pidgin_is_gone(self):
        self.assertFalse(hasattr(Lang, "PIDGIN"))
        for bucket in LEXICON.entries.values():
            for entry in bucket:
                self.assertIn(entry.lang, {Lang.CAMFRANGLAIS, Lang.FRENCH})

    def test_normalisation_folds_accents_and_case(self):
        self.assertEqual(normalize("Ékié!"), "ekie")
        self.assertEqual(normalize("  C'EST   comment ? "), "c'est comment")

    def test_slash_variants_become_separate_keys(self):
        self.assertIn("pater", LEXICON.entries)
        self.assertIn("pasho", LEXICON.entries)

    def test_gloss_head_drops_infinitive_marker(self):
        entry = next(e for e in LEXICON.lookup("tchop") if e.cat is Cat.VERB)
        self.assertEqual(entry.head, "eat")


class TestLexer(unittest.TestCase):
    def test_multiword_entries_are_one_token(self):
        tokens = LEXER.tokenize("Je vais acheter njama njama")
        self.assertIn("njama njama", [t.norm for t in tokens])

    def test_language_tagging_across_a_mixed_utterance(self):
        tokens = LEXER.tokenize("Mola, le reseau ndem encore.")
        langs = {t.lang for t in tokens if t.cat is not Cat.PUNCT}
        self.assertIn(Lang.CAMFRANGLAIS, langs)
        self.assertIn(Lang.FRENCH, langs)

    def test_tchop_is_a_verb_after_an_auxiliary(self):
        self.assertEqual(cats("il va tchop")[-1], Cat.VERB)

    def test_tchop_is_a_noun_after_a_determiner(self):
        self.assertEqual(cats("il achete le tchop")[-1], Cat.NOUN)

    def test_a_is_the_auxiliary_before_a_verb(self):
        self.assertEqual(cats("il a mange")[1], Cat.TMA)

    def test_a_is_a_preposition_before_a_noun_phrase(self):
        self.assertEqual(cats("on va a l'amphi")[2], Cat.PREP)

    def test_second_half_of_ne_pas_is_a_particle(self):
        self.assertEqual(cats("je ne peux pas payer")[3], Cat.PART)

    def test_unknown_words_are_reported_not_silently_dropped(self):
        token = LEXER.tokenize("Mvogada")[0]
        self.assertIs(token.lang, Lang.UNKNOWN)

    def test_french_plural_falls_back_to_the_singular_entry(self):
        token = next(t for t in LEXER.tokenize("les taxis") if t.cat is Cat.NOUN)
        self.assertTrue(token.plural)
        self.assertEqual(token.norm, "taxi")


class TestRegexSpecification(unittest.TestCase):
    def test_regex_scanner_agrees_with_the_dictionary_scanner(self):
        text = "il va tchop njama njama dans le kwatt"
        by_regex = [lexeme.lower() for lexeme, _ in scan(text, LEXICON)]
        by_lexer = [t.norm for t in LEXER.tokenize(text)]
        self.assertEqual(by_regex, by_lexer)


class TestLanguageIdentification(unittest.TestCase):
    def test_camfranglais_dominant_utterance(self):
        result = profile(LEXER.tokenize("Mbom, le mbourou est ngeme, on va tchop njoh"))
        self.assertIs(result.dominant, Lang.CAMFRANGLAIS)

    def test_mixture_label_mentions_more_than_one_language(self):
        result = profile(LEXER.tokenize("Mola, le pays est dur, je n'ai pas de mbourou"))
        self.assertIn("matrix", result.label)


class TestGrammar(unittest.TestCase):
    def test_working_grammar_is_ll1(self):
        self.assertTrue(ANALYSIS.is_ll1, [str(c) for c in ANALYSIS.conflicts])

    def test_first_and_follow_are_computed_for_every_nonterminal(self):
        for nt in GRAMMAR.nonterminals:
            self.assertIn(nt, ANALYSIS.first)
            self.assertIn(nt, ANALYSIS.follow)

    def test_follow_of_start_symbol_contains_end_marker(self):
        self.assertIn("$", ANALYSIS.follow[GRAMMAR.start])

    def test_left_recursion_removal_leaves_no_left_recursion(self):
        transformed, log = remove_left_recursion(load_grammar(RAW_GRAMMAR_FILE))
        self.assertTrue(log)
        for prod in transformed.productions:
            self.assertFalse(prod.rhs and prod.rhs[0] == prod.lhs, str(prod))

    def test_left_factoring_removes_common_prefixes(self):
        factored, _ = left_factor(load_grammar(RAW_GRAMMAR_FILE))
        for nt, bucket in factored.by_lhs.items():
            heads = [p.rhs[0] for p in bucket if p.rhs]
            self.assertEqual(len(heads), len(set(heads)), nt)

    def test_no_pidgin_only_categories_remain(self):
        for name in ("PLUR", "MAKE"):
            self.assertNotIn(name, GRAMMAR.terminals, name)


class TestParser(unittest.TestCase):
    def test_every_corpus_sentence_is_accepted(self):
        for text in read_corpus(CORPUS_FILE):
            with self.subTest(text):
                result = PARSER.parse(LEXER.tokenize(text))
                self.assertTrue(result.accepted, result.error)

    def test_every_negative_case_is_rejected(self):
        for text in read_corpus(REJECTS_FILE):
            with self.subTest(text):
                self.assertFalse(PARSER.parse(LEXER.tokenize(text)).accepted)

    def test_rejection_reports_position_and_expected_set(self):
        result = PARSER.parse(LEXER.tokenize("avec avec avec le"))
        self.assertFalse(result.accepted)
        self.assertTrue(result.expected)
        self.assertIn("syntax error", result.error)

    def test_parse_tree_is_built_for_accepted_input(self):
        result = PARSER.parse(LEXER.tokenize("Il a tchop."))
        self.assertTrue(result.accepted)
        self.assertEqual(result.tree.symbol, GRAMMAR.start)
        self.assertTrue(result.tree.children)

    def test_trace_is_recorded(self):
        result = PARSER.parse(LEXER.tokenize("Il a tchop."))
        self.assertTrue(result.trace)
        self.assertEqual(result.trace[-1].action, "accept")


class TestTranslation(unittest.TestCase):
    def test_single_word_lookup_lists_every_reading(self):
        readings = TRANSLATOR.translate_word("tchop")
        self.assertTrue(any("eat" in r[2] for r in readings))

    def test_french_auxiliaries_drive_the_tense(self):
        self.assertEqual(english("Il a tchop."), "He has eaten.")
        self.assertEqual(english("Il va tchop."), "He will eat.")
        self.assertEqual(english("Il peut tchop."), "He can eat.")

    def test_negation_uses_do_support(self):
        self.assertEqual(english("Je ne tchop pas."), "I do not eat.")

    def test_zero_copula_is_filled_in(self):
        self.assertEqual(english("La moto fain."), "The motorcycle is fine.")

    def test_copula_plus_participle_is_passive(self):
        self.assertIn("is spoiled", english("La route est gate."))

    def test_object_clitic_moves_after_the_verb(self):
        self.assertIn("take me along", english("Tu peux me emmener a Mvog-Ada?"))

    def test_partitive_de_disappears_under_negation(self):
        self.assertIn("not have fuel", english("La station n'a pas d'essence."))

    def test_french_plural_reaches_english(self):
        self.assertIn("taxis", english("Les taxis sont sur la route."))

    def test_camfranglais_formula(self):
        self.assertIn("times are hard", english("Le pays est dur oh!").lower())

    def test_english_insertions_pass_through(self):
        self.assertIn("download", english("Je ne peux pas telecharger."))

    def test_every_corpus_sentence_produces_output(self):
        for text in read_corpus(CORPUS_FILE):
            with self.subTest(text):
                self.assertTrue(english(text).strip())


class TestNounPhrases(unittest.TestCase):
    def test_attributive_adjective_does_not_add_a_second_article(self):
        self.assertEqual(english("le gros piol"), "The big home.")

    def test_elided_determiner(self):
        self.assertEqual(english("L'argent a finit."), "The money has finished.")


class TestFrenchElision(unittest.TestCase):
    def test_elided_clitic_is_split_off(self):
        self.assertEqual(cats("j'ai gauler ma bolo")[:2], [Cat.PRON, Cat.TMA])

    def test_elision_translates(self):
        self.assertEqual(english("Mbom, j'ai gauler ma bolo."), "Guy, I have caught my job.")

    def test_whole_form_in_the_dictionary_is_not_split(self):
        tokens = LEXER.tokenize("C'est comment?")
        self.assertEqual(tokens[0].norm, "c'est comment")

    def test_elided_partner_is_read_as_french(self):
        token = LEXER.tokenize("j'ai")[1]
        self.assertIs(token.lang, Lang.FRENCH)


class TestVocabulary(unittest.TestCase):
    def test_camfranglais_additions(self):
        for term, meaning in (("piol", "home"), ("nang", "sleep"), ("bosh", "study")):
            with self.subTest(term):
                readings = TRANSLATOR.translate_word(term)
                self.assertTrue(readings, term)
                self.assertEqual(readings[0][0], "CAMFRANGLAIS")
                self.assertIn(meaning, readings[0][2])


class TestGenerator(unittest.TestCase):
    generator = Generator(GRAMMAR, LEXICON, LEXER, PARSER)

    def test_generated_sentences_parse(self):
        for lang in (None, Lang.CAMFRANGLAIS, Lang.FRENCH):
            for _ in range(15):
                text = self.generator.sentence(lang)
                with self.subTest(lang=lang, text=text):
                    self.assertTrue(PARSER.parse(LEXER.tokenize(text)).accepted, text)

    def test_generated_sentences_translate(self):
        for _ in range(15):
            text = self.generator.sentence()
            with self.subTest(text):
                self.assertTrue(english(text).strip())

    def test_generation_stays_within_the_loaded_languages(self):
        allowed = {Lang.CAMFRANGLAIS, Lang.FRENCH, Lang.ENGLISH, Lang.UNKNOWN}
        for _ in range(30):
            text = self.generator.sentence()
            found = {t.lang for t in LEXER.tokenize(text) if t.cat is not Cat.PUNCT}
            with self.subTest(text):
                self.assertTrue(found <= allowed, found - allowed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
