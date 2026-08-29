"""
Dataset read/write helpers for the Francanglais collector.
Kept separate from the GUI so app.py stays focused on presentation.
"""

import os
import csv
from typing import Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(BASE_DIR, "audio")
DATASET_PATH = os.path.join(BASE_DIR, "dataset.csv")

FIELDNAMES = [
    "id",
    "text",
    "entry_type",       # word | phrase | sentence
    "french_gloss",
    "english_gloss",
    "category",
    "notes",
    "audio_filename",   # empty if none
    "contributor",
    "timestamp",
]

CATEGORIES = [
    "greeting", "everyday", "slang", "insult/banter", "market/money",
    "school/campus", "food", "family", "proverb/expression", "other",
]

ENTRY_TYPES = ["word", "phrase", "sentence"]


def ensure_dataset_file():
    os.makedirs(AUDIO_DIR, exist_ok=True)
    if not os.path.exists(DATASET_PATH):
        with open(DATASET_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def load_all():
    ensure_dataset_file()
    with open(DATASET_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append_entry(entry: dict):
    ensure_dataset_file()
    with open(DATASET_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(entry)


def save_all(entries):
    """Overwrite the whole dataset file. Used after an edit or delete."""
    ensure_dataset_file()
    with open(DATASET_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(entries)


def update_entry(entry_id: str, updated_fields: dict):
    entries = load_all()
    for e in entries:
        if e["id"] == entry_id:
            e.update(updated_fields)
            break
    save_all(entries)


def delete_entry(entry_id: str):
    entries = load_all()
    entries = [e for e in entries if e["id"] != entry_id]
    save_all(entries)


def text_exists(text: str, exclude_id: Optional[str] = None) -> bool:
    """Case-insensitive check for a duplicate Francanglais text."""
    norm = text.strip().lower()
    if not norm:
        return False
    for e in load_all():
        if exclude_id is not None and e["id"] == exclude_id:
            continue
        if e["text"].strip().lower() == norm:
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