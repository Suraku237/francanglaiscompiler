"""
Token frequency and variation analysis across the whole dataset.
"""

from collections import Counter
from collections.abc import Iterable

from .tokenizer import Token


def compute_frequencies(all_tokens: Iterable[Token]) -> tuple[Counter[str], Counter[str]]:
    """Count raw spellings (lowercased) and categories, including one-shot inputs."""
    tokens = tuple(all_tokens)
    by_text = Counter(t.text.lower() for t in tokens)
    by_category = Counter(t.category for t in tokens)
    return by_text, by_category


def variation_report(by_text: Counter, top_n: int = 20):
    """Returns the top_n most frequent tokens as (text, count) pairs."""
    return by_text.most_common(top_n)