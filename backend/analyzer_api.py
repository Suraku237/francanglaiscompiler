from fastapi import APIRouter, Query

from . import analyzer, analyzer_history, coursework_store
from .analyzer_models import AnalyzerTestRequest, CanonicalUUID, RecordedTest, TestReport
from .coursework_api import course_operation
from .coursework_models import GrammarRequest, PracticeText

router = APIRouter(prefix="/api/analyzer", tags=["Franc Analyzer"])


class AnalyzerRequest(GrammarRequest):
    text: PracticeText


@router.get("")
def get_analyzer() -> dict:
    return course_operation(analyzer.analyzer_state)


@router.put("/grammar")
def save_grammar(payload: GrammarRequest) -> GrammarRequest:
    def operation() -> GrammarRequest:
        # Read and merge under the workspace lock, preserving the legacy profile.
        profile = coursework_store.load_project().model_copy(update={"grammar": payload.grammar})
        return GrammarRequest(grammar=coursework_store.save_project(profile).grammar)

    return course_operation(operation)


@router.post("/analyze")
def analyze(payload: AnalyzerRequest) -> dict:
    return course_operation(lambda: analyzer.analyze(payload.text, payload.grammar))


@router.post("/tests")
def record_test(payload: AnalyzerTestRequest) -> RecordedTest:
    return course_operation(lambda: analyzer_history.record_test(payload))


@router.get("/tests")
def test_report(
    offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
) -> TestReport:
    return course_operation(lambda: analyzer_history.test_report(offset, limit))


@router.get("/tests/{test_id}")
def get_test(test_id: CanonicalUUID) -> RecordedTest:
    return course_operation(lambda: analyzer_history.get_test(test_id))
