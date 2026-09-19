"""Supplied constructed practice material, never collected research data."""

import csv
import logging
from pathlib import Path

from compiler.lexer.tokenizer import normalize_text

from .collection import CollectionError
from .schemas import PracticeEntry, PracticeResponse

logger = logging.getLogger(__name__)
EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "examples" / "camfranglais_statements.csv"
FIELDS = [
    "id", "text", "entry_type", "french_gloss", "english_gloss", "category", "notes",
    "audio_filename", "contributor", "timestamp",
]


def load_examples() -> list[PracticeEntry]:
    try:
        entries = []
        identifiers = set()
        with EXAMPLES_PATH.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, strict=True)
            if reader.fieldnames != FIELDS:
                raise ValueError("Unexpected practice CSV header.")
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Incomplete practice CSV row.")
                if not row["id"] or row["id"] in identifiers:
                    raise ValueError("Missing or duplicate practice identifier.")
                if row["entry_type"] != "statement" or not row["notes"].startswith("Constructed example"):
                    raise ValueError("The practice library accepts explicitly constructed statements only.")
                if not row["text"].strip() or not row["french_gloss"].strip() or not row["english_gloss"].strip():
                    raise ValueError("Practice statements need text and both supplied meanings.")
                identifiers.add(row["id"])
                entries.append(PracticeEntry(
                    id=f"examples:{EXAMPLES_PATH.name}:{row['id']}",
                    text=row["text"], french_gloss=row["french_gloss"], english_gloss=row["english_gloss"],
                    topic=row["category"], notes=row["notes"],
                    source_document=EXAMPLES_PATH.name, source_line=reader.line_num,
                ))
        if not entries:
            raise ValueError("The practice source has no statements.")
        return entries
    except (OSError, ValueError, csv.Error) as exc:
        logger.error("Constructed practice source could not be loaded (%s)", type(exc).__name__)
        raise CollectionError(
            503, "Cannot read the practice examples. Check the supplied CSV and its permissions, then retry."
        ) from exc


def list_examples(query: str, offset: int, limit: int) -> PracticeResponse:
    entries = load_examples()
    words = normalize_text(query).split()
    matches = [
        entry for entry in entries
        if all(word in normalize_text(" ".join((
            entry.text, entry.french_gloss, entry.english_gloss, entry.topic,
        ))) for word in words)
    ]
    return PracticeResponse(
        entries=matches[offset:offset + limit], total=len(entries), matched=len(matches),
        offset=offset, limit=limit, sources=[EXAMPLES_PATH.name],
    )
