"""Read-only reference vocabulary; never a source of collected fieldwork."""

import logging
import re
from pathlib import Path

from compiler.lexer.tokenizer import normalize_text

from .collection import CollectionError
from .schemas import DictionaryEntry, DictionaryResponse

logger = logging.getLogger(__name__)
DICTIONARY_DIR = Path(__file__).resolve().parents[1] / "dictionary"
DICTIONARY_PATHS = (
    DICTIONARY_DIR / "camfranglais.md",
    DICTIONARY_DIR / "extra_lexicon.md",
)
HEADER = ["Camfranglais", "English meaning", "Origin"]


def headword_aliases(headword: str) -> list[str]:
    variants: list[str] = []
    for alternative in re.split(r"\s+/\s+", headword):
        variants.append(alternative)
        # The supplied "Na wa (oh)" explicitly includes optional wording.
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


def parse_dictionary(text: str, source_document: str) -> list[DictionaryEntry]:
    entries: list[DictionaryEntry] = []
    topic = ""
    in_table = False
    needs_separator = False
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if needs_separator and not line.startswith("|"):
            raise ValueError(f"{source_document}:{line_number}: missing table separator.")
        if line.startswith("## "):
            topic = line[3:].removeprefix("CAMFRANGLAIS: ").strip()
            in_table = False
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        if not line.endswith("|") or len(cells) != 3:
            raise ValueError(f"{source_document}:{line_number}: expected three table columns.")
        if cells == HEADER:
            if needs_separator:
                raise ValueError(f"{source_document}:{line_number}: missing table separator.")
            needs_separator = True
            in_table = False
            continue
        if needs_separator:
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                raise ValueError(f"{source_document}:{line_number}: invalid table separator.")
            needs_separator = False
            in_table = True
            continue
        if not in_table or not topic or not all(cells):
            raise ValueError(f"{source_document}:{line_number}: incomplete dictionary row.")
        if not re.fullmatch(r"\*\*[^*]+\*\*", cells[0]):
            raise ValueError(f"{source_document}:{line_number}: expected a bold headword.")
        headword = cells[0][2:-2].strip()
        if not headword:
            raise ValueError(f"{source_document}:{line_number}: empty headword.")
        entries.append(DictionaryEntry(
            id=f"dictionary:{source_document}:{line_number}",
            text=headword, aliases=headword_aliases(headword),
            english_gloss=cells[1], origin=cells[2], topic=topic,
            source_document=source_document, source_line=line_number,
        ))
    if needs_separator or not entries:
        raise ValueError(f"{source_document}: no complete vocabulary table was found.")
    return entries


def load_dictionary() -> list[DictionaryEntry]:
    try:
        return [
            entry
            for path in DICTIONARY_PATHS
            for entry in parse_dictionary(path.read_text(encoding="utf-8-sig"), path.name)
        ]
    except (OSError, ValueError) as exc:
        logger.error("Reference dictionary loading failed (%s)", type(exc).__name__)
        raise CollectionError(
            503, "Cannot read the reference dictionary. Check its Markdown files and permissions, then retry."
        ) from exc


def list_dictionary(query: str, offset: int, limit: int) -> DictionaryResponse:
    entries = load_dictionary()
    words = normalize_text(query).split()
    matched = [
        entry for entry in entries
        if all(word in normalize_text(" ".join((
            entry.text, *entry.aliases, entry.english_gloss, entry.origin,
            entry.topic, entry.source_document,
        ))) for word in words)
    ]
    return DictionaryResponse(
        entries=matched[offset:offset + limit], total=len(entries), matched=len(matched),
        offset=offset, limit=limit,
        sources=list(dict.fromkeys(entry.source_document for entry in entries)),
    )
