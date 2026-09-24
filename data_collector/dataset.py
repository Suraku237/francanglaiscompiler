"""
Shared CSV storage for the desktop collector, Python API and lexer.
"""

import os
import csv
import tempfile
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from threading import Lock
from typing import Optional, Protocol

from filelock import FileLock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
DATASET_PATH = os.path.join(BASE_DIR, "dataset.csv")

FIELDNAMES = [
    "id",
    "text",
    "entry_type",       # word | phrase | sentence
    "french_gloss",
    "english_gloss",
    "category",         # matches CS4110 assignment topics
    "source_location",  # e.g. "taxi, Mvan" / "Marché Mokolo" / "ICT campus"
    "notes",
    "audio_filename",   # empty if no source recording is attached
    "contributor",      # name(s) of group member(s) who collected this
    "timestamp",
    "language",
    "review_status",
    "lexical_category",
]
PRE_REVIEW_FIELDNAMES = FIELDNAMES[:-3]
LEGACY_FIELDNAMES = [field for field in PRE_REVIEW_FIELDNAMES if field != "source_location"]
DATASET_LANGUAGES = ["francanglais", "pidgin", "mixed", "unspecified"]
# Keep the standalone desktop storage usable without importing the compiler package.
LEXICAL_CATEGORIES = [
    "NUMBER", "PUNCTUATION", "SLANG", "PIDGIN_MARKER", "NOUN", "VERB",
    "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD",
    "ADJECTIVE", "ADVERB", "INTERJECTION", "PRONOUN", "PREPOSITION",
    "CONJUNCTION", "DETERMINER", "PARTICLE", "AMBIGUOUS",
    "ENGLISH_VERB_LIKE", "FRENCH_VERB_LIKE", "UNKNOWN",
]

# The 10 topics required by the CS4110 assignment
# ("Lexical and Syntactic Analysis of Informal Urban Communication in Yaoundé")
CATEGORIES = [
    "Taxi / Commuting", "Internet Connectivity", "Electricity Supply",
    "Market Bargaining", "Rainy Season", "Fuel Scarcity",
    "Roadside Business", "Bendskin Communication", "Security Checkpoint",
    "Campus Life", "Other",
]

BUSINESS_CATEGORIES = [
    "Customer Service", "Sales", "Marketing", "Operations", "Logistics",
    "Finance", "Human Resources", "Product & Technical", "Legal & Compliance",
    "General Communication", "Other",
]

ENTRY_TYPES = ["Word", "Phrase", "Sentence"]

_LOCKS: dict[str, FileLock] = {}
_LOCKS_GUARD = Lock()


class DatasetStorage(Protocol):
    audio_dir: Path

    def lock(self) -> FileLock: ...
    def ensure(self) -> None: ...
    def load_all(self) -> list[dict[str, str]]: ...
    def save_all(self, entries: list[dict[str, str]]) -> None: ...
    def append_entry(self, entry: dict[str, str]) -> None: ...
    def check_audio_capacity(self, additional: int) -> None: ...


_storage: ContextVar[DatasetStorage | None] = ContextVar("dataset_storage", default=None)


@contextmanager
def use_storage(storage: DatasetStorage) -> Iterator[None]:
    token = _storage.set(storage)
    try:
        yield
    finally:
        _storage.reset(token)


def audio_directory() -> Path:
    storage = _storage.get()
    return storage.audio_dir if storage is not None else Path(AUDIO_DIR)


def check_audio_capacity(additional: int) -> None:
    storage = _storage.get()
    if storage is not None:
        storage.check_audio_capacity(additional)


class EntryNotFoundError(LookupError):
    """An entry was removed before an update or delete could be committed."""


def dataset_lock() -> FileLock:
    """Use the same reentrant, cross-process lock for a complete transaction."""
    storage = _storage.get()
    if storage is not None:
        return storage.lock()
    with _LOCKS_GUARD:
        if DATASET_PATH not in _LOCKS:
            _LOCKS[DATASET_PATH] = FileLock(DATASET_PATH + ".lock", timeout=10)
        return _LOCKS[DATASET_PATH]


def _write_entries(entries: list[dict[str, str]]) -> None:
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8",
            dir=os.path.dirname(DATASET_PATH), prefix=".dataset-", suffix=".tmp", delete=False,
        ) as f:
            temporary_path = f.name
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(normalize_entry(entry) for entry in entries)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_path, DATASET_PATH)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.remove(temporary_path)


def ensure_dataset_file() -> None:
    storage = _storage.get()
    if storage is not None:
        storage.ensure()
        return
    with dataset_lock():
        os.makedirs(AUDIO_DIR, exist_ok=True)
        if not os.path.exists(DATASET_PATH):
            _write_entries([])


def normalize_entry(entry: dict[str, str]) -> dict[str, str]:
    """Upgrade legacy metadata without changing collected text or provenance."""
    normalized = dict(entry)
    normalized.setdefault("source_location", "")
    if normalized.get("language") not in DATASET_LANGUAGES:
        normalized["language"] = "unspecified"
    if normalized.get("review_status") not in ("unreviewed", "approved"):
        normalized["review_status"] = "unreviewed"
    if normalized.get("lexical_category") not in LEXICAL_CATEGORIES:
        normalized["lexical_category"] = ""
    return normalized


def load_all() -> list[dict[str, str]]:
    storage = _storage.get()
    if storage is not None:
        return storage.load_all()
    with dataset_lock():
        ensure_dataset_file()
        with open(DATASET_PATH, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames not in (FIELDNAMES, PRE_REVIEW_FIELDNAMES, LEGACY_FIELDNAMES):
                raise ValueError("Dataset CSV header does not match the expected fields.")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("Dataset CSV contains an incomplete or malformed row.")
            return [normalize_entry(row) for row in rows]


def append_entry(entry: dict) -> None:
    storage = _storage.get()
    if storage is not None:
        storage.append_entry(entry)
        return
    with dataset_lock():
        entries = load_all()
        entries.append(entry)
        _write_entries(entries)


def save_all(entries) -> None:
    """Overwrite the whole dataset file. Used after an edit or delete."""
    storage = _storage.get()
    if storage is not None:
        storage.save_all(entries)
        return
    with dataset_lock():
        ensure_dataset_file()
        _write_entries(entries)


def apply_entry_update(entry: dict[str, str], updated_fields: dict[str, str]) -> None:
    """Changed evidence needs review unless this edit explicitly approves it."""
    changed = any(entry.get(key) != value for key, value in updated_fields.items() if key != "review_status")
    entry.update(updated_fields)
    if changed and "review_status" not in updated_fields:
        entry["review_status"] = "unreviewed"


def update_entry(entry_id: str, updated_fields: dict[str, str]) -> None:
    """Update under the CSV lock; raise EntryNotFoundError for a stale ID."""
    with dataset_lock():
        entries = load_all()
        for e in entries:
            if e["id"] == entry_id:
                apply_entry_update(e, updated_fields)
                break
        else:
            raise EntryNotFoundError("This collection entry no longer exists.")
        save_all(entries)


def delete_entry(entry_id: str) -> None:
    """Delete under the CSV lock; raise EntryNotFoundError for a stale ID."""
    with dataset_lock():
        entries = load_all()
        remaining = [e for e in entries if e["id"] != entry_id]
        if len(remaining) == len(entries):
            raise EntryNotFoundError("This collection entry no longer exists.")
        save_all(remaining)


def text_exists(text: str, exclude_id: Optional[str] = None, language: str = "unspecified") -> bool:
    """Check duplicate text within a language; legacy desktop entries are unspecified."""
    def normalized(value: str) -> str:
        return " ".join(unicodedata.normalize("NFC", value.casefold()).translate(
            str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"})
        ).split())

    norm = normalized(text)
    if not norm:
        return False
    for e in load_all():
        if exclude_id is not None and e["id"] == exclude_id:
            continue
        if e["language"] == language and normalized(e["text"]) == norm:
            return True
    return False


def count_by(field: str) -> dict:
    counts = {}
    for e in load_all():
        key = e.get(field) or "(none)"
        counts[key] = counts.get(key, 0) + 1
    return counts


def total_count() -> int:
    return len(load_all())