from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .schemas import RequestModel

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


class SuggestedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: DraftText
    entry_type: Literal["Word", "Phrase", "Sentence"] = "Sentence"
    language: ImportLanguage = "unspecified"
    french_gloss: OptionalText = ""
    english_gloss: OptionalText = ""
    lexical_category: LexicalCategory = ""
    review_status: Literal["unreviewed"] = "unreviewed"


class ImportPreview(BaseModel):
    filename: str
    format: str
    method: Literal["local", "gemini"]
    text: str
    segments: list[str]
    warnings: list[str] = Field(default_factory=list)
    drafts: list[SuggestedEntry] = Field(default_factory=list, max_length=MAX_DRAFTS)


class SuggestRequest(RequestModel):
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    language: Literal["francanglais", "pidgin", "mixed"]


class SuggestionResponse(BaseModel):
    drafts: list[SuggestedEntry] = Field(max_length=12)
    warnings: list[str]
    model: str
