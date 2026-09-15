import csv
import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

import httpx
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from filelock import Timeout
from starlette.concurrency import run_in_threadpool

from compiler.lexer.learned import build_lexicon
from compiler.lexer.tokenizer import analyze_sentence
from data_collector import dataset

from . import collection
from .config import Settings
from .coursework_api import router as coursework_router
from .gemini import AIError, GeminiService
from .grounding import local_translation, retrieve, without_dataset
from .import_api import router as import_router
from .schemas import (
    AnalysisResult,
    AnalyzeRequest,
    ChatRequest,
    ChatResponse,
    DatasetEntry,
    DatasetResponse,
    EntryCreate,
    EntryPatch,
    HealthResponse,
    MetadataResponse,
    TokenResult,
    TranslationRequest,
    TranslationResponse,
)

logger = logging.getLogger(__name__)
T = TypeVar("T")


def analyze(text: str, entries: list[dict[str, str]] | None = None) -> AnalysisResult:
    result = analyze_sentence(text, build_lexicon(entries) if entries is not None else None)
    return AnalysisResult(
        tokens=[TokenResult(text=token.text, category=token.category) for token in result["tokens"]],
        code_mixed_spans=result["code_mixed_spans"],
        verb_phrases=result["verb_phrases"],
    )


def storage_operation(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except Timeout as exc:
        raise collection.CollectionError(503, "The collection is busy. Please try again.") from exc
    except (OSError, csv.Error, ValueError) as exc:
        logger.error("Collection storage operation failed (%s)", type(exc).__name__)
        raise collection.CollectionError(
            500, "Cannot read or save the collection. Check the server CSV file and permissions."
        ) from exc


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.gemini = GeminiService(config, client)
            yield

    app = FastAPI(
        title="Mboa - Francanglais and Cameroon Pidgin",
        description="Dataset-first translation, language learning, reviewed multimodal imports and compiler analysis.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(AIError)
    async def ai_error_handler(_request: Request, exc: AIError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(collection.CollectionError)
    async def collection_error_handler(_request: Request, exc: collection.CollectionError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ai_configured=config.ai_configured, model=config.gemini_model)

    @app.post("/api/translate", response_model=TranslationResponse)
    async def translate(payload: TranslationRequest, request: Request) -> TranslationResponse:
        service: GeminiService = request.app.state.gemini
        def get_grounding():
            entries = dataset.load_all() if payload.use_dataset else []
            grounding = retrieve(
                entries, payload.text, payload.source_language, payload.target_language
            ) if payload.use_dataset else without_dataset(payload.text)
            return entries, grounding

        entries, grounding = await run_in_threadpool(lambda: storage_operation(get_grounding))
        if grounding.exact_translation is not None:
            result = local_translation(grounding, payload.explanation_language)
            origin, model = "dataset", "local-dataset"
        else:
            if not payload.allow_ai:
                raise collection.CollectionError(
                    422, "No unambiguous approved full-entry translation is available and AI suggestions are disabled. "
                    "Add or review a complete aligned entry, or enable AI suggestions."
                )
            result = await service.translate(payload, grounding.evidence, grounding.coverage)
            label = (
                "Suggestion IA non vérifiée, à réviser manuellement. "
                if payload.explanation_language == "fr" else "Unverified AI suggestion; manual review required. "
            )
            result = result.model_copy(update={"note": label + result.note[:2000 - len(label)]})
            origin = "ai_with_dataset" if grounding.evidence else "ai"
            model = config.gemini_model
        return TranslationResponse(
            **result.model_dump(),
            source_language=payload.source_language,
            target_language=payload.target_language,
            model=model, origin=origin,
            evidence=grounding.evidence, coverage=grounding.coverage,
            analysis=analyze(result.translation, entries),
        )

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        service: GeminiService = request.app.state.gemini
        evidence = []
        if payload.use_dataset:
            grounding = await run_in_threadpool(lambda: storage_operation(lambda: retrieve(
                dataset.load_all(), payload.message, payload.source_language, payload.target_language,
                recent_user_messages=[message.content for message in payload.history if message.role == "user"],
                chat=True,
            )))
            evidence = grounding.evidence
        return ChatResponse(
            reply=await service.chat(payload, evidence), model=config.gemini_model,
            origin="ai_with_dataset" if evidence else "ai", evidence=evidence,
        )

    @app.post("/api/analyze", response_model=AnalysisResult)
    def analyze_text(payload: AnalyzeRequest) -> AnalysisResult:
        return storage_operation(lambda: analyze(payload.text, dataset.load_all()))

    @app.get("/api/metadata", response_model=MetadataResponse)
    def metadata() -> MetadataResponse:
        return MetadataResponse(
            categories=dataset.CATEGORIES, entry_types=dataset.ENTRY_TYPES,
            lexical_categories=dataset.LEXICAL_CATEGORIES, dataset_languages=dataset.DATASET_LANGUAGES,
        )

    @app.get("/api/dataset", response_model=DatasetResponse)
    def get_dataset(query: str = Query(default="", max_length=200)) -> DatasetResponse:
        return storage_operation(lambda: collection.list_entries(query))

    @app.post("/api/dataset", status_code=201, response_model=DatasetEntry)
    def add_entry(payload: EntryCreate) -> DatasetEntry:
        return storage_operation(lambda: collection.create_entry(payload))

    @app.patch("/api/dataset/{entry_id}", response_model=DatasetEntry)
    def patch_entry(entry_id: str, payload: EntryPatch) -> DatasetEntry:
        return storage_operation(lambda: collection.edit_entry(entry_id, payload))

    @app.delete("/api/dataset/{entry_id}", status_code=204)
    def delete_entry(entry_id: str) -> Response:
        storage_operation(lambda: collection.remove_entry(entry_id))
        return Response(status_code=204)

    app.include_router(coursework_router)
    app.include_router(import_router)
    return app


app = create_app()
