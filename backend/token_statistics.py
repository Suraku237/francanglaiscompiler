import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping


def normalize_token(raw: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", raw.casefold())
        if not unicodedata.combining(character)
    ).replace("\u2019", "'")


def token_statistics(tokens: Iterable[Mapping[str, str]]) -> dict:
    frequencies: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    unknown: Counter[str] = Counter()
    variants: dict[str, Counter[str]] = defaultdict(Counter)
    for token in tokens:
        raw = token["text"]
        frequencies[raw.casefold()] += 1
        categories[token["category"]] += 1
        if token["category"] == "UNKNOWN":
            unknown[raw.casefold()] += 1
        variants[normalize_token(raw)][raw] += 1
    return {
        "frequencies": [{"token": token, "count": count} for token, count in frequencies.most_common()],
        "category_counts": dict(categories),
        "variations": [
            {"normalized": normalized, "forms": [{"text": text, "count": count} for text, count in forms.items()]}
            for normalized, forms in sorted(variants.items()) if len(forms) > 1
        ],
        "unknown_tokens": [{"token": token, "count": count} for token, count in unknown.most_common()],
        "total_tokens": sum(frequencies.values()),
    }
