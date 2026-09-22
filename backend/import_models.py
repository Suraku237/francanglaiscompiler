from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_EXTRACTED_TEXT = 40000
MAX_PDF_PAGES = 40
MAX_DRAFTS = 100
ImportLanguage = Literal["francanglais", "pidgin", "mixed", "unspecified"]
DraftText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
OptionalText = Annotated[str, StringConstraints(max_length=4000)]
LexicalCategory = Literal[
    "", "NUMBER", "PUNCTUATION", "SLANG", "PIDGIN_MARKER", "NOUN", "VERB",
    "FRENCH_FUNCTION_WORD", "ENGLISH_FUNCTION_WORD", "ENGLISH_VERB_LIKE",
    "FRENCH_VERB_LIKE", "UNKNOWN",
]


class ImportEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: DraftText
    entry_type: Literal["Word", "Phrase", "Sentence"] = "Sentence"
    language: ImportLanguage = "unspecified"
    french_gloss: OptionalText = ""
    english_gloss: OptionalText = ""
    lexical_category: LexicalCategory = ""
    review_status: Literal["unreviewed"] = "unreviewed"
    category: Annotated[str, StringConstraints(min_length=1, max_length=200)] = "Other"
    source_location: Annotated[str, StringConstraints(max_length=200)] = ""
    contributor: Annotated[str, StringConstraints(max_length=200)] = ""
    notes: Annotated[str, StringConstraints(max_length=2000)] = ""


class ImportPreview(BaseModel):
    filename: str
    format: str
    method: Literal["local"] = "local"
    text: str
    segments: list[str]
    warnings: list[str] = Field(default_factory=list)
    drafts: list[ImportEntry] = Field(default_factory=list, max_length=MAX_DRAFTS)
