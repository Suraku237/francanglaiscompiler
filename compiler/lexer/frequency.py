"""
Token frequency and variation analysis across the whole dataset.
"""

from collections import Counter


def compute_frequencies(all_tokens):
    """all_tokens: list of Token(text, category) across every collected sentence."""
    by_text = Counter(t.text.lower() for t in all_tokens)
    by_category = Counter(t.category for t in all_tokens)
    return by_text, by_category


def variation_report(by_text: Counter, top_n: int = 20):
    """Returns the top_n most frequent tokens as (text, count) pairs."""
    return by_text.most_common(top_n)