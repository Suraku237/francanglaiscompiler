import re
import unicodedata

_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})


def normalize_word(text: str) -> str:
    if text.isascii():
        return text.lower()
    return unicodedata.normalize("NFC", text.casefold()).translate(_APOSTROPHES)


def normalize_text(text: str) -> str:
    """Normalize matching only; never rewrite a stored source sentence."""
    return " ".join(normalize_word(text).split())


def headword_aliases(headword: str) -> list[str]:
    variants = []
    for alternative in re.split(r"\s+/\s+", headword):
        variants.append(alternative)
        optional = re.fullmatch(r"(.+?)\s+\(([^()]+)\)", alternative)
        if optional:
            variants.extend((optional[1], f"{optional[1]} {optional[2]}"))
    variants.extend(word.rstrip("!?") for word in tuple(variants))
    unique: dict[str, str] = {}
    for variant in variants:
        if not variant.strip():
            raise ValueError("A dictionary headword contains an empty alternative.")
        unique.setdefault(normalize_text(variant), variant)
    return list(unique.values())
