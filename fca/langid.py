"""Language-mixture detection over a tokenised utterance.

Every token already carries the language it was recognised from, so identifying the
mixture is a counting problem. What matters for the report is the distinction between
tokens that belong to exactly one language and tokens that several dictionaries share
(``chop``, ``wahala``, ``moto``), since the second group is precisely what makes
Yaoundé speech hard to classify.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .tokens import Cat, Lang, Token

_LABELS = {
    Lang.CAMFRANGLAIS: "Camfranglais",
    Lang.FRENCH: "French",
    Lang.ENGLISH: "English",
    Lang.UNKNOWN: "unrecognised",
}


@dataclass
class LanguageProfile:
    counts: Counter = field(default_factory=Counter)
    shared: int = 0
    total: int = 0

    @property
    def percentages(self) -> dict[Lang, float]:
        if not self.total:
            return {}
        return {lang: 100.0 * n / self.total for lang, n in self.counts.items()}

    @property
    def dominant(self) -> Lang:
        ranked = [
            (n, lang) for lang, n in self.counts.items() if lang is not Lang.UNKNOWN
        ]
        return max(ranked)[1] if ranked else Lang.UNKNOWN

    @property
    def present(self) -> list[Lang]:
        order = (Lang.CAMFRANGLAIS, Lang.FRENCH, Lang.ENGLISH)
        return [lang for lang in order if self.counts.get(lang)]

    @property
    def label(self) -> str:
        """A short human description such as ``Camfranglais matrix with French insertions``."""
        found = self.present
        if not found:
            return "unrecognised"
        if len(found) == 1:
            return _LABELS[found[0]]
        head = _LABELS[self.dominant]
        rest = [_LABELS[lang] for lang in found if lang is not self.dominant]
        joined = rest[0] if len(rest) == 1 else ", ".join(rest[:-1]) + " and " + rest[-1]
        return f"{head} matrix with {joined} insertions"

    @property
    def unknown_rate(self) -> float:
        return 100.0 * self.counts.get(Lang.UNKNOWN, 0) / self.total if self.total else 0.0

    def summary(self) -> str:
        parts = [
            f"{_LABELS[lang]} {pct:.0f}%"
            for lang, pct in sorted(
                self.percentages.items(), key=lambda kv: -kv[1]
            )
        ]
        return f"{self.label}  ({', '.join(parts)}; {self.shared} shared token(s))"


def profile(tokens: list[Token]) -> LanguageProfile:
    """Count the languages present in a token stream."""
    result = LanguageProfile()
    for tok in tokens:
        if tok.cat is Cat.PUNCT:
            continue
        result.total += 1
        result.counts[tok.lang] += 1
        if len(set(tok.langs)) > 1:
            result.shared += 1
    return result


def describe(tokens: list[Token]) -> str:
    return profile(tokens).summary()
