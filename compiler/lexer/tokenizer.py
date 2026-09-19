"""
Tokenizer + token classifier for the Francanglais lexical analyzer.

This is the "custom lexical specification using regular expressions for
token types" required by the CS4110 assignment: TOKEN_SPLIT_RE below is
the regex that segments raw text into tokens, and classify_token()
applies the regex categories from lexicon.TOKEN_REGEX_RULES plus the
lexicon word-lists to tag each token's type.
"""

import re
import unicodedata
from collections import namedtuple
from collections.abc import Mapping

from . import lexicon

Token = namedtuple("Token", ["text", "category"])

# Segments text into tokens. A "word" is letters plus internal
# apostrophes/hyphens (so "j'ai", "n'y", "go-slow" stay single tokens);
# numbers and punctuation are their own token types.
TOKEN_SPLIT_RE = re.compile(
    r"[^\W\d_]+(?:['\u2019-][^\W\d_]+)*|\d+(?:[.,]\d+)?|[.,!?;:\"()]|\S"
)


def tokenize(text: str):
    """Splits raw text into a list of raw string tokens (no classification yet)."""
    # The final non-whitespace alternative preserves unsupported input for UNKNOWN.
    return TOKEN_SPLIT_RE.findall(text)


def normalize_text(text: str) -> str:
    """Normalize matching only, preserving accents and the original stored text."""
    return " ".join(unicodedata.normalize("NFC", text.casefold()).translate(
        str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})
    ).split())


def classify_token(token: str, learned_lexicon: Mapping[str, str] | None = None) -> str:
    """Classifies a single token into one lexical category."""
    lower = token.lower()

    for category, pattern in lexicon.TOKEN_REGEX_RULES:
        if re.match(pattern, token):
            return category

    if learned_lexicon is not None:
        learned = learned_lexicon.get(normalize_text(token))
        if learned in lexicon.TERMINAL_CATEGORIES:
            return learned

    if lower in lexicon.SLANG_WORDS:
        return "SLANG"
    if lower in lexicon.PIDGIN_MARKERS:
        return "PIDGIN_MARKER"
    if lower in lexicon.NOUN_LEXICON:
        return "NOUN"
    if lower in lexicon.VERB_LEXICON:
        return "VERB"
    if lower in lexicon.FRENCH_FUNCTION_WORDS:
        return "FRENCH_FUNCTION_WORD"
    if lower in lexicon.ENGLISH_FUNCTION_WORDS:
        return "ENGLISH_FUNCTION_WORD"

    # Heuristic fallback based on surface morphology, for words not in
    # any lexicon yet — flags a *guess*, not a confirmed classification.
    if lower.endswith(("ing", "ed")):
        return "ENGLISH_VERB_LIKE"
    if lower.endswith(("er", "ir", "re")) and len(lower) > 3:
        return "FRENCH_VERB_LIKE"

    return "UNKNOWN"


def find_verb_phrases(text: str):
    """Returns any known multi-word verb phrases/idioms found in the raw text."""
    lower = text.lower()
    found = []
    for pattern in lexicon.VERB_PHRASES:
        found.extend(m.group(0) for m in re.finditer(pattern, lower))
    return found


# Which single-token categories count as "French" vs "English" vs "Pidgin"
# for the purpose of spotting code-mixed spans within a sentence.
LANGUAGE_MAP = {
    "FRENCH_FUNCTION_WORD": "FR",
    "FRENCH_VERB_LIKE": "FR",
    "ENGLISH_FUNCTION_WORD": "EN",
    "ENGLISH_VERB_LIKE": "EN",
    "PIDGIN_MARKER": "PID",
}


def analyze_sentence(text: str, learned_lexicon: Mapping[str, str] | None = None):
    """
    Tokenizes + classifies a sentence, and flags code-mixed spans
    (adjacent tokens whose inferred language differs) and any known
    verb-phrase idioms.
    """
    raw_tokens = tokenize(text)
    tokens = [Token(t, classify_token(t, learned_lexicon)) for t in raw_tokens]

    code_mixed_spans = []
    prev_lang = None
    prev_token = None
    for tok in tokens:
        lang = LANGUAGE_MAP.get(tok.category)
        if lang is None:
            continue  # skip content/unknown words; don't lose the running language
        if prev_lang is not None and lang != prev_lang:
            code_mixed_spans.append(f"{prev_token} ... {tok.text}")
        prev_lang = lang
        prev_token = tok.text

    return {
        "tokens": tokens,
        "code_mixed_spans": code_mixed_spans,
        "verb_phrases": find_verb_phrases(text),
    }