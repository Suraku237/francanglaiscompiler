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
    def test_all_three_dictionaries_loaded(self):
        for lang in (Lang.PIDGIN, Lang.CAMFRANGLAIS, Lang.FRENCH):
            self.assertGreater(LEXICON.count(lang), 50, lang)

    def test_normalisation_folds_accents_and_case(self):
        self.assertEqual(normalize("Ékié!"), "ekie")
        self.assertEqual(normalize("  C'EST   comment ? "), "c'est comment")

    def test_slash_variants_become_separate_keys(self):
        self.assertIn("mami", LEXICON.entries)
        self.assertIn("mama", LEXICON.entries)

    def test_gloss_head_drops_infinitive_marker(self):
        entry = next(e for e in LEXICON.lookup("tchop") if e.cat is Cat.VERB)
        self.assertEqual(entry.head, "eat")


class TestLexer(unittest.TestCase):
    def test_multiword_entries_are_one_token(self):
        tokens = LEXER.tokenize("A go bai njama njama")
        self.assertIn("njama njama", [t.norm for t in tokens])

    def test_language_tagging_across_a_mixed_utterance(self):
        tokens = LEXER.tokenize("Mola, le reseau ndem again.")
        langs = {t.lang for t in tokens if t.cat is not Cat.PUNCT}
        self.assertIn(Lang.CAMFRANGLAIS, langs)
        self.assertIn(Lang.FRENCH, langs)

    def test_chop_is_a_verb_after_a_tense_marker(self):
        self.assertEqual(cats("a don chop")[-1], Cat.VERB)

    def test_chop_is_a_noun_after_a_determiner(self):
        self.assertEqual(cats("a get di chop")[-1], Cat.NOUN)

    def test_go_is_a_future_marker_before_a_verb(self):
        self.assertEqual(cats("a go chop")[1], Cat.TMA)

    def test_go_is_a_verb_before_a_noun(self):
        self.assertEqual(cats("a go maket")[1], Cat.VERB)

    def test_post_nominal_dem_is_a_plural_marker(self):
        self.assertEqual(cats("di pikin dem")[-1], Cat.PLUR)

    def test_unknown_words_are_reported_not_silently_dropped(self):
        token = LEXER.tokenize("Mvogada")[0]
        self.assertIs(token.lang, Lang.UNKNOWN)


class TestRegexSpecification(unittest.TestCase):
    def test_regex_scanner_agrees_with_the_dictionary_scanner(self):
        text = "a don tchop njama njama for kwatt"
        by_regex = [lexeme.lower() for lexeme, _ in scan(text, LEXICON)]
        by_lexer = [t.norm for t in LEXER.tokenize(text)]
        self.assertEqual(by_regex, by_lexer)


class TestLanguageIdentification(unittest.TestCase):
    def test_pidgin_dominant_utterance(self):
        result = profile(LEXER.tokenize("A don chop di rais for haus"))
        self.assertIs(result.dominant, Lang.PIDGIN)

    def test_mixture_label_mentions_more_than_one_language(self):
        result = profile(LEXER.tokenize("Mola, le pays est dur, a no get moni"))
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
        result = PARSER.parse(LEXER.tokenize("for for for di"))
        self.assertFalse(result.accepted)
        self.assertTrue(result.expected)
        self.assertIn("syntax error", result.error)

    def test_parse_tree_is_built_for_accepted_input(self):
        result = PARSER.parse(LEXER.tokenize("A don chop."))
        self.assertTrue(result.accepted)
        self.assertEqual(result.tree.symbol, GRAMMAR.start)
        self.assertTrue(result.tree.children)

    def test_trace_is_recorded(self):
        result = PARSER.parse(LEXER.tokenize("A don chop."))
        self.assertTrue(result.trace)
        self.assertEqual(result.trace[-1].action, "accept")


class TestTranslation(unittest.TestCase):
    def test_single_word_lookup_lists_every_reading(self):
        readings = TRANSLATOR.translate_word("chop")
        self.assertTrue(any("eat" in r[2] for r in readings))

    def test_tense_mood_aspect_markers(self):
        self.assertEqual(english("A don chop."), "I have eaten.")
        self.assertEqual(english("A go chop."), "I will eat.")
        self.assertEqual(english("A bin chop."), "I ate.")
        self.assertEqual(english("A di chop."), "I am eating.")
        self.assertEqual(english("A fit chop."), "I can eat.")

    def test_negation_uses_do_support(self):
        self.assertEqual(english("A no chop."), "I do not eat.")

    def test_zero_copula_is_filled_in(self):
        self.assertEqual(english("Di moto fain."), "The motorcycle is beautiful.")

    def test_plural_marker_becomes_an_english_plural(self):
        self.assertIn("children", english("Di pikin dem dei for haus."))

    def test_hortative_make(self):
        self.assertEqual(english("Make wi go maket."), "Let us go to the market.")

    def test_yes_no_question_gets_do_support(self):
        self.assertTrue(english("Yu sabi di tori?").startswith("Do you"))

    def test_french_camfranglais_mixture(self):
        self.assertIn("times are hard", english("Le pays est dur oh!").lower())

    def test_english_insertions_pass_through(self):
        self.assertIn("download", english("A no fit download notin."))

    def test_double_negative_is_resolved(self):
        self.assertIn("anything", english("A no fit download notin."))

    def test_every_corpus_sentence_produces_output(self):
        for text in read_corpus(CORPUS_FILE):
            with self.subTest(text):
                self.assertTrue(english(text).strip())


class TestQuestions(unittest.TestCase):
    def test_wh_question_with_an_explicit_subject_inverts(self):
        self.assertEqual(english("Wetin yu di chop?"), "What are you eating?")
        self.assertEqual(english("Wusai yu dei?"), "Where are you?")

    def test_wh_word_as_subject_is_not_inverted(self):
        self.assertEqual(english("Hu na dat?"), "Who is that?")

    def test_yes_no_question_takes_do_support(self):
        self.assertEqual(english("Yu sabi di tori?"), "Do you know the story?")

    def test_modal_question_fronts_the_modal(self):
        self.assertEqual(english("Wuna go kam?"), "Will you come?")


class TestNounPhrases(unittest.TestCase):
    def test_attributive_adjective_does_not_add_a_second_article(self):
        self.assertEqual(english("di big haus"), "The big house.")

    def test_determiner_before_a_noun_that_could_be_a_verb(self):
        self.assertEqual(english("Di lecture don start."), "The lecture has started.")

    def test_object_pronoun_is_recognised(self):
        self.assertEqual(english("Gi mi moni."), "Give me money.")


class TestTrickyReadings(unittest.TestCase):
    def test_stacked_future_and_progressive(self):
        self.assertEqual(english("A go di chop."), "I will be eating.")

    def test_sentence_initial_di_is_the_article(self):
        self.assertEqual(cats("Di courant don go.")[0], Cat.DET)

    def test_di_after_a_pronoun_is_the_progressive_marker(self):
        self.assertEqual(cats("A di chop.")[1], Cat.TMA)

    def test_clause_final_copula_gets_a_complement(self):
        self.assertEqual(english("Taxi no dey."), "The taxi is not there.")

    def test_predicative_adjective_from_a_noun_shaped_gloss(self):
        self.assertEqual(english("A hongri."), "I am hungry.")

    def test_idiomatic_multiword_verb_phrase(self):
        self.assertEqual(english("Kam chop."), "Come and eat.")


class TestFrenchElision(unittest.TestCase):
    def test_elided_clitic_is_split_off(self):
        self.assertEqual(cats("j'ai gauler ma bolo")[:2], [Cat.PRON, Cat.TMA])

    def test_elision_translates(self):
        self.assertEqual(english("Mbom, j'ai gauler ma bolo."), "Guy, I have caught my job.")
        self.assertEqual(english("L'argent don finish."), "The money has finished.")

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

    def test_additions_work_in_a_sentence(self):
        self.assertEqual(english("A don nang for piol."), "I have slept at home.")
        self.assertEqual(english("Mbom, a go bosh tide."), "Guy, I will study today.")


class TestGenerator(unittest.TestCase):
    generator = Generator(GRAMMAR, LEXICON, LEXER, PARSER)

    def test_generated_sentences_parse(self):
        for lang in (None, Lang.PIDGIN, Lang.CAMFRANGLAIS, Lang.FRENCH):
            for _ in range(15):
                text = self.generator.sentence(lang)
                with self.subTest(lang=lang, text=text):
                    self.assertTrue(PARSER.parse(LEXER.tokenize(text)).accepted, text)

    def test_generated_sentences_translate(self):
        for _ in range(15):
            text = self.generator.sentence()
            with self.subTest(text):
                self.assertTrue(english(text).strip())

    def test_requested_language_is_present(self):
        for lang in (Lang.PIDGIN, Lang.CAMFRANGLAIS):
            hits = 0
            for _ in range(15):
                tokens = LEXER.tokenize(self.generator.sentence(lang))
                hits += any(t.lang is lang for t in tokens)
            self.assertGreater(hits, 10, lang)


class TestLanguageFamilies(unittest.TestCase):
    """Pidgin goes with English; Camfranglais goes with French. The two never mix."""

    generator = Generator(GRAMMAR, LEXICON, LEXER, PARSER)

    FORBIDDEN = {
        Lang.PIDGIN: {Lang.CAMFRANGLAIS, Lang.FRENCH},
        Lang.CAMFRANGLAIS: {Lang.PIDGIN},
        Lang.FRENCH: {Lang.PIDGIN},
    }

    def test_generation_stays_inside_one_family(self):
        for lang, banned in self.FORBIDDEN.items():
            for _ in range(20):
                text = self.generator.sentence(lang)
                found = {t.lang for t in LEXER.tokenize(text) if t.cat is not Cat.PUNCT}
                with self.subTest(lang=lang, text=text):
                    self.assertFalse(found & banned, f"{text} -> {found & banned}")

    def test_auto_generation_never_mixes_the_families(self):
        for _ in range(30):
            text = self.generator.sentence()
            found = {t.lang for t in LEXER.tokenize(text) if t.cat is not Cat.PUNCT}
            with self.subTest(text):
                self.assertFalse(
                    Lang.PIDGIN in found and found & {Lang.CAMFRANGLAIS, Lang.FRENCH},
                    text,
                )

    def test_shared_word_follows_the_surrounding_family(self):
        # 'chop' is in both dictionaries; the words around it decide which one.
        pidgin = {t.norm: t.lang for t in LEXER.tokenize("A don chop di rais.")}
        self.assertIs(pidgin["chop"], Lang.PIDGIN)

        camfranglais = {t.norm: t.lang for t in LEXER.tokenize("La chop va tchop.")}
        self.assertIs(camfranglais["chop"], Lang.CAMFRANGLAIS)

    def test_explicit_preference_still_wins(self):
        lexer = Lexer(LEXICON, Lang.CAMFRANGLAIS)
        token = next(t for t in lexer.tokenize("A don chop di rais.") if t.norm == "chop")
        self.assertIs(token.lang, Lang.CAMFRANGLAIS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
