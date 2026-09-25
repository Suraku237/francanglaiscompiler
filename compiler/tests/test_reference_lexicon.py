import csv
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from compiler.lexer import lexicon, reference, tokenizer
from compiler.lexer.vocabulary import normalize_text
from compiler.parser.service import analyze_grammar, parse_analysis


class ClassifiedLexiconTests(unittest.TestCase):
    def tearDown(self):
        reference.load_classified_lexicon.cache_clear()
        reference.reference_categories.cache_clear()
        reference.reference_languages.cache_clear()
        reference.reference_verb_phrases.cache_clear()
        tokenizer._all_verb_phrases.cache_clear()

    def test_all_878_supplied_rows_and_fields_are_preserved(self):
        with reference.CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
            supplied = list(csv.DictReader(stream))
        entries = reference.load_classified_lexicon()
        self.assertEqual(len(entries), 878)
        self.assertEqual(len(supplied), len(entries))
        self.assertEqual(Counter(entry.section for entry in entries)["Common English"], 362)
        self.assertEqual(Counter(entry.section for entry in entries)["Common French"], 316)
        for original, entry in zip(supplied, entries):
            self.assertEqual({field: getattr(entry, field) for field in reference.CSV_FIELDS}, original)
            self.assertGreater(entry.source_line, 1)
            self.assertTrue(set(entry.categories).issubset(lexicon.TERMINAL_CATEGORIES))

    def test_every_usable_supplied_single_word_is_recognized_without_rewriting_it(self):
        words = {
            alias for entry in reference.load_classified_lexicon() for alias in entry.aliases
            if tokenizer.tokenize(alias) == [alias]
        }
        self.assertEqual(len(words), 811)
        for raw in words:
            with self.subTest(word=raw):
                tokens = tokenizer.analyze_sentence(raw)["tokens"]
                self.assertEqual(len(tokens), 1)
                self.assertEqual(tokens[0].text, raw)
                self.assertNotEqual(tokens[0].category, "UNKNOWN")

    def test_every_existing_explicit_classification_keeps_priority(self):
        rules = (
            ("SLANG", lexicon.SLANG_WORDS), ("PIDGIN_MARKER", lexicon.PIDGIN_MARKERS),
            ("NOUN", lexicon.NOUN_LEXICON), ("VERB", lexicon.VERB_LEXICON),
            ("FRENCH_FUNCTION_WORD", lexicon.FRENCH_FUNCTION_WORDS),
            ("ENGLISH_FUNCTION_WORD", lexicon.ENGLISH_FUNCTION_WORDS),
        )
        expected = {}
        for category, words in rules:
            for word in words:
                expected.setdefault(normalize_text(word), category)
        for word, category in expected.items():
            self.assertEqual(tokenizer.classify_token(word), category, word)
        self.assertEqual(tokenizer.classify_token("go"), "VERB")
        self.assertEqual(tokenizer.classify_token("tchop"), "NOUN")
        self.assertEqual(tokenizer.classify_token("veux"), "VERB")

    def test_reference_adds_real_categories_before_morphological_guesses(self):
        text = "mola shiba kako nang sec souvent other"
        self.assertEqual([token.category for token in tokenizer.analyze_sentence(text)["tokens"]], [
            "NOUN", "VERB", "NOUN", "VERB", "ADJECTIVE", "ADVERB", "ADJECTIVE",
        ])
        tokens = [token._asdict() for token in tokenizer.analyze_sentence("sec souvent")["tokens"]]
        self.assertTrue(parse_analysis(analyze_grammar("S -> ADJECTIVE ADVERB"), tokens)["accepted"])

    def test_aliases_unicode_and_ambiguities_are_explicit(self):
        for word in ("pater", "pasho", "pere", "PASHO"):
            self.assertEqual(tokenizer.classify_token(word), "NOUN")
        for word in ("mbindi", "back", "free"):
            self.assertEqual(tokenizer.classify_token(word), "AMBIGUOUS")
        self.assertEqual(tokenizer.classify_token("mbindi", {"mbindi": "NOUN"}), "NOUN")
        self.assertEqual(tokenizer.classify_token("12", {"12": "VERB"}), "NUMBER")
        self.assertEqual(tokenizer.classify_token("!"), "PUNCTUATION")
        self.assertEqual(tokenizer.classify_token("unlisted-fixture-word"), "UNKNOWN")

    def test_reference_phrases_are_annotations_not_collapsed_tokens(self):
        raw = "JE\tWANDA ! se  lancer"
        result = tokenizer.analyze_sentence(raw)
        self.assertEqual([token.text for token in result["tokens"]], ["JE", "WANDA", "!", "se", "lancer"])
        self.assertEqual(result["verb_phrases"], ["JE\tWANDA", "se  lancer"])
        self.assertEqual(tokenizer.find_slang_phrases(raw), ["JE\tWANDA"])
        self.assertEqual(tokenizer.find_verb_phrases("drop me"), ["drop me"])

    def test_invalid_csv_never_silently_discards_or_invents_rows(self):
        header = ",".join(reference.CSV_FIELDS) + "\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.csv"
            for content in (
                "", header, "word,category\nterm,noun\n",
                header + "word,,meaning,source,topic\n",
                header + "word,noun,meaning,source,topic,extra\n",
                header + "word,unsupported,meaning,source,topic\n",
                header + '"unfinished,noun,meaning,source,topic\n',
            ):
                path.write_text(content, encoding="utf-8")
                reference.load_classified_lexicon.cache_clear()
                with patch.object(reference, "CSV_PATH", path), self.assertRaises((ValueError, csv.Error)):
                    reference.load_classified_lexicon()

    def test_missing_reference_is_an_explicit_io_failure(self):
        reference.load_classified_lexicon.cache_clear()
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(reference, "CSV_PATH", Path(directory) / "missing.csv"), self.assertRaises(FileNotFoundError):
                reference.load_classified_lexicon()
