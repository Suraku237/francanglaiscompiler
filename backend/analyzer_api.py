from fastapi import APIRouter, Query

from . import analyzer, analyzer_history, coursework_store
from .analyzer_models import (
    AnalyzerTestRequest, CanonicalUUID, OwnedRecordedTest, RecordedTest, RecordedTestResult,
    RecordedTestView, TestReport, VocabularyApproval,
)
from .coursework_api import course_operation
from .coursework_models import GrammarRequest, PracticeText
from .ownership import record_ownership

router = APIRouter(prefix="/api/analyzer", tags=["Franc Analyzer"])


class AnalyzerRequest(GrammarRequest):
    text: PracticeText


@router.get("")
def get_analyzer() -> dict:
    return course_operation(analyzer.analyzer_state)


@router.put("/grammar")
def save_grammar(payload: GrammarRequest) -> dict:
    def operation() -> dict:
        # Read and merge under the workspace lock, preserving the legacy profile.
        profile = coursework_store.load_project().model_copy(update={"grammar": payload.grammar})
        response: dict[str, object] = {"grammar": coursework_store.save_project(profile).grammar}
        ownership = record_ownership("coursework", "default")
        if ownership is not None:
            response["grammar_ownership"] = ownership.model_dump()
        return response

    return course_operation(operation)


@router.post("/analyze")
def analyze(payload: AnalyzerRequest) -> dict:
    return course_operation(lambda: analyzer.analyze(payload.text, payload.grammar))


@router.post("/tests")
def record_test(payload: AnalyzerTestRequest) -> RecordedTestView:
    return course_operation(lambda: test_view(analyzer_history.record_test(payload)))


def test_view(record: RecordedTest) -> RecordedTestView:
    ownership = record_ownership("analyzer_test", record.id)
    result = {**record.model_dump(), "approval": VocabularyApproval.from_statistics(record.lexical.statistics)}
    return OwnedRecordedTest(**result, ownership=ownership) if ownership is not None else RecordedTestResult(**result)


@router.get("/tests")
def test_report(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
) -> TestReport:
    return course_operation(lambda: analyzer_history.test_report(offset, limit))


@router.get("/tests/{test_id}")
def get_test(test_id: CanonicalUUID) -> RecordedTestView:
    return course_operation(lambda: test_view(analyzer_history.get_test(test_id)))
