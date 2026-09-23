from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from compiler.lexer.lexicon import TERMINAL_CATEGORIES

from .ownership import Ownership

TranslationLanguage = Literal["fr", "en", "francanglais", "pidgin"]
DatasetLanguage = Literal["francanglais", "pidgin", "mixed", "unspecified"]
ReviewStatus = Literal["unreviewed", "approved"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Gloss = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
StoredText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
StoredGloss = Annotated[str, StringConstraints(max_length=4000)]
StoredNotes = Annotated[str, StringConstraints(max_length=2000)]


class DictionaryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: ShortText
    aliases: list[ShortText]
    language: Literal["francanglais"] = "francanglais"
    english_gloss: Text
    origin: ShortText
    topic: ShortText
    source_document: ShortText
    source_line: int = Field(ge=1)


class DictionaryResponse(BaseModel):
    entries: list[DictionaryEntry] = Field(max_length=100)
    total: int
    matched: int
    offset: int
    limit: int
    sources: list[str]


class PracticeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: StoredText
    language: Literal["francanglais"] = "francanglais"
    french_gloss: StoredGloss
    english_gloss: StoredGloss
    topic: ShortText
    notes: StoredNotes
    source_document: ShortText
    source_line: int = Field(ge=1)
    constructed: Literal[True] = True


class PracticeResponse(BaseModel):
    entries: list[PracticeEntry] = Field(max_length=100)
    total: int
    matched: int
    offset: int
    limit: int
    sources: list[str]


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(RequestModel):
    text: StoredText

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("Text must not be blank.")
        return text


class TokenResult(BaseModel):
    text: str
    category: str


class AnalysisResult(BaseModel):
    tokens: list[TokenResult]
    code_mixed_spans: list[str]
    verb_phrases: list[str]


class EntryCreate(RequestModel):
    text: StoredText
    entry_type: Literal["Word", "Phrase", "Sentence"] = "Sentence"
    french_gloss: StoredGloss = ""
    english_gloss: StoredGloss = ""
    language: DatasetLanguage = "francanglais"
    review_status: ReviewStatus = "unreviewed"
    lexical_category: ShortText = ""
    category: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)] = "Other"
    source_location: ShortText = ""
    notes: StoredNotes = ""
    contributor: ShortText = ""

    @model_validator(mode="after")
    def valid_lexical_metadata(self) -> Self:
        if not self.text.strip():
            raise ValueError("Text must not be blank.")
        if self.lexical_category not in ("", *TERMINAL_CATEGORIES):
            raise ValueError("Select a supported lexer terminal category or leave it empty.")
        return self


class EntryPatch(RequestModel):
    text: StoredText | None = None
    entry_type: Annotated[str, StringConstraints(max_length=200)] | None = None
    french_gloss: StoredGloss | None = None
    english_gloss: StoredGloss | None = None
    language: DatasetLanguage | None = None
    review_status: ReviewStatus | None = None
    lexical_category: ShortText | None = None
    category: Annotated[str, StringConstraints(max_length=200)] | None = None
    source_location: ShortText | None = None
    notes: StoredNotes | None = None
    contributor: ShortText | None = None

    @model_validator(mode="after")
    def reject_null_fields(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Supply at least one field to update.")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Use an empty string, not null, to clear optional fields.")
        if self.text is not None and not self.text.strip():
            raise ValueError("Text must not be blank.")
        if self.lexical_category is not None and self.lexical_category not in ("", *TERMINAL_CATEGORIES):
            raise ValueError("Select a supported lexer terminal category or leave it empty.")
        return self


class DatasetEntry(BaseModel):
    id: str
    text: str
    entry_type: str
    french_gloss: str
    english_gloss: str
    category: str
    source_location: str
    notes: str
    audio_filename: str
    contributor: str
    timestamp: str
    language: DatasetLanguage = "unspecified"
    review_status: ReviewStatus = "unreviewed"
    lexical_category: str = ""


class OwnedDatasetEntry(DatasetEntry):
    ownership: Ownership


DatasetEntryView = OwnedDatasetEntry | DatasetEntry


class DatasetResponse(BaseModel):
    entries: list[DatasetEntryView]
    total: int
    by_category: dict[str, int]
    by_type: dict[str, int]
    by_review_status: dict[str, int] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["compiler"] = "compiler"


class MetadataResponse(BaseModel):
    categories: list[str]
    entry_types: list[str]
    lexical_categories: list[str]
    dataset_languages: list[str]
