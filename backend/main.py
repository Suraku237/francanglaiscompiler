import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from compiler.lexer.learned import build_lexicon
from compiler.lexer.tokenizer import analyze_sentence
from data_collector import dataset

from . import collection, dictionary, examples
from .audio_api import router as audio_router
from .auth import AuthSettings, get_current_identity, install_auth
from .collection import storage_operation
from .config import Settings
from .coursework_api import router as coursework_router
from .gemini import AIError, GeminiService
from .grounding import ai_origin, local_translation, retrieve, without_local_sources
from .import_api import router as import_router
from .web import install_web
from .workspace_backups import install_backups, maintain_backups
from .workspaces import install_workspace
from .schemas import (
    AnalysisResult,
    AnalyzeRequest,
    ChatRequest,
    ChatResponse,
    DatasetEntry,
    DatasetResponse,
    DictionaryResponse,
    EntryCreate,
    EntryPatch,
    HealthResponse,
    MetadataResponse,
    Origin,
    PracticeResponse,
    TokenResult,
    TranslationRequest,
    TranslationResponse,
)


def analyze(text: str, entries: list[dict[str, str]] | None = None) -> AnalysisResult:
    result = analyze_sentence(text, build_lexicon(entries) if entries is not None else None)
    return AnalysisResult(
        tokens=[TokenResult(text=token.text, category=token.category) for token in result["tokens"]],
        code_mixed_spans=result["code_mixed_spans"],
        verb_phrases=result["verb_phrases"],
    )


def create_app(
    settings: Settings | None = None, *, transport: httpx.AsyncBaseTransport | None = None,
    include_academic: bool = False, require_auth: bool = True,
    auth_settings: AuthSettings | None = None,
    auth_transport: httpx.AsyncBaseTransport | None = None,
    mailer: Callable[[str, str, str], None] | None = None,
) -> FastAPI:
    config = settings if settings is not None else Settings()
    accounts = auth_settings if auth_settings is not None else AuthSettings()
    if include_academic and require_auth:
        raise ValueError("Archived academic routes must not be enabled in the hosted application.")
    if not require_auth and accounts.environment == "production":
        raise ValueError("Authentication cannot be disabled in production.")

    def charge_ai():
        user = get_current_identity()
        if user is None:
            raise collection.CollectionError(401, "Sign in before requesting AI processing.")
        app.state.auth_store.charge_ai(user.id)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with httpx.AsyncClient(transport=transport) as client:
            app.state.gemini = GeminiService(config, client, before_request=charge_ai if require_auth else None)
            stop = asyncio.Event()
            maintenance = asyncio.create_task(maintain_backups(accounts.data_dir, stop)) if require_auth else None
            try:
                yield
            finally:
                stop.set()
                if maintenance is not None:
                    await maintenance

    app = FastAPI(
        title="Mboa Language Workspace",
        description="Private accounts, translation, terminology and reviewed document/audio processing.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if accounts.environment == "production" else "/docs",
        redoc_url=None if accounts.environment == "production" else "/redoc",
        openapi_url=None if accounts.environment == "production" else "/openapi.json",
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
        if payload.use_examples and not include_academic:
            raise collection.CollectionError(422, "This source is not available in the professional workspace.")
        service: GeminiService = request.app.state.gemini
        def get_grounding():
            entries = dataset.load_all() if payload.use_dataset else []
            grounding = retrieve(
                entries, payload.text, payload.source_language, payload.target_language,
                references=dictionary.load_dictionary() if payload.use_dictionary else [],
                examples=examples.load_examples() if payload.use_examples else [],
            ) if payload.use_dataset or payload.use_dictionary or payload.use_examples else without_local_sources(payload.text)
            return entries, grounding

        entries, grounding = await run_in_threadpool(lambda: storage_operation(get_grounding))
        origin: Origin
        if grounding.exact_translation is not None:
            result = local_translation(grounding, payload.explanation_language)
            if grounding.exact_sources == {"dictionary"}:
                origin, model = "dictionary", "local-dictionary"
            elif grounding.exact_sources == {"examples"}:
                origin, model = "examples", "local-examples"
            elif grounding.exact_sources == {"dataset"}:
                origin, model = "dataset", "local-dataset"
            else:
                origin, model = "local_sources", "local-sources"
        else:
            if not payload.allow_ai:
                raise collection.CollectionError(
                    422, "No unambiguous full-entry translation is available from the enabled local sources "
                    "and AI suggestions are disabled. Check dictionary meanings, translation direction and "
                    "conflicting senses; the supplied dictionary has English meanings only. "
                    "Add or review a complete aligned entry, or enable AI suggestions."
                )
            result = await service.translate(payload, grounding.evidence, grounding.coverage)
            label = (
                "Suggestion IA non vérifiée, à réviser manuellement. "
                if payload.explanation_language == "fr" else "Unverified AI suggestion; manual review required. "
            )
            result = result.model_copy(update={"note": label + result.note[:2000 - len(label)]})
            origin = ai_origin(grounding.evidence)
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
        if payload.use_examples and not include_academic:
            raise collection.CollectionError(422, "This source is not available in the professional workspace.")
        service: GeminiService = request.app.state.gemini
        evidence = []
        if payload.use_dataset or payload.use_dictionary or payload.use_examples:
            grounding = await run_in_threadpool(lambda: storage_operation(lambda: retrieve(
                dataset.load_all() if payload.use_dataset else [],
                payload.message, payload.source_language, payload.target_language,
                references=dictionary.load_dictionary() if payload.use_dictionary else [],
                examples=examples.load_examples() if payload.use_examples else [],
                recent_user_messages=[message.content for message in payload.history if message.role == "user"],
                chat=True,
            )))
            evidence = grounding.evidence
        return ChatResponse(
            reply=await service.chat(payload, evidence), model=config.gemini_model,
            origin=ai_origin(evidence), evidence=evidence,
        )

    @app.post("/api/analyze", response_model=AnalysisResult)
    def analyze_text(payload: AnalyzeRequest) -> AnalysisResult:
        return storage_operation(lambda: analyze(payload.text, dataset.load_all()))

    @app.get("/api/metadata", response_model=MetadataResponse)
    def metadata() -> MetadataResponse:
        return MetadataResponse(
            categories=dataset.CATEGORIES if include_academic else dataset.BUSINESS_CATEGORIES,
            entry_types=dataset.ENTRY_TYPES,
            lexical_categories=dataset.LEXICAL_CATEGORIES, dataset_languages=dataset.DATASET_LANGUAGES,
        )

    @app.get("/api/dataset", response_model=DatasetResponse)
    def get_dataset(query: str = Query(default="", max_length=200)) -> DatasetResponse:
        return storage_operation(lambda: collection.list_entries(query))

    def get_examples(
        query: str = Query(default="", max_length=200),
        offset: int = Query(default=0, ge=0), limit: int = Query(default=25, ge=1, le=100),
    ) -> PracticeResponse:
        return examples.list_examples(query, offset, limit)

    @app.get("/api/dictionary", response_model=DictionaryResponse)
    def get_dictionary(
        query: str = Query(default="", max_length=200),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ) -> DictionaryResponse:
        return dictionary.list_dictionary(query, offset, limit)

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

    if include_academic:
        app.include_router(coursework_router)
        app.add_api_route("/api/examples", get_examples, response_model=PracticeResponse, methods=["GET"])
    app.include_router(import_router)
    app.include_router(audio_router)
    origins = [accounts.public_url]
    if accounts.environment == "development":
        origins.extend(config.cors_origins)
        origins.extend(["http://127.0.0.1:4188", "http://localhost:4188"])
    if require_auth:
        workspace = install_workspace(app, accounts.data_dir)
        install_backups(app)
        install_auth(
            app, accounts, workspace_context=workspace, allowed_origins=origins,
            transport=auth_transport, mailer=mailer,
        )
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Mboa-Project"],
    )
    install_web(
        app, frontend_dir=Path(__file__).resolve().parents[1] / "frontend" / "dist",
        production=accounts.environment == "production", public_url=accounts.public_url,
    )
    return app


app = create_app()
