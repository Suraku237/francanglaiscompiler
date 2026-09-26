import hmac
import logging
import re
import secrets
import sqlite3
from contextlib import closing
from contextvars import ContextVar
from pathlib import Path
from threading import Lock
from uuid import NAMESPACE_URL, uuid5

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from filelock import Timeout
from starlette.concurrency import run_in_threadpool

from . import coursework_store
from .auth import digest, private_directory
from .collection import CollectionError
from .config import ServerSettings
from .ownership import Ownership
from .rate_limits import RateLimitExceeded, throttle
from .shared_workspace import SharedWorkspaceStore
from .workspaces import use_workspace, valid_id

logger = logging.getLogger(__name__)
PUBLIC_OWNER_ID = str(uuid5(NAMESPACE_URL, "camfranglais:public-analyzer"))
COOKIE = "camfranglais_public"
READ_ONLY_MESSAGE = "This public workspace is read-only. You can analyze inputs and save tests."
_public_request: ContextVar[bool] = ContextVar("public_workspace_request", default=False)
_READ_PATHS = {
    "/api/health", "/api/public/session", "/api/metadata", "/api/dataset",
    "/api/dictionary", "/api/examples", "/api/analyzer", "/api/analyzer/tests",
}
_POST_PATHS = {"/api/analyze", "/api/analyzer/analyze", "/api/analyzer/tests", "/api/readings/lookup"}
_READ_RESOURCE = re.compile(r"/api/(?:analyzer/tests/[^/]+|(?:dataset|readings)/[^/]+/audio)")
_READ_ONLY_RESOURCE = re.compile(r"/api/(?:dataset(?:/[^/]+(?:/audio)?)?|readings(?:/[^/]+(?:/audio)?)?|analyzer/grammar)")


class PublicWorkspaceStore(SharedWorkspaceStore):
    def __init__(self, data_dir: Path):
        super().__init__(data_dir, PUBLIC_OWNER_ID, "Public visitor")

    def authorize_write(
        self, db: sqlite3.Connection, kind: str, identifier: str, *, new: bool = False,
    ) -> None:
        if kind != "analyzer_test" or not new:
            raise CollectionError(403, READ_ONLY_MESSAGE)
        if db.execute("SELECT 1 FROM analyzer_tests WHERE id=?", (identifier,)).fetchone():
            raise CollectionError(409, "Saved tests are immutable. Reuse the original request to retrieve its result.")
        super().authorize_write(db, kind, identifier, new=True)

    def authorize_import(self, document: dict) -> None:
        raise CollectionError(403, READ_ONLY_MESSAGE)

    def ownership(self, kind: str, identifier: str) -> Ownership:
        # Historical creator identities remain private; their stored ownership is not changed.
        return Ownership(owner_id=None, owner_name="", can_edit=False)


class PublicAccessState:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "public-access.sqlite3"
        self._store: PublicWorkspaceStore | None = None
        self._initialization = Lock()

    def workspace(self) -> PublicWorkspaceStore:
        with self._initialization:
            if self._store is None:
                private_directory(self.data_dir)
                if self.path.is_symlink():
                    raise ValueError("The public request-limit database must not be a filesystem link.")
                with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
                    db.execute("CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY,count INTEGER NOT NULL,expires REAL NOT NULL)")
                self._store = PublicWorkspaceStore(self.data_dir)
            return self._store

    def limit(self, address: str) -> PublicWorkspaceStore:
        workspace = self.workspace()
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            throttle(db, f"public:{digest(address)}", 120, 60)
        return workspace


def require_shared_grammar(grammar: str, *, request_id: str | None = None) -> None:
    if _public_request.get() and grammar != coursework_store.load_project().grammar:
        # A retry retrieves an immutable earlier result rather than running a new analysis.
        if request_id is not None and coursework_store.load_analyzer_request(request_id) is not None:
            return
        raise CollectionError(409, "Use the saved shared grammar. Reload the application before analyzing again.")


def _csrf(raw: str) -> str:
    return digest("public-csrf:" + raw)


def install_public_access(
    app: FastAPI, settings: ServerSettings, *, allowed_origins: list[str], include_academic: bool,
) -> None:
    state = PublicAccessState(settings.data_dir)
    app.state.public_access = state
    app.state.server_settings = settings
    origins = {settings.public_url}
    if settings.environment == "development":
        origins.update(allowed_origins)

    @app.get("/api/public/session")
    def public_session(request: Request) -> JSONResponse:
        raw = request.cookies.get(COOKIE, "")
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) is None:
            raw = secrets.token_urlsafe(32)
        response = JSONResponse({
            "access_mode": "public_read_only", "csrf_token": _csrf(raw),
            "capabilities": {
                "analyze": True, "save_tests": include_academic,
                "edit_collection": False, "edit_grammar": False, "edit_recordings": False,
            },
        })
        response.set_cookie(
            COOKIE, raw, httponly=True, secure=settings.environment == "production",
            samesite="lax", path="/",
        )
        return response

    @app.middleware("http")
    async def public_workspace(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        if not include_academic and (path.startswith("/api/analyzer") or path == "/api/examples"):
            return JSONResponse({"detail": "API endpoint not found."}, 404)
        readable = path in _READ_PATHS or _READ_RESOURCE.fullmatch(path) is not None
        if request.method in ("GET", "HEAD"):
            if not readable:
                return JSONResponse({"detail": "API endpoint not found."}, 404)
        elif request.method != "POST" or path not in _POST_PATHS:
            if _READ_ONLY_RESOURCE.fullmatch(path):
                return JSONResponse({"detail": READ_ONLY_MESSAGE}, 403)
            return JSONResponse({"detail": "API endpoint not found."}, 404)
        else:
            raw = request.cookies.get(COOKIE, "")
            submitted = request.headers.get("x-csrf-token", "")
            if request.headers.get("origin") not in origins:
                return JSONResponse({"detail": "This request did not originate from the application."}, 403)
            if (re.fullmatch(r"[A-Za-z0-9_-]{43}", raw) is None or
                    re.fullmatch(r"[a-f0-9]{64}", submitted) is None or
                    not hmac.compare_digest(submitted, _csrf(raw))):
                return JSONResponse({"detail": "The request token is missing or changed. Reload the application and try again."}, 403)
        if path == "/api/health":
            return await call_next(request)
        try:
            for project in (request.headers.get("x-mboa-project"), request.query_params.get("project")):
                if project:
                    valid_id(project, default=True)
            address = request.client.host if request.client else "unknown"
            workspace = await run_in_threadpool(state.limit, address)
            token = _public_request.set(True)
            try:
                with use_workspace(workspace):
                    return await call_next(request)
            finally:
                _public_request.reset(token)
        except RateLimitExceeded as exc:
            return JSONResponse({"detail": str(exc)}, 429, headers={"Retry-After": str(exc.retry_after)})
        except CollectionError as exc:
            return JSONResponse({"detail": exc.detail}, exc.status_code)
        except Timeout:
            return JSONResponse({"detail": "The shared workspace is busy. Please try again."}, 503)
        except (OSError, sqlite3.Error, ValueError) as exc:
            logger.error("Public workspace storage failed (%s)", type(exc).__name__)
            return JSONResponse({"detail": "Shared workspace storage is temporarily unavailable. Contact the operator."}, 503)
