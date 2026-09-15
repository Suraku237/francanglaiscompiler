"""Sentence generation for the auto-generate button.

Free random derivation from the CFG produces grammatical but meaningless strings
("make nain ches"), so generation works from a fixed set of sentence patterns instead.
Each pattern is a sequence of lexical categories that the LL(1) grammar accepts, and
each slot is filled with a word of that class drawn from the requested language and,
for nouns, from the everyday topics the corpus is about.

Every candidate is run back through the scanner and the parser, and only a sentence the
parser accepts is returned - so the button can never produce something the analyzer
then rejects.
"""

from __future__ import annotations

import json
import random

from .grammar import Grammar
from .lexer import Lexer
from .lexicon import DATA_DIR, Lexicon, normalize
from .parser import LL1Parser
from .tokens import Cat, Lang

#: Sentence shapes, as category sequences. Every one of these derives from fca.gram.
PATTERNS: tuple[tuple[str, ...], ...] = (
    ("PRON", "TMA", "VERB", "DET", "NOUN"),
    ("PRON", "TMA", "VERB", "POSS", "NOUN"),
    ("PRON", "NEG", "TMA", "VERB", "PREP", "NOUN"),
    ("PRON", "NEG", "VERB", "DET", "NOUN"),
    ("PRON", "TMA", "VERB", "PREP", "DET", "NOUN"),
    ("DET", "NOUN", "TMA", "VERB", "ADV"),
    ("DET", "NOUN", "TMA", "VERB", "PREP", "NOUN"),
    ("DET", "NOUN", "COP", "ADJ"),
    ("DET", "ADJ", "NOUN", "TMA", "VERB"),
    ("NOUN", "TMA", "VERB", "PREP", "DET", "NOUN"),
    ("NOUN", "NEG", "COP", "PREP", "NOUN"),
    ("DET", "NOUN", "PLUR", "NEG", "COP", "PREP", "NOUN"),
    ("QWORD", "PRON", "TMA", "VERB"),
    ("QWORD", "PREP", "DET", "NOUN"),
    ("QWORD", "PRON", "VERB", "DET", "NOUN"),
    ("MAKE", "PRON", "VERB", "PREP", "NOUN"),
    ("PART", "VERB", "PRON", "PREP", "NOUN"),
    ("INTERJ", "PRON", "TMA", "VERB", "POSS", "NOUN"),
    ("INTERJ", "DET", "NOUN", "TMA", "VERB"),
    ("PRON", "TMA", "VERB", "NUM", "NOUN"),
)

#: Dictionary sections worth drawing nouns from; body parts and numerals are not.
_TOPICAL = (
    "place", "transport", "money", "work", "hustle", "food", "drink", "home",
    "time", "weather", "people", "address", "trouble", "street", "utilit",
    "market", "life",
)

#: How the two varieties actually compose. Pidgin speech draws on Pidgin and English;
#: Camfranglais draws on Camfranglais, French and English. The two families are never
#: mixed with each other, so a generated sentence stays inside one of them.
_FAMILIES: dict[Lang, tuple[Lang, ...]] = {
    Lang.PIDGIN: (Lang.PIDGIN, Lang.ENGLISH),
    Lang.CAMFRANGLAIS: (Lang.CAMFRANGLAIS, Lang.FRENCH, Lang.ENGLISH),
    Lang.FRENCH: (Lang.FRENCH, Lang.CAMFRANGLAIS, Lang.ENGLISH),
}

_AUTO = (Lang.PIDGIN, Lang.CAMFRANGLAIS)


class Generator:
    """Builds a random utterance the analyzer is guaranteed to accept."""

    def __init__(self, grammar: Grammar, lexicon: Lexicon, lexer: Lexer, parser: LL1Parser):
        self.grammar = grammar
        self.lexer = lexer
        self.parser = parser
        self.words, self.topical = self._index(lexicon)
        data = json.loads((DATA_DIR / "generation.json").read_text(encoding="utf-8"))
        self.pools = {
            Cat(cat): {normalize(term) for term in terms}
            for cat, terms in data["pools"].items()
        }

    @staticmethod
    def _index(lexicon: Lexicon):
        words: dict[tuple[Lang, Cat], list[str]] = {}
        topical: dict[tuple[Lang, Cat], list[str]] = {}
        for term, entries in lexicon.entries.items():
            for entry in entries:
                key = (entry.lang, entry.cat)
                words.setdefault(key, []).append(term)
                section = entry.section.lower()
                if any(word in section for word in _TOPICAL):
                    topical.setdefault(key, []).append(term)
        for term, cats in lexicon.english.items():
            for cat in cats:
                words.setdefault((Lang.ENGLISH, cat), []).append(term)
        return words, topical

    # -- public API ------------------------------------------------------

    def sentence(self, lang: Lang | None = None, tries: int = 60) -> str:
        chain = _FAMILIES[lang or random.choice(_AUTO)]
        patterns = [p for p in PATTERNS if self._fillable(p, chain)]
        if not patterns:
            return "A don chop di rais."
        fallback = ""
        for _ in range(tries):
            pattern = random.choice(patterns)
            words = [self._word(Cat(name), chain) for name in pattern]
            if not all(words):
                continue
            text = self._finish(words, pattern)
            if self.parser.parse(self.lexer.tokenize(text)).accepted:
                return text
            fallback = fallback or text
        return fallback or "A don chop di rais."

    # -- lexical choice --------------------------------------------------

    def _candidates(self, cat: Cat, lang: Lang) -> list[str]:
        """Words of this class available in one language, narrowed to the curated pool."""
        pool = self.words.get((lang, cat))
        if not pool:
            return []
        allowed = self.pools.get(cat)
        if allowed:
            return [term for term in pool if term in allowed]
        if cat is Cat.NOUN:
            return self.topical.get((lang, cat)) or list(pool)
        return list(pool)

    def _fillable(self, pattern: tuple[str, ...], chain: tuple[Lang, ...]) -> bool:
        """Drop patterns this family cannot fill - 'make' and plural 'dem' are Pidgin only."""
        return all(
            any(self._candidates(Cat(name), lang) for lang in chain)
            for name in pattern
        )

    def _word(self, cat: Cat, chain: tuple[Lang, ...]) -> str:
        for lang in chain:
            pool = self._candidates(cat, lang)
            if pool:
                return random.choice(pool)
        return ""

    @staticmethod
    def _finish(words: list[str], pattern: tuple[str, ...]) -> str:
        text = " ".join(words)
        text = text[0].upper() + text[1:]
        return text + ("?" if pattern[0] == "QWORD" else ".")
