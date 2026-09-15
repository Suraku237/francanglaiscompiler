"""Token and category definitions shared by the lexer, parser and translator."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Lang(str, Enum):
    """Source language a token was recognised from."""

    PIDGIN = "PIDGIN"
    CAMFRANGLAIS = "CAMFRANGLAIS"
    FRENCH = "FRENCH"
    ENGLISH = "ENGLISH"
    PUNCT = "PUNCT"
    UNKNOWN = "UNKNOWN"


class Cat(str, Enum):
    """Grammatical category. These are the terminals of the CFG."""

    PRON = "PRON"
    POSS = "POSS"
    DET = "DET"
    NOUN = "NOUN"
    NUM = "NUM"
    ADJ = "ADJ"
    ADV = "ADV"
    VERB = "VERB"
    COP = "COP"
    TMA = "TMA"
    NEG = "NEG"
    PREP = "PREP"
    CONJ = "CONJ"
    QWORD = "QWORD"
    PART = "PART"
    INTERJ = "INTERJ"
    MAKE = "MAKE"
    PLUR = "PLUR"
    PUNCT = "PUNCT"
    UNKNOWN = "UNKNOWN"


#: Categories that may open a noun phrase.
NOMINAL_OPENERS = {Cat.PRON, Cat.POSS, Cat.DET, Cat.NOUN, Cat.NUM, Cat.ADJ}

#: End-of-input marker used by the parser.
EOF = "$"


@dataclass
class Token:
    """A single lexical unit produced by the scanner."""

    surface: str
    norm: str
    cat: Cat = Cat.UNKNOWN
    lang: Lang = Lang.UNKNOWN
    gloss: str = ""
    line: int = 1
    col: int = 1
    index: int = 0
    words: int = 1
    candidates: tuple = field(default_factory=tuple)
    langs: tuple = field(default_factory=tuple)
    section: str = ""
    origin: str = ""
    guessed: bool = False

    @property
    def is_multiword(self) -> bool:
        return self.words > 1

    @property
    def known(self) -> bool:
        return self.lang is not Lang.UNKNOWN

    def __str__(self) -> str:  # pragma: no cover - display helper
        return f"<{self.cat.value} {self.surface!r} {self.lang.value}>"
