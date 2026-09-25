"""Conservative language-transition candidates, separate from token categories."""

from . import lexicon
from .reference import reference_languages
from .vocabulary import normalize_word

_CATEGORY_LANGUAGES = {
    "FRENCH_FUNCTION_WORD": "FR", "FRENCH_VERB_LIKE": "FR",
    "ENGLISH_FUNCTION_WORD": "EN", "ENGLISH_VERB_LIKE": "EN",
    "PIDGIN_MARKER": "PID",
}


def word_languages(text: str, category: str) -> frozenset[str]:
    if category in {"UNKNOWN", "NUMBER", "PUNCTUATION"}:
        return frozenset()
    word = normalize_word(text)
    candidates = {
        language for language, words in lexicon.LANGUAGE_WORDS.items() if word in words
    }
    candidates.update(reference_languages().get(word, ()))
    if not candidates:
        language = _CATEGORY_LANGUAGES.get(category)
        if language is not None:
            candidates.add(language)
    return frozenset(candidates)
