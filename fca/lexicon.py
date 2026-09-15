"""Loads the markdown dictionaries into a single searchable lexicon.

The ``dictionary/*.md`` files are the single source of truth for vocabulary. They are
human-readable tables, so they can be extended by hand without touching any code; this
module turns them into :class:`Entry` objects keyed by a normalised form.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .tokens import Cat, Lang

ROOT = Path(__file__).resolve().parent.parent
DICT_DIR = ROOT / "dictionary"
DATA_DIR = ROOT / "data"

_ROW = re.compile(r"^\|(.+)\|\s*$")
_SEPARATOR = re.compile(r"^\|[\s:|-]+\|$")
_HEADING = re.compile(r"^##\s+(.*?)\s*$")
_BOLD = re.compile(r"\*\*(.*?)\*\*")
_PAREN = re.compile(r"\([^)]*\)")

#: Default category per dictionary section, matched by keyword on the heading.
_SECTION_RULES = (
    ("verb", Cat.VERB),
    ("greeting", Cat.INTERJ),
    ("exclamation", Cat.INTERJ),
    ("describing", Cat.ADJ),
    ("adjective", Cat.ADJ),
    ("number", Cat.NUM),
    ("grammar", Cat.PART),
    ("time and weather", Cat.NOUN),
    ("body", Cat.NOUN),
    ("food", Cat.NOUN),
    ("people", Cat.NOUN),
    ("places", Cat.NOUN),
    ("home", Cat.NOUN),
    ("money", Cat.NOUN),
    ("trouble", Cat.NOUN),
)


def strip_accents(text: str) -> str:
    """Fold accented characters onto their ASCII base (``é`` -> ``e``)."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def normalize(text: str) -> str:
    """Canonical key form: accent-free, lowercase, punctuation-trimmed."""
    text = strip_accents(text).lower().replace("\u2019", "'")
    text = re.sub(r"[^a-z0-9'\- ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip("-'")


def clean_sense(sense: str) -> str:
    """Reduce one dictionary gloss to a bare English equivalent."""
    sense = _PAREN.sub("", sense)
    sense = sense.replace("lit.", "").strip()
    sense = re.sub(r"^(also|or|and|by extension|esp\.?)\s+", "", sense.strip(), flags=re.I)
    return re.sub(r"\s+", " ", sense).strip(" .;,?!")


def split_senses(gloss: str) -> list[str]:
    parts = [clean_sense(p) for p in re.split(r"[;!?]", gloss)]
    return [p for p in parts if p]


@dataclass
class Entry:
    """One dictionary row, already normalised and categorised."""

    term: str
    surface: str
    lang: Lang
    cat: Cat
    gloss: str
    senses: list[str] = field(default_factory=list)
    origin: str = ""
    section: str = ""
    candidates: tuple[Cat, ...] = ()

    @property
    def words(self) -> int:
        return len(self.term.split())

    @property
    def head(self) -> str:
        """Primary English equivalent: first sense, no infinitive ``to``, no aside."""
        first = self.senses[0] if self.senses else self.surface
        first = first.split(",")[0]
        return re.sub(r"^to\s+", "", first).strip()


class Lexicon:
    """All vocabulary from every dictionary, indexed by normalised form."""

    def __init__(self) -> None:
        self.entries: dict[str, list[Entry]] = {}
        self.max_words = 1
        self.explode: set[str] = set()
        self.mass_nouns: set[str] = set()
        self.english: dict[str, list[Cat]] = {}
        self.english_extra: set[str] = set()

    # -- construction ---------------------------------------------------

    def add(self, entry: Entry) -> None:
        if entry.term in self.explode:
            return
        bucket = self.entries.setdefault(entry.term, [])
        if any(e.lang is entry.lang and e.cat is entry.cat for e in bucket):
            return
        bucket.append(entry)
        self.max_words = max(self.max_words, entry.words)

    def lookup(self, key: str) -> list[Entry]:
        return self.entries.get(key, [])

    def __contains__(self, key: str) -> bool:
        return key in self.entries

    def __len__(self) -> int:
        return sum(len(v) for v in self.entries.values())

    def count(self, lang: Lang) -> int:
        return sum(1 for bucket in self.entries.values() for e in bucket if e.lang is lang)

    # -- English support ------------------------------------------------

    def is_english(self, key: str) -> bool:
        return key in self.english or key in self.english_extra

    def english_cats(self, key: str) -> tuple[Cat, ...]:
        if key in self.english:
            return tuple(self.english[key])
        return (Cat.NOUN, Cat.VERB) if key in self.english_extra else ()

    def english_cat(self, key: str) -> Cat:
        cats = self.english_cats(key)
        return cats[0] if cats else Cat.UNKNOWN


def _section_default(section: str) -> Cat:
    low = section.lower()
    for needle, cat in _SECTION_RULES:
        if needle in low:
            return cat
    return Cat.NOUN


def _term_variants(cell: str) -> list[str]:
    """Expand ``**mami / mama**`` and ``**Na wa (oh)**`` into separate keys."""
    match = _BOLD.search(cell)
    raw = match.group(1) if match else cell
    raw = raw.strip()
    variants: list[str] = []
    for piece in raw.split("/"):
        piece = piece.strip()
        if not piece:
            continue
        with_paren = normalize(piece)
        without_paren = normalize(_PAREN.sub("", piece))
        for candidate in (without_paren, with_paren):
            if candidate and candidate not in variants:
                variants.append(candidate)
    return variants


def parse_dictionary(path: Path, lang: Lang, overrides: dict) -> list[Entry]:
    """Read one markdown dictionary file into entries.

    A heading of the form ``## PIDGIN: determiners`` switches the language for the
    rows that follow, so a supplementary file can hold several languages at once.
    """
    entries: list[Entry] = []
    section = ""
    current = lang
    candidates = overrides.get("candidates", {})

    def tables_for(active: Lang) -> tuple[dict, dict]:
        return overrides.get("any", {}), overrides.get(active.value.lower(), {})

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _HEADING.match(line)
        if heading:
            section = heading.group(1)
            prefix, sep, rest = section.partition(":")
            if sep and prefix.strip().upper() in Lang.__members__:
                current = Lang[prefix.strip().upper()]
                section = rest.strip()
            continue
        row = _ROW.match(line.strip())
        if not row or _SEPARATOR.match(line.strip()):
            continue
        cells = [c.strip() for c in row.group(1).split("|")]
        if len(cells) < 2 or not _BOLD.search(cells[0]):
            continue  # table header row

        has_pos_column = len(cells) >= 3 and cells[1].isupper()
        if has_pos_column:
            explicit_cat, gloss, origin = cells[1], cells[2], ""
        else:
            explicit_cat, gloss = "", cells[1]
            origin = cells[2] if len(cells) >= 3 else ""

        any_over, lang_over = tables_for(current)
        senses = split_senses(gloss)
        for term in _term_variants(cells[0]):
            cat = _resolve_category(
                term, explicit_cat, senses, section, any_over, lang_over
            )
            cand = tuple(Cat(c) for c in candidates.get(term, ()))
            entries.append(
                Entry(
                    term=term,
                    surface=_BOLD.search(cells[0]).group(1).strip(),
                    lang=current,
                    cat=cat,
                    gloss=gloss,
                    senses=senses,
                    origin=origin,
                    section=section,
                    candidates=cand,
                )
            )
    return entries


def _resolve_category(
    term: str,
    explicit: str,
    senses: list[str],
    section: str,
    any_over: dict,
    lang_over: dict,
) -> Cat:
    # A table that declares its own POS column is trusted over the override file.
    if explicit:
        return Cat(explicit)
    if term in lang_over:
        return Cat(lang_over[term])
    if term in any_over:
        return Cat(any_over[term])
    if senses and senses[0].lower().startswith("to "):
        return Cat.VERB
    return _section_default(section)


def _load_english(path: Path) -> dict[str, list[Cat]]:
    """A word may be listed under several categories; keep them all as candidates."""
    words: dict[str, list[Cat]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        head, _, rest = line.partition(":")
        try:
            cat = Cat(head.strip())
        except ValueError:
            continue
        for word in rest.split(","):
            key = normalize(word)
            if not key:
                continue
            bucket = words.setdefault(key, [])
            if cat not in bucket:
                bucket.append(cat)
    return words


def load_lexicon(
    dict_dir: Path | None = None, data_dir: Path | None = None
) -> Lexicon:
    """Build the full lexicon from the dictionary and data directories."""
    dict_dir = dict_dir or DICT_DIR
    data_dir = data_dir or DATA_DIR

    overrides = json.loads((data_dir / "pos_overrides.json").read_text(encoding="utf-8"))
    lex = Lexicon()
    lex.explode = {normalize(t) for t in overrides.get("explode", ())}
    lex.mass_nouns = set(overrides.get("mass_nouns", ()))
    lex.english = _load_english(data_dir / "english_core.txt")

    sources = (
        (dict_dir / "pidgin.md", Lang.PIDGIN),
        (dict_dir / "camfranglais.md", Lang.CAMFRANGLAIS),
        (dict_dir / "french_core.md", Lang.FRENCH),
        (data_dir / "extra_lexicon.md", Lang.PIDGIN),
    )
    for path, lang in sources:
        if not path.exists():
            continue
        for entry in parse_dictionary(path, lang, overrides):
            lex.add(entry)

    # Every word used in an English gloss is, by definition, English.
    for bucket in lex.entries.values():
        for entry in bucket:
            for sense in entry.senses:
                for word in normalize(sense).split():
                    if len(word) > 1 and word not in lex.english:
                        lex.english_extra.add(word)
    return lex
