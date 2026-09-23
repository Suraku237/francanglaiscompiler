import csv
import logging
import sqlite3
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TypeVar
from uuid import uuid4

from filelock import Timeout

from compiler.lexer.tokenizer import normalize_text
from data_collector import dataset

from .ownership import record_ownership, require_owner
from .schemas import DatasetEntry, DatasetEntryView, DatasetResponse, EntryCreate, EntryPatch, OwnedDatasetEntry

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CollectionError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def storage_operation(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Timeout as exc:
        raise CollectionError(503, "The collection is busy. Please try again.") from exc
    except (OSError, csv.Error, ValueError, sqlite3.Error) as exc:
        logger.error("Collection storage operation failed (%s)", type(exc).__name__)
        raise CollectionError(
            500, "Cannot read or save the collection. Check the server storage and permissions."
        ) from exc


def list_entries(query: str) -> DatasetResponse:
    entries = dataset.load_all()
    search = query.strip().casefold()
    matches = [
        entry for entry in entries
        if not search or any(search in value.casefold() for value in entry.values())
    ]
    return DatasetResponse(
        entries=[entry_view(DatasetEntry.model_validate(entry)) for entry in reversed(matches)],
        total=len(entries),
        by_category=dict(Counter(entry["category"] or "(none)" for entry in entries)),
        by_type=dict(Counter(entry["entry_type"] or "(none)" for entry in entries)),
        by_review_status={
            status: sum(entry["review_status"] == status for entry in entries)
            for status in ("approved", "unreviewed")
        },
    )


def entry_view(entry: DatasetEntry) -> DatasetEntryView:
    ownership = record_ownership("entry", entry.id)
    return OwnedDatasetEntry(**entry.model_dump(), ownership=ownership) if ownership is not None else entry


def _check_duplicate(
    entries: list[dict[str, str]], text: str, language: str, exclude_id: str = ""
) -> None:
    if any(
        entry["id"] != exclude_id and entry["language"] == language
        and normalize_text(entry["text"]) == normalize_text(text)
        for entry in entries
    ):
        raise CollectionError(409, "This text is already in the collection for the selected language.")


def create_entry(request: EntryCreate, *, audio_filename: str = "") -> DatasetEntryView:
    if request.category not in (*dataset.BUSINESS_CATEGORIES, *dataset.CATEGORIES):
        raise CollectionError(422, "Select one of the available collection categories.")
    with dataset.dataset_lock():
        entries = dataset.load_all()
        _check_duplicate(entries, request.text, request.language)
        entry = DatasetEntry(
            **request.model_dump(),
            id=str(uuid4()),
            audio_filename=audio_filename,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        dataset.append_entry(entry.model_dump())
        return entry_view(entry)


def edit_entry(
    entry_id: str, request: EntryPatch, *, audio_filename: str | None = None,
) -> DatasetEntryView:
    with dataset.dataset_lock():
        entries = dataset.load_all()
        entry = next((item for item in entries if item["id"] == entry_id), None)
        if entry is None:
            raise CollectionError(404, "This collection entry no longer exists.")
        require_owner("entry", entry_id)
        if request.entry_type is not None and request.entry_type not in (*dataset.ENTRY_TYPES, entry["entry_type"]):
            raise CollectionError(422, "Select one of the available collection entry types.")
        if request.category is not None and request.category not in (
            *dataset.BUSINESS_CATEGORIES, *dataset.CATEGORIES, entry["category"],
        ):
            raise CollectionError(422, "Select one of the available collection categories.")
        text = request.text if request.text is not None else entry["text"]
        language = request.language if request.language is not None else entry["language"]
        if normalize_text(text) != normalize_text(entry["text"]) or language != entry["language"]:
            _check_duplicate(entries, text, language, entry_id)
        changes = request.model_dump(exclude_unset=True)
        if audio_filename is not None:
            changes["audio_filename"] = audio_filename
        dataset.apply_entry_update(entry, changes)
        dataset.save_all(entries)
        return entry_view(DatasetEntry.model_validate(entry))


def remove_entry(entry_id: str) -> None:
    with dataset.dataset_lock():
        entries = dataset.load_all()
        remaining = [entry for entry in entries if entry["id"] != entry_id]
        if len(remaining) == len(entries):
            raise CollectionError(404, "This collection entry no longer exists.")
        require_owner("entry", entry_id)
        dataset.save_all(remaining)
