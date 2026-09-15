"""Token frequency and variation analysis over a corpus.

This backs the *"Analyze token frequency and variation"* component of the project: how
often each token appears, how the vocabulary splits across categories and languages,
how rich the vocabulary is (type/token ratio), and which spellings of the same word are
competing in the data (``tchop``/``chop``, ``njoh``/``ndjoh``).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .lexer import Lexer
from .tokens import Cat, Lang, Token


@dataclass
class FrequencyReport:
    tokens: int = 0
    types: int = 0
    by_token: Counter = field(default_factory=Counter)
    by_category: Counter = field(default_factory=Counter)
    by_language: Counter = field(default_factory=Counter)
    by_section: Counter = field(default_factory=Counter)
    surfaces: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))
    unknown: Counter = field(default_factory=Counter)

    @property
    def type_token_ratio(self) -> float:
        return self.types / self.tokens if self.tokens else 0.0

    @property
    def hapax(self) -> list[str]:
        """Words that occur exactly once - a measure of lexical churn."""
        return sorted(t for t, n in self.by_token.items() if n == 1)

    def spelling_variation(self) -> dict[str, list[str]]:
        """Normalised forms written more than one way in the data."""
        return {
            norm: sorted(forms)
            for norm, forms in self.surfaces.items()
            if len(forms) > 1
        }

    def most_common(self, n: int = 20) -> list[tuple[str, int]]:
        return self.by_token.most_common(n)


def analyse_tokens(tokens: list[Token], report: FrequencyReport | None = None) -> FrequencyReport:
    report = report or FrequencyReport()
    for tok in tokens:
        if tok.cat is Cat.PUNCT:
            continue
        report.tokens += 1
        report.by_token[tok.norm] += 1
        report.by_category[tok.cat.value] += 1
        report.by_language[tok.lang.value] += 1
        if tok.section:
            report.by_section[tok.section] += 1
        report.surfaces[tok.norm][tok.surface] += 1
        if tok.lang is Lang.UNKNOWN:
            report.unknown[tok.norm] += 1
    report.types = len(report.by_token)
    return report


def analyse_corpus(lines: list[str], lexer: Lexer | None = None) -> FrequencyReport:
    lexer = lexer or Lexer()
    report = FrequencyReport()
    for line in lines:
        analyse_tokens(lexer.tokenize(line), report)
    report.types = len(report.by_token)
    return report
