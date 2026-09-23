from fastapi import APIRouter

from . import analyzer, coursework_store
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
