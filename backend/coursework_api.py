import csv
import logging
import sqlite3
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Response
from filelock import Timeout
from pydantic import ValidationError

from compiler.parser.service import analyze_grammar, parse_analysis
from data_collector import dataset

from . import coursework, coursework_store
from .collection import CollectionError
from .coursework_export import export_bundle
from .coursework_models import GrammarRequest, ParseRequest, ProjectProfile, ScreenshotRequest

router = APIRouter(prefix="/api/coursework", tags=["CS4110 coursework"])
T = TypeVar("T")
logger = logging.getLogger(__name__)


def course_operation(operation: Callable[[], T]) -> T:
    try:
        # Keep corpus, profile and screenshot reads on the same workspace revision.
        with dataset.dataset_lock():
            return operation()
    except Timeout as exc:
        raise CollectionError(503, "Coursework files are busy. Please try again.") from exc
    except (OSError, csv.Error, ValidationError, sqlite3.Error) as exc:
        logger.error("Coursework storage operation failed (%s)", type(exc).__name__)
        raise CollectionError(500, "Cannot read or save coursework. Check the server storage and permissions.") from exc
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


@router.post("/screenshots", status_code=201)
def upload_screenshot(payload: ScreenshotRequest) -> dict[str, str]:
    return course_operation(lambda: coursework_store.add_screenshot(payload))


@router.get("/screenshots/{image_id}")
def get_screenshot(image_id: str) -> Response:
    return course_operation(lambda: Response(
        coursework_store.screenshot_bytes(image_id), media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
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
