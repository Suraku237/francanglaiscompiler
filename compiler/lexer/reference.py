"""Bundled classified vocabulary, used after the existing explicit lexer rules."""

import csv
import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal

from .vocabulary import headword_aliases, normalize_text

CSV_PATH = Path(__file__).resolve().parents[2] / "dictionary" / "full_lexicon_classified.csv"
CSV_FIELDS = ("word", "part_of_speech", "english_meaning", "origin", "section")
_CONTENT_CATEGORIES = {
    "noun": "NOUN", "proper noun": "NOUN", "verb": "VERB", "verb phrase": "VERB",
    "adjective": "ADJECTIVE", "adverb": "ADVERB", "interjection": "INTERJECTION",
}
_FUNCTION_CATEGORIES = {
    "pronoun": "PRONOUN", "preposition": "PREPOSITION", "conjunction": "CONJUNCTION",
    "determiner": "DETERMINER", "particle": "PARTICLE",
}


@dataclass(frozen=True)
class ReferenceEntry:
    word: str
    part_of_speech: str
    english_meaning: str
    origin: str
    section: str
    source_line: int
    aliases: tuple[str, ...]
    categories: tuple[str, ...]

    @property
    def language(self) -> Literal["fr", "en", "francanglais"]:
        if self.section == "Common French":
            return "fr"
        if self.section == "Common English":
            return "en"
        return "francanglais"


def _categories(part_of_speech: str, origin: str, section: str) -> tuple[str, ...]:
    categories = set()
    for value in part_of_speech.split("/"):
        label = re.sub(r"\s+\([^()]*\)$", "", value.strip()).casefold()
        if label in _CONTENT_CATEGORIES:
            categories.add(_CONTENT_CATEGORIES[label])
        elif label in _FUNCTION_CATEGORIES:
            if section == "Common French" or origin == "French":
                categories.add("FRENCH_FUNCTION_WORD")
            elif section == "Common English" or origin == "English":
                categories.add("ENGLISH_FUNCTION_WORD")
            elif label == "particle" and origin == "Pidgin":
                categories.add("PIDGIN_MARKER")
            else:
                categories.add(_FUNCTION_CATEGORIES[label])
        elif label != "phrase":
            raise ValueError(f"Unsupported reference part of speech: {value!r}")
    return tuple(sorted(categories))


@lru_cache(maxsize=1)
def load_classified_lexicon() -> tuple[ReferenceEntry, ...]:
    entries = []
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(CSV_FIELDS):
            raise ValueError("The classified lexicon must have word, part_of_speech, english_meaning, origin and section columns.")
        for row in reader:
            if set(row) != set(CSV_FIELDS) or any(not isinstance(value, str) or not value.strip() for value in row.values()):
                raise ValueError(f"Classified lexicon row ending at line {reader.line_num} has missing or extra values.")
            entries.append(ReferenceEntry(
                **row, source_line=reader.line_num, aliases=tuple(headword_aliases(row["word"])),
                categories=_categories(row["part_of_speech"], row["origin"], row["section"]),
            ))
    if not entries:
        raise ValueError("The classified lexicon contains no vocabulary rows.")
    return tuple(entries)


@lru_cache(maxsize=1)
def reference_categories() -> Mapping[str, tuple[str, ...]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for entry in load_classified_lexicon():
        for alias in entry.aliases:
            word = normalize_text(alias)
            if " " not in word:
                candidates[word].update(entry.categories)
    return MappingProxyType({word: tuple(sorted(categories)) for word, categories in candidates.items()})


@lru_cache(maxsize=1)
def reference_verb_phrases() -> tuple[str, ...]:
    phrases = {
        normalize_text(alias)
        for entry in load_classified_lexicon() if "VERB" in entry.categories
        for alias in entry.aliases if " " in normalize_text(alias)
    }
    return tuple(r"\s+".join(re.escape(word) for word in phrase.split()) for phrase in sorted(phrases))
