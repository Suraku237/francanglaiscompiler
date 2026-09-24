"""Reviewed Collection annotations, separate from the bundled reference lexicon."""

from collections import defaultdict
from collections.abc import Iterable

from .lexicon import TERMINAL_CATEGORIES
from .tokenizer import normalize_text, tokenize


def build_lexicon(entries: Iterable[dict[str, str]]) -> dict[str, str]:
    categories: dict[str, set[str]] = defaultdict(set)
    for entry in entries:
        if (
            entry.get("review_status") != "approved"
            or entry.get("language") not in ("francanglais", "pidgin")
            or entry.get("entry_type", "").casefold() != "word"
            or entry.get("lexical_category") not in TERMINAL_CATEGORIES
        ):
            continue
        word = normalize_text(entry.get("text", ""))
        if word and tokenize(word) == [word]:
            categories[word].add(entry["lexical_category"])
    # Conflicting reviewed annotations do not silently choose a winner.
    return {word: next(iter(values)) for word, values in categories.items() if len(values) == 1}
