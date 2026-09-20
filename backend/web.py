import logging
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse
from starlette.routing import Match, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

JSON_REQUEST_LIMIT = 1024 * 1024
MEDIA_REQUEST_LIMIT = 12 * 1024 * 1024 + 65536
BACKUP_REQUEST_LIMIT = 32 * 1024 * 1024 + 65536


class PrivateQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


class WebBoundaryMiddleware:
    def __init__(self, app: ASGIApp, *, production: bool = False):
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        api_request = path == "/api" or path.startswith("/api/")

        async def guarded_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                headers["Cross-Origin-Opener-Policy"] = "same-origin"
                headers["Cross-Origin-Resource-Policy"] = "same-origin"
                headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
                headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob:; media-src 'self' blob:; font-src 'self'; "
                    "connect-src 'self'; object-src 'none'; base-uri 'self'; "
                    "frame-ancestors 'none'; form-action 'self'"
                )
                if api_request:
                    if "no-store" not in headers.get("Cache-Control", ""):
                        headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
                if self.production:
                    headers["Strict-Transport-Security"] = "max-age=31536000"
            await send(message)

        if len(path) > 4096 or len(scope.get("query_string", b"")) > 8192:
            await JSONResponse(
                {"detail": "The request URL is too long."}, status_code=414,
            )(scope, receive, guarded_send)
            return

        limit = JSON_REQUEST_LIMIT
        if path == "/api/workspace/backups/preview":
            limit = BACKUP_REQUEST_LIMIT
        elif path.startswith("/api/import") or path.endswith("/audio"):
            limit = MEDIA_REQUEST_LIMIT

        lengths = Headers(scope=scope).getlist("content-length")
        if lengths:
            try:
                if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdecimal():
                    raise ValueError("Invalid content length")
                content_length = int(lengths[0])
            except ValueError:
                await JSONResponse(
                    {"detail": "Invalid request size."}, status_code=400,
                )(scope, receive, guarded_send)
                return
            if api_request and content_length > limit:
                await JSONResponse(
                    {"detail": "The request exceeds the permitted size."}, status_code=413,
                )(scope, receive, guarded_send)
                return

        received = 0

        async def guarded_receive() -> Message:
            nonlocal received
            message = await receive()
            if api_request and message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(413, "The request exceeds the permitted size.")
            return message

        await self.app(scope, guarded_receive, guarded_send)


def install_web(
    app: FastAPI, *, frontend_dir: Path, production: bool = False,
    public_url: str = "http://127.0.0.1:8000",
) -> None:
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, PrivateQueryFilter) for item in logger.filters):
        logger.addFilter(PrivateQueryFilter())
    if production:
        hostname = urlsplit(public_url).hostname
        if not hostname:
            raise ValueError("A valid public URL is required for hosted deployment.")
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(
            TrustedHostMiddleware, allowed_hosts=[hostname, "127.0.0.1", "localhost"],
            www_redirect=False,
        )
    app.add_middleware(WebBoundaryMiddleware, production=production)
    if frontend_dir.joinpath("index.html").is_file():
        @app.api_route("/api/{unmatched:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
        async def unknown_api(unmatched: str, request: Request):
            allowed = {
                method for route in app.routes if isinstance(route, Route)
                and route.matches(request.scope)[0] == Match.PARTIAL
                for method in route.methods or set()
            }
            if allowed:
                return JSONResponse(
                    {"detail": "Method Not Allowed"}, status_code=405,
                    headers={"Allow": ", ".join(sorted(allowed))},
                )
            return JSONResponse({"detail": "API endpoint not found."}, status_code=404)
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    elif production:
        raise ValueError("The frontend build is missing. Build the web application before deployment.")
