from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, Json, StringConstraints, field_validator, model_validator

from compiler.lexer.lexicon import TERMINAL_CATEGORIES

from .coursework_models import GrammarRequest, PracticeText
from .ownership import Ownership
from .schemas import DatasetLanguage
from .token_statistics import token_statistics


def canonical_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("Use a canonical UUID string.")
    return value


def iso_timestamp(value: str) -> str:
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("A timestamp must include its timezone.")
    return value


def lexer_category(value: str) -> str:
    if value not in TERMINAL_CATEGORIES:
        raise ValueError("Unknown lexer category.")
    return value


CanonicalUUID = Annotated[str, StringConstraints(min_length=36, max_length=36), AfterValidator(canonical_uuid)]
Timestamp = Annotated[str, AfterValidator(iso_timestamp)]
Category = Annotated[str, AfterValidator(lexer_category)]
Count = Annotated[int, Field(ge=0)]
PositiveCount = Annotated[int, Field(gt=0)]
Grammar = dict[str, list[list[str]]]


class AnalyzerTestRequest(GrammarRequest):
    request_id: CanonicalUUID
    text: PracticeText


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TokenSnapshot(SnapshotModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    category: Category


class Frequency(SnapshotModel):
    token: str
    count: PositiveCount


class VariationForm(SnapshotModel):
    text: str
    count: PositiveCount


class Variation(SnapshotModel):
    normalized: str
    forms: list[VariationForm] = Field(min_length=2)


class LexicalStatistics(SnapshotModel):
    frequencies: list[Frequency]
    category_counts: dict[Category, PositiveCount]
    variations: list[Variation]
    unknown_tokens: list[Frequency]
    total_tokens: Count


class VocabularyApproval(SnapshotModel):
    basis: Literal["no_unknown_tokens"] = "no_unknown_tokens"
    accepted: bool
    unknown_count: Count

    @classmethod
    def from_statistics(cls, statistics: LexicalStatistics) -> Self:
        count = sum(item.count for item in statistics.unknown_tokens)
        return cls(accepted=count == 0, unknown_count=count)

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.accepted != (self.unknown_count == 0):
            raise ValueError("Vocabulary approval must reject exactly the tests containing UNKNOWN tokens.")
        return self


class LexicalSnapshot(SnapshotModel):
    tokens: list[TokenSnapshot]
    code_mixed_spans: list[str]
    verb_phrases: list[str]
    slang_expressions: list[str]
    statistics: LexicalStatistics

    @model_validator(mode="after")
    def consistent_statistics(self) -> Self:
        if self.statistics.model_dump() != token_statistics(token.model_dump() for token in self.tokens):
            raise ValueError("Saved lexical statistics do not match the saved tokens.")
        return self


class TransformationStep(SnapshotModel):
    operation: str
    before: Grammar
    after: Grammar
    description: str


class GrammarConflict(SnapshotModel):
    nonterminal: str
    terminal: str
    productions: list[list[str]]


class GrammarAnalysis(SnapshotModel):
    original: Grammar
    transformed: Grammar
    start_symbol: str
    terminals: list[str]
    nonterminals: list[str]
    steps: list[TransformationStep]
    first: dict[str, list[str]]
    follow: dict[str, list[str]]
    table: dict[str, dict[str, list[str]]]
    conflicts: list[GrammarConflict]
    is_ll1: bool
    warnings: list[str]

    @model_validator(mode="after")
    def consistent_symbols(self) -> Self:
        if self.start_symbol not in self.original or self.start_symbol not in self.transformed:
            raise ValueError("Saved grammar is missing its start symbol.")
        if self.nonterminals != list(self.transformed):
            raise ValueError("Saved grammar nonterminals disagree with its transformed rules.")
        if set(self.first) != set(self.transformed) or set(self.follow) != set(self.transformed):
            raise ValueError("Saved grammar sets disagree with its transformed rules.")
        if self.conflicts and self.is_ll1:
            raise ValueError("A conflicting grammar cannot be LL(1).")
        return self


class ParseStep(SnapshotModel):
    stack: list[str]
    remaining: list[str]
    action: str


class ParseResult(SnapshotModel):
    accepted: bool
    error: str | None
    trace: list[ParseStep] = Field(min_length=1)
    consumed: Count

    @model_validator(mode="after")
    def consistent_outcome(self) -> Self:
        if self.accepted != (self.error is None):
            raise ValueError("Saved parse outcome and error disagree.")
        return self


class TestMetadata(SnapshotModel):
    topics: list[Annotated[str, StringConstraints(min_length=1)]]
    languages: list[DatasetLanguage]
    matching_entries: Count

    @model_validator(mode="after")
    def distinct_recorded_labels(self) -> Self:
        for labels in (self.topics, self.languages):
            if len(labels) != len(set(labels)) or len(labels) > self.matching_entries:
                raise ValueError("Saved labels must be distinct labels of matching entries.")
        if any(not topic.strip() for topic in self.topics):
            raise ValueError("Empty topics are not recorded labels.")
        return self


class RecordedTest(SnapshotModel):
    id: CanonicalUUID
    created_at: Timestamp
    grammar_source: Annotated[str, StringConstraints(min_length=1, max_length=12000)]
    text: PracticeText
    lexical: LexicalSnapshot
    grammar: GrammarAnalysis
    parse: ParseResult
    metadata: TestMetadata

    @field_validator("grammar_source")
    @classmethod
    def canonical_grammar(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("Saved grammar source must use the canonical trimmed form.")
        return value

    @model_validator(mode="after")
    def consistent_consumption(self) -> Self:
        if self.parse.consumed > len(self.lexical.tokens):
            raise ValueError("Parse consumption exceeds the saved token count.")
        if self.parse.accepted and self.parse.consumed != len(self.lexical.tokens):
            raise ValueError("An accepted parse must consume every saved token.")
        if self.parse.accepted and not self.grammar.is_ll1:
            raise ValueError("A non-LL(1) grammar cannot produce an accepted predictive parse.")
        return self


class RecordedTestResult(RecordedTest):
    approval: VocabularyApproval

    @model_validator(mode="after")
    def consistent_approval(self) -> Self:
        if self.approval != VocabularyApproval.from_statistics(self.lexical.statistics):
            raise ValueError("Vocabulary approval disagrees with the saved token categories.")
        return self


class OwnedRecordedTest(RecordedTestResult):
    ownership: Ownership


RecordedTestView = OwnedRecordedTest | RecordedTestResult


class StoredAnalyzerTest(SnapshotModel):
    id: CanonicalUUID
    project_id: str
    data: Json[RecordedTest]

    @field_validator("project_id")
    @classmethod
    def project_identifier(cls, value: str) -> str:
        return value if value == "default" else canonical_uuid(value)

    @model_validator(mode="after")
    def matching_identifier(self) -> Self:
        if self.id != self.data.id:
            raise ValueError("Saved analyzer test identifiers disagree.")
        return self


class TestSummary(SnapshotModel):
    id: CanonicalUUID
    created_at: Timestamp
    text: PracticeText
    accepted: bool
    token_count: Count
    error: str | None
    unknown_count: Count
    grammar_accepted: bool
    grammar_error: str | None


class OwnedTestSummary(TestSummary):
    ownership: Ownership


class TestTotals(SnapshotModel):
    total: Count
    accepted: Count
    rejected: Count
    acceptance_rate: Annotated[float, Field(ge=0, le=100)] | None


class AggregateStatistics(LexicalStatistics):
    raw_frequencies: list[Frequency]
    normalized_frequencies: list[Frequency]


class UnknownReview(Frequency):
    tests: PositiveCount
    forms: list[str] = Field(min_length=1)


class TestReport(SnapshotModel):
    approval_basis: Literal["no_unknown_tokens"] = "no_unknown_tokens"
    summary: TestTotals
    grammar_summary: TestTotals
    statistics: AggregateStatistics
    unknown_review: list[UnknownReview]
    topic_counts: dict[str, PositiveCount]
    language_counts: dict[str, PositiveCount]
    tests: list[OwnedTestSummary | TestSummary]
    offset: Count
    limit: Annotated[int, Field(ge=1, le=100)]
