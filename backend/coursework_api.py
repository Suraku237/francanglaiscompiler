import csv
import json
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Request, Response
from fastapi.responses import FileResponse
from filelock import Timeout
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from compiler.parser.service import analyze_grammar, parse_analysis

from . import coursework, coursework_store
from .collection import CollectionError
from .coursework_export import export_bundle
from .coursework_models import ExplainRequest, GrammarRequest, ParseRequest, ProjectProfile, ScreenshotRequest
from .gemini import GeminiService
from .schemas import ChatResponse

router = APIRouter(prefix="/api/coursework", tags=["CS4110 coursework"])
T = TypeVar("T")


def course_operation(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Timeout as exc:
        raise CollectionError(503, "Coursework files are busy. Please try again.") from exc
    except (OSError, csv.Error, ValidationError) as exc:
        raise CollectionError(500, "Cannot read or save coursework files. Check the local data and permissions.") from exc
    except ValueError as exc:
        raise CollectionError(422, str(exc)) from exc


@router.get("")
def get_coursework() -> dict:
    return course_operation(coursework.coursework_state)


@router.put("/project")
def save_project(payload: ProjectProfile) -> ProjectProfile:
    return course_operation(lambda: coursework_store.save_project(payload))


@router.post("/analyze")
def analyze_corpus(payload: GrammarRequest) -> dict:
    return course_operation(lambda: coursework.analyze_coursework(payload.grammar))


@router.post("/parse")
def parse_text(payload: ParseRequest) -> dict:
    def operation() -> dict:
        grammar = analyze_grammar(payload.grammar)
        tokens = coursework.tokens_for(payload.text)
        return {"tokens": tokens, "parse": parse_analysis(grammar, tokens)}
    return course_operation(operation)


@router.post("/explain", response_model=ChatResponse)
async def explain(payload: ExplainRequest, request: Request) -> ChatResponse:
    def context_for_ai() -> str:
        analysis = analyze_grammar(payload.grammar)
        parsed = parse_analysis(analysis, coursework.tokens_for(payload.text))
        # Send only explicitly entered text/grammar and selected computed facts, never the corpus/profile.
        context = {
            "grammar": payload.grammar, "practice_text": payload.text,
            "is_ll1": analysis["is_ll1"], "conflicts": analysis["conflicts"][:10],
            "first": analysis["first"], "follow": analysis["follow"],
            "parse": {"accepted": parsed["accepted"], "error": parsed["error"], "consumed": parsed["consumed"]},
            "last_trace_steps": parsed["trace"][-5:],
        }
        encoded = json.dumps(context, ensure_ascii=False)
        if len(encoded) > 30000:
            raise ValueError("This grammar creates too much context for AI help. Simplify it or ask about a smaller grammar.")
        return encoded

    context = await run_in_threadpool(lambda: course_operation(context_for_ai))
    service: GeminiService = request.app.state.gemini
    reply = await service.explain_coursework(payload.question, payload.language, context)
    return ChatResponse(reply=reply, model=service.settings.gemini_model)


@router.post("/screenshots", status_code=201)
def upload_screenshot(payload: ScreenshotRequest) -> dict[str, str]:
    return course_operation(lambda: coursework_store.add_screenshot(payload))


@router.get("/screenshots/{image_id}")
def get_screenshot(image_id: str) -> FileResponse:
    return course_operation(lambda: FileResponse(
        coursework_store.screenshot_path(image_id), media_type="image/png"
    ))


@router.delete("/screenshots/{image_id}", status_code=204)
def delete_screenshot(image_id: str) -> Response:
    course_operation(lambda: coursework_store.delete_screenshot(image_id))
    return Response(status_code=204)


@router.get("/export")
def download_export() -> Response:
    content = course_operation(export_bundle)
    return Response(content, media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="francanglais-coursework.zip"',
        "Cache-Control": "no-store",
    })
