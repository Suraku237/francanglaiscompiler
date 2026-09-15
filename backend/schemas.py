from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from compiler.lexer.lexicon import TERMINAL_CATEGORIES

Language = Literal["fr", "en"]
TranslationLanguage = Literal["fr", "en", "francanglais", "pidgin"]
DatasetLanguage = Literal["francanglais", "pidgin", "mixed", "unspecified"]
ReviewStatus = Literal["unreviewed", "approved"]
Origin = Literal["dataset", "ai_with_dataset", "ai"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Gloss = Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
StoredText = Annotated[str, StringConstraints(min_length=1, max_length=4000)]
StoredGloss = Annotated[str, StringConstraints(max_length=4000)]
StoredNotes = Annotated[str, StringConstraints(max_length=2000)]


class Evidence(BaseModel):
    id: str
    text: str
    language: DatasetLanguage
    french_gloss: str
    english_gloss: str
    match_type: Literal["exact", "phrase", "token"]


class Coverage(BaseModel):
    matched_terms: list[str] = Field(default_factory=list)
    unmatched_terms: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnalyzeRequest(RequestModel):
    text: Text


class TranslationRequest(AnalyzeRequest):
    source_language: TranslationLanguage = "fr"
    target_language: TranslationLanguage = "francanglais"
    tone: Literal["everyday", "polite", "street"] = "everyday"
    explanation_language: Language = "en"
    use_dataset: bool = True
    allow_ai: bool = True

    @model_validator(mode="after")
    def different_languages(self) -> Self:
        if self.source_language == self.target_language:
            raise ValueError("Source and target languages must differ.")
        return self


class VocabularyItem(BaseModel):
    term: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    meaning: Text


class TranslationContent(BaseModel):
    translation: Text
    explanation: Text
    vocabulary: list[VocabularyItem] = Field(max_length=12)
    note: Notes


class TokenResult(BaseModel):
    text: str
    category: str


class AnalysisResult(BaseModel):
    tokens: list[TokenResult]
    code_mixed_spans: list[str]
    verb_phrases: list[str]


class TranslationResponse(TranslationContent):
    source_language: TranslationLanguage
    target_language: TranslationLanguage
    model: str
    analysis: AnalysisResult
    origin: Origin
    evidence: list[Evidence] = Field(default_factory=list)
    coverage: Coverage = Field(default_factory=Coverage)


class ChatMessage(RequestModel):
    role: Literal["user", "assistant"]
    content: Text


class ChatRequest(RequestModel):
    message: Text
    language: Language = "en"
    use_dataset: bool = True
    source_language: TranslationLanguage = "francanglais"
    target_language: TranslationLanguage = "en"
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_history(self) -> Self:
        if len(self.history) % 2:
            raise ValueError("History must contain complete user/assistant exchanges.")
        for index, message in enumerate(self.history):
            if message.role != ("user" if index % 2 == 0 else "assistant"):
                raise ValueError("History must alternate user and assistant messages.")
        if sum(len(message.content) for message in self.history) > 24000:
            raise ValueError("Conversation history must not exceed 24000 characters.")
        return self


class ChatResponse(BaseModel):
    reply: Text
    model: str
    origin: Origin = "ai"
    evidence: list[Evidence] = Field(default_factory=list)


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


class DatasetResponse(BaseModel):
    entries: list[DatasetEntry]
    total: int
    by_category: dict[str, int]
    by_type: dict[str, int]


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    ai_configured: bool
    model: str


class MetadataResponse(BaseModel):
    categories: list[str]
    entry_types: list[str]
    lexical_categories: list[str]
    dataset_languages: list[str]
