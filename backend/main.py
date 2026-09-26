import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from compiler.lexer.learned import build_lexicon
from compiler.lexer.tokenizer import analyze_sentence
from data_collector import dataset

from . import collection, dictionary, examples
from .analyzer_api import public_router as public_analyzer_router, router as analyzer_router
from .audio_api import public_router as public_audio_router, router as audio_router
from .auth import AuthSettings, install_auth
from .collection import storage_operation
from .config import ServerSettings, Settings
from .coursework_api import router as coursework_router
from .import_api import router as import_router
from .public_access import install_public_access
from .readings_api import public_router as public_readings_router, router as readings_router
from .web import install_web
from .workspace_backups import install_backups, maintain_backups
from .workspaces import install_workspace
from .schemas import (
    AnalysisResult,
    AnalyzeRequest,
    DatasetEntryView,
    DatasetResponse,
    DictionaryResponse,
    EntryCreate,
    EntryPatch,
    HealthResponse,
    MetadataResponse,
    PracticeResponse,
    TokenResult,
)


def analyze(text: str, entries: list[dict[str, str]] | None = None) -> AnalysisResult:
    result = analyze_sentence(text, build_lexicon(entries) if entries is not None else None)
    return AnalysisResult(
        tokens=[TokenResult(text=token.text, category=token.category) for token in result["tokens"]],
        code_mixed_spans=result["code_mixed_spans"],
        verb_phrases=result["verb_phrases"],
    )


def create_app(
    settings: Settings | None = None, *,
    include_academic: bool = True, require_auth: bool | None = None,
    auth_settings: AuthSettings | None = None,
    server_settings: ServerSettings | None = None,
    auth_transport: httpx.AsyncBaseTransport | None = None,
    mailer: Callable[[str, str, str], None] | None = None,
) -> FastAPI:
    """Public by default; explicit auth/maintenance modes retain offline legacy tooling."""
    config = settings if settings is not None else Settings()
    public = require_auth is None
    if server_settings is not None and (require_auth is not None or auth_settings is not None):
        raise ValueError("Use server_settings only for the public application.")
    accounts = auth_settings
    if require_auth and accounts is None:
        accounts = AuthSettings()
    server = server_settings or accounts or ServerSettings()
    if require_auth is False and server.environment == "production":
        raise ValueError("The unrestricted maintenance API cannot run in production.")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        stop = asyncio.Event()
        maintenance = asyncio.create_task(maintain_backups(server.data_dir, stop)) if public or require_auth else None
        try:
            yield
        finally:
            stop.set()
            if maintenance is not None:
                await maintenance

    app = FastAPI(
        title="Camfranglais Compiler",
        description="Shared manual fieldwork, lexical analysis, CFG transformations and LL(1) parsing.",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if server.environment == "production" else "/docs",
        redoc_url=None if server.environment == "production" else "/redoc",
        openapi_url=None if server.environment == "production" else "/openapi.json",
    )

    @app.exception_handler(collection.CollectionError)
    async def collection_error_handler(_request: Request, exc: collection.CollectionError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

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

    if not public:
        @app.post("/api/dataset", status_code=201, response_model=DatasetEntryView)
        def add_entry(payload: EntryCreate) -> DatasetEntryView:
            return storage_operation(lambda: collection.create_entry(payload))

        @app.patch("/api/dataset/{entry_id}", response_model=DatasetEntryView)
        def patch_entry(entry_id: str, payload: EntryPatch) -> DatasetEntryView:
            return storage_operation(lambda: collection.edit_entry(entry_id, payload))

        @app.delete("/api/dataset/{entry_id}", status_code=204)
        def delete_entry(entry_id: str) -> Response:
            storage_operation(lambda: collection.remove_entry(entry_id))
            return Response(status_code=204)

    if include_academic:
        app.include_router(public_analyzer_router if public else analyzer_router)
        if not public:
            app.include_router(coursework_router)
        app.add_api_route("/api/examples", get_examples, response_model=PracticeResponse, methods=["GET"])
    if not public:
        app.include_router(import_router)
    app.include_router(public_audio_router if public else audio_router)
    origins = [server.public_url]
    if server.environment == "development":
        origins.extend(config.cors_origins)
        origins.extend(["http://127.0.0.1:4188", "http://localhost:4188"])
    if require_auth:
        if accounts is None:
            raise ValueError("Legacy authenticated mode requires account settings.")
        app.include_router(readings_router)
        workspace = install_workspace(app, accounts.data_dir)
        install_backups(app)
        install_auth(
            app, accounts, workspace_context=workspace, allowed_origins=origins,
            transport=auth_transport, mailer=mailer,
        )
    elif public:
        app.include_router(public_readings_router)
        install_public_access(app, server, allowed_origins=origins, include_academic=include_academic)
    app.add_middleware(
        CORSMiddleware, allow_origins=origins, allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Mboa-Project"],
    )
    install_web(
        app, frontend_dir=Path(__file__).resolve().parents[1] / "frontend" / "dist",
        production=server.environment == "production", public_url=server.public_url,
    )
    return app


app = create_app()
