import hashlib
import hmac
import json
import logging
import secrets
import smtplib
import sqlite3
import ssl
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, closing, contextmanager
from contextvars import ContextVar
from email.message import EmailMessage
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

import httpx
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.concurrency import run_in_threadpool
from filelock import Timeout

from .collection import CollectionError

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "mboa_session"
OAUTH_COOKIE = "mboa_oauth"
SESSION_SECONDS = 7 * 24 * 3600
logger = logging.getLogger(__name__)
PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
_identity: ContextVar["UserIdentity | None"] = ContextVar("mboa_identity", default=None)


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MBOA_", env_file=(ROOT / ".env", ROOT / "backend" / ".env"), extra="ignore",
    )
    environment: Literal["development", "production"] = "development"
    data_dir: Path = ROOT / ".mboa"
    public_url: str = "http://127.0.0.1:8000"
    mail_mode: Literal["file", "smtp"] = "file"
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    mail_from: str = ""
    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def valid_deployment(self):
        url = urlsplit(self.public_url)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username or
                url.password or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("MBOA_PUBLIC_URL must be an HTTP(S) origin without credentials or a path.")
        if bool(self.google_client_id) != bool(self.google_client_secret.get_secret_value()):
            raise ValueError("Configure both Google client ID and client secret, or neither.")
        if self.mail_mode == "smtp" and not (self.smtp_host and self.mail_from):
            raise ValueError("SMTP delivery requires MBOA_SMTP_HOST and MBOA_MAIL_FROM.")
        if self.environment == "production":
            if url.scheme != "https" or url.hostname in ("localhost", "127.0.0.1", "::1"):
                raise ValueError("Production requires a public HTTPS origin.")
            if self.mail_mode != "smtp":
                raise ValueError("Production requires SMTP delivery, never a local mail outbox.")
        self.public_url = self.public_url.rstrip("/")
        self.data_dir = self.data_dir.absolute()
        return self


class UserIdentity(BaseModel):
    id: str
    email: str
    display_name: str
    email_verified: bool
    google_linked: bool = False


class AuthInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmailInput(AuthInput):
    email: EmailStr


class LoginInput(EmailInput):
    password: str = Field(min_length=1, max_length=128)


class RegisterInput(LoginInput):
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)


class TokenInput(AuthInput):
    token: str = Field(min_length=20, max_length=200)


class ResetInput(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class ProfileInput(AuthInput):
    display_name: str = Field(min_length=1, max_length=100)


class AuthError(Exception):
    def __init__(self, status: int, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.status = status
        self.detail = detail
        self.retry_after = retry_after


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def get_current_identity() -> UserIdentity | None:
    return _identity.get()


def private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    for item in (path, *path.parents):
        if item.is_symlink() or (getattr(item.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Private data directories must not contain filesystem links.")


class AuthStore:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        private_directory(settings.data_dir)
        self.path = settings.data_dir / "auth.sqlite3"
        if self.path.is_symlink():
            raise ValueError("The identity database must not be a filesystem link.")
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
                    password_hash TEXT, verified INTEGER NOT NULL DEFAULT 0, google_sub TEXT UNIQUE,
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tokens (
                    token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    purpose TEXT NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS limits (
                    key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth (
                    state TEXT PRIMARY KEY, browser TEXT NOT NULL, verifier TEXT NOT NULL,
                    nonce TEXT NOT NULL, user_id TEXT, expires REAL NOT NULL
                );
            """)
        self.dummy_hash = PASSWORDS.hash(secrets.token_urlsafe(24))

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            with db:
                yield db

    @staticmethod
    def identity(row: sqlite3.Row) -> UserIdentity:
        return UserIdentity(
            id=row["id"], email=row["email"], display_name=row["display_name"],
            email_verified=bool(row["verified"]), google_linked=bool(row["google_sub"]),
        )

    def registered_user_count(self) -> int:
        with self.connection() as db:
            return db.execute("SELECT count(*) FROM users").fetchone()[0]

    def throttle(self, key: str, maximum: int, seconds: int) -> None:
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM limits WHERE expires <= ?", (now,))
            row = db.execute("SELECT * FROM limits WHERE key=?", (key,)).fetchone()
            if row and row["count"] >= maximum:
                raise AuthError(429, "Too many requests. Please try again later.", max(1, int(row["expires"] - now)))
            db.execute(
                "INSERT INTO limits VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1",
                (key, now + seconds),
            )

    def session(self, raw: str) -> UserIdentity | None:
        if not raw or len(raw) > 200:
            return None
        with self.connection() as db:
            row = db.execute(
                "SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id "
                "WHERE sessions.token=? AND sessions.expires>? AND users.verified=1",
                (digest(raw), time.time()),
            ).fetchone()
            return self.identity(row) if row else None

    def new_session(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires<=?", (time.time(),))
            db.execute("INSERT INTO sessions VALUES (?,?,?)", (digest(raw), user_id, time.time() + SESSION_SECONDS))
            db.execute(
                "DELETE FROM sessions WHERE user_id=? AND token NOT IN "
                "(SELECT token FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT 10)",
                (user_id, user_id),
            )
        return raw

    def issue_token(self, user_id: str, purpose: str) -> str:
        raw = secrets.token_urlsafe(32)
        with self.connection() as db:
            db.execute("DELETE FROM tokens WHERE expires<=? OR (user_id=? AND purpose=?)", (time.time(), user_id, purpose))
            db.execute("INSERT INTO tokens VALUES (?,?,?,?)", (digest(raw), user_id, purpose, time.time() + 3600))
        return raw

    def consume_token(self, raw: str, purpose: str, password: str | None = None) -> None:
        password_hash = PASSWORDS.hash(password) if password is not None else None
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            token = db.execute(
                "SELECT * FROM tokens WHERE token=? AND purpose=? AND expires>?",
                (digest(raw), purpose, time.time()),
            ).fetchone()
            if not token:
                raise AuthError(400, "This link is invalid or expired. Request a new one.")
            user_id = token["user_id"]
            if purpose == "verify":
                db.execute("UPDATE users SET verified=1 WHERE id=?", (user_id,))
            else:
                db.execute("UPDATE users SET password_hash=?, verified=1 WHERE id=?", (password_hash, user_id))
                db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
            db.execute("DELETE FROM tokens WHERE user_id=?", (user_id,))


def deliver_email(settings: AuthSettings, address: str, subject: str, text: str) -> None:
    message = EmailMessage()
    message["From"] = settings.mail_from or "Mboa <no-reply@localhost>"
    message["To"] = address
    message["Subject"] = subject
    message.set_content(text)
    if settings.mail_mode == "file":
        directory = settings.data_dir / "mail"
        private_directory(directory)
        path = directory / f"{uuid4().hex}.eml"
        with path.open("xb") as handle:
            handle.write(message.as_bytes())
        path.chmod(0o600)
        return
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        logger.error("Account email delivery failed (%s)", type(exc).__name__)
        raise AuthError(503, "Account email delivery is unavailable. Please try again later.") from exc


def install_auth(
    app: FastAPI, settings: AuthSettings, *,
    workspace_context: Callable[[UserIdentity, Request], AbstractAsyncContextManager[object]] | None = None,
    allowed_origins: list[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    mailer: Callable[[str, str, str], None] | None = None,
) -> AuthStore:
    store = AuthStore(settings)
    app.state.auth_store = store
    app.state.auth_settings = settings
    origins = {settings.public_url}
    if settings.environment == "development":
        origins.update(allowed_origins or [])
    send_mail = mailer or (lambda address, subject, text: deliver_email(settings, address, subject, text))
    secure = settings.environment == "production"
    anonymous_paths = {
        "/api/health", "/api/auth/session", "/api/auth/register", "/api/auth/login",
        "/api/auth/verify-email", "/api/auth/resend-verification", "/api/auth/forgot-password",
        "/api/auth/reset-password", "/api/auth/google/start", "/api/auth/google/callback",
    }

    def error_response(exc: AuthError) -> JSONResponse:
        headers = {"Retry-After": str(exc.retry_after)} if exc.retry_after is not None else {}
        return JSONResponse({"detail": exc.detail}, exc.status, headers=headers)

    @app.exception_handler(AuthError)
    async def auth_error(_request: Request, exc: AuthError):
        return error_response(exc)

    def csrf(raw: str) -> str:
        return digest("csrf:" + raw)

    def envelope(user: UserIdentity | None, raw: str = "") -> dict:
        return {
            "user": user.model_dump() if user else None,
            "csrf_token": csrf(raw) if user else None,
            "google_enabled": bool(settings.google_client_id), "email_enabled": True,
            "development_mail": settings.mail_mode == "file",
        }

    @app.middleware("http")
    async def authentication(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or request.method == "OPTIONS":
            return await call_next(request)
        raw = request.cookies.get(COOKIE, "")
        try:
            user = await run_in_threadpool(store.session, raw)
            if path not in anonymous_paths and user is None:
                raise AuthError(401, "Sign in to access the shared workspace.")
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                if request.headers.get("origin") not in origins:
                    raise AuthError(403, "This request did not originate from the application.")
                if user and path not in anonymous_paths:
                    if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), csrf(raw)):
                        raise AuthError(403, "Your session changed. Reload the application before making changes.")
            if user:
                await run_in_threadpool(store.throttle, f"api:{user.id}", 240, 60)
            else:
                ip = request.client.host if request.client else "unknown"
                await run_in_threadpool(store.throttle, f"anonymous:{digest(ip)}", 120, 60)
            request.state.user = user
            token = _identity.set(user)
            try:
                if user and workspace_context is not None and not path.startswith("/api/auth/"):
                    async with workspace_context(user, request):
                        return await call_next(request)
                return await call_next(request)
            finally:
                _identity.reset(token)
        except AuthError as exc:
            return error_response(exc)
        except CollectionError as exc:
            return JSONResponse({"detail": exc.detail}, exc.status_code)
        except Timeout:
            return JSONResponse({"detail": "The workspace is busy. Please try again."}, 503)
        except sqlite3.Error as exc:
            logger.error("Identity storage failed (%s)", type(exc).__name__)
            return JSONResponse({"detail": "Account storage is temporarily unavailable."}, 503)
        except (OSError, ValueError) as exc:
            logger.error("Account or workspace storage failed (%s)", type(exc).__name__)
            return JSONResponse({"detail": "Account or workspace storage is temporarily unavailable."}, 503)

    async def auth_limit(request: Request, email: str, action: str, maximum: int = 8):
        ip = request.client.host if request.client else "unknown"
        await run_in_threadpool(store.throttle, f"{action}:ip:{digest(ip)}", maximum * 3, 3600)
        await run_in_threadpool(store.throttle, f"{action}:email:{digest(email.casefold())}", maximum, 3600)

    async def mail_link(address: str, user_id: str, purpose: str):
        raw = await run_in_threadpool(store.issue_token, user_id, purpose)
        route = "verify-email" if purpose == "verify" else "reset-password"
        link = f"{settings.public_url}/#{route}?token={raw}"
        await run_in_threadpool(
            send_mail, address, "Verify your Mboa email" if purpose == "verify" else "Reset your Mboa password",
            f"Open Mboa to {'verify your email' if purpose == 'verify' else 'reset your password'}:\n\n"
            f"{link}\n\nThis single-use link expires in one hour. Ignore it if you did not request it.",
        )

    def set_session(response: Response, raw: str):
        response.set_cookie(COOKIE, raw, max_age=SESSION_SECONDS, httponly=True, secure=secure, samesite="lax", path="/")

    @app.get("/api/auth/session")
    async def session(request: Request):
        return envelope(request.state.user, request.cookies.get(COOKIE, ""))

    @app.post("/api/auth/register", status_code=202)
    async def register(payload: RegisterInput, request: Request):
        email = str(payload.email).casefold()
        if not payload.display_name.strip():
            raise AuthError(422, "Enter your name.")
        await auth_limit(request, email, "register", 4)
        password_hash = await run_in_threadpool(PASSWORDS.hash, payload.password)

        def create():
            with store.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT id,verified FROM users WHERE email=?", (email,)).fetchone()
                if existing:
                    return None
                user_id = str(uuid4())
                db.execute(
                    "INSERT INTO users(id,email,display_name,password_hash,created) VALUES (?,?,?,?,?)",
                    (user_id, email, payload.display_name.strip(), password_hash, time.time()),
                )
                return user_id

        user_id = await run_in_threadpool(create)
        if user_id:
            await mail_link(email, user_id, "verify")
        return {"message": "If this address can be registered, a verification link has been sent. Check your email or request another link."}

    @app.post("/api/auth/login")
    async def login(payload: LoginInput, request: Request, response: Response):
        email = str(payload.email).casefold()
        await auth_limit(request, email, "login", 15)

        def authenticate():
            with store.connection() as db:
                row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            try:
                PASSWORDS.verify(row["password_hash"] if row and row["password_hash"] else store.dummy_hash, payload.password)
            except (VerificationError, InvalidHashError):
                raise AuthError(401, "The email or password is incorrect.")
            if row is None or not row["password_hash"]:
                raise AuthError(401, "The email or password is incorrect.")
            if not row["verified"]:
                raise AuthError(403, "Verify your email before signing in. You can request another verification link.")
            return store.identity(row)

        user = await run_in_threadpool(authenticate)
        raw = await run_in_threadpool(store.new_session, user.id)
        set_session(response, raw)
        return envelope(user, raw)

    @app.post("/api/auth/logout", status_code=204)
    async def logout(request: Request, response: Response):
        def remove():
            with store.connection() as db:
                db.execute("DELETE FROM sessions WHERE token=?", (digest(request.cookies.get(COOKIE, "")),))
        await run_in_threadpool(remove)
        response.delete_cookie(COOKIE, path="/", httponly=True, secure=secure, samesite="lax")

    @app.post("/api/auth/verify-email")
    async def verify(payload: TokenInput):
        await run_in_threadpool(store.consume_token, payload.token, "verify")
        return {"message": "Email verified. You can now sign in."}

    @app.post("/api/auth/resend-verification")
    async def resend(payload: EmailInput, request: Request):
        email = str(payload.email).casefold()
        await auth_limit(request, email, "verify", 4)
        with store.connection() as db:
            row = db.execute("SELECT id FROM users WHERE email=? AND verified=0", (email,)).fetchone()
        if row:
            await mail_link(email, row["id"], "verify")
        return {"message": "If verification is needed, a new link has been sent."}

    @app.post("/api/auth/forgot-password")
    async def forgot(payload: EmailInput, request: Request):
        email = str(payload.email).casefold()
        await auth_limit(request, email, "reset", 4)
        with store.connection() as db:
            row = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if row:
            await mail_link(email, row["id"], "reset")
        return {"message": "If an account exists, a password reset link has been sent."}

    @app.post("/api/auth/reset-password")
    async def reset(payload: ResetInput):
        await run_in_threadpool(store.consume_token, payload.token, "reset", payload.password)
        return {"message": "Password changed. All previous sessions were signed out."}

    @app.patch("/api/auth/profile")
    async def profile(payload: ProfileInput, request: Request):
        name = payload.display_name.strip()
        if not name:
            raise AuthError(422, "Enter your name.")
        with store.connection() as db:
            db.execute("UPDATE users SET display_name=? WHERE id=?", (name, request.state.user.id))
        user = request.state.user.model_copy(update={"display_name": name})
        return envelope(user, request.cookies.get(COOKIE, ""))

    @app.get("/api/auth/google/start")
    async def google_start(request: Request, link: bool = False):
        if not settings.google_client_id:
            raise AuthError(503, "Google sign-in has not been configured by the operator.")
        if link and not request.state.user:
            raise AuthError(401, "Sign in before linking Google.")
        await auth_limit(request, "", "google", 20)
        state, browser, verifier, nonce = [secrets.token_urlsafe(32) for _ in range(4)]
        with store.connection() as db:
            db.execute("DELETE FROM oauth WHERE expires<=?", (time.time(),))
            db.execute(
                "INSERT INTO oauth VALUES (?,?,?,?,?,?)",
                (digest(state), digest(browser), verifier, nonce, request.state.user.id if link else None, time.time() + 600),
            )
        import base64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        parameters = {
            "client_id": settings.google_client_id, "redirect_uri": settings.public_url + "/api/auth/google/callback",
            "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
        }
        response = RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(parameters), 302)
        response.set_cookie(OAUTH_COOKIE, browser, max_age=600, httponly=True, secure=secure, samesite="lax", path="/api/auth/google")
        return response

    @app.get("/api/auth/google/callback")
    async def google_callback(request: Request, state: str = "", code: str = "", error: str = ""):
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            saved = db.execute("SELECT * FROM oauth WHERE state=? AND expires>?", (digest(state), time.time())).fetchone()
            if not saved or not hmac.compare_digest(saved["browser"], digest(request.cookies.get(OAUTH_COOKIE, ""))):
                raise AuthError(400, "Google sign-in expired or belongs to another browser. Start again.")
            db.execute("DELETE FROM oauth WHERE state=?", (digest(state),))
        if error or not code or len(code) > 4096:
            return RedirectResponse(settings.public_url + "/#signin?error=google-cancelled", 303)
        if saved["user_id"] and (not request.state.user or request.state.user.id != saved["user_id"]):
            raise AuthError(403, "The account changed. Start Google linking again.")
        stage = "token_exchange"
        try:
            async with httpx.AsyncClient(transport=transport, timeout=15) as client:
                tokens = await client.post("https://oauth2.googleapis.com/token", data={
                    "code": code, "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret.get_secret_value(),
                    "redirect_uri": settings.public_url + "/api/auth/google/callback",
                    "grant_type": "authorization_code", "code_verifier": saved["verifier"],
                })
                tokens.raise_for_status()
                stage = "signing_keys"
                keys = await client.get("https://www.googleapis.com/oauth2/v3/certs")
                keys.raise_for_status()
            stage = "identity_token"
            encoded = tokens.json()["id_token"]
            header = jwt.get_unverified_header(encoded)
            keyset = jwt.PyJWKSet.from_json(keys.text)
            signing_key = next(key for key in keyset.keys if key.key_id == header.get("kid") and key.algorithm_name == "RS256")
            claims = jwt.decode(
                encoded, signing_key.key, algorithms=["RS256"], audience=settings.google_client_id,
                issuer=["accounts.google.com", "https://accounts.google.com"],
                options={"require": ["exp", "iat", "sub", "aud", "iss", "nonce", "email", "email_verified"]},
            )
            if (claims["nonce"] != saved["nonce"] or claims["email_verified"] is not True or
                    not isinstance(claims["sub"], str) or len(claims["sub"]) > 255):
                raise ValueError("Invalid identity")
            email = str(EmailInput(email=claims["email"]).email).casefold()
        except httpx.HTTPStatusError as exc:
            try:
                failure = exc.response.json()
            except ValueError:
                provider_error = "invalid_json"
            else:
                reported = failure.get("error") if isinstance(failure, dict) else None
                provider_error = reported if isinstance(reported, str) and reported in {
                    "invalid_client", "invalid_grant", "invalid_request", "unauthorized_client",
                    "unsupported_grant_type", "redirect_uri_mismatch", "access_denied",
                    "temporarily_unavailable", "server_error",
                } else "unrecognized"
            logger.warning(
                "Google sign-in HTTP failure: stage=%s status=%s error=%s",
                stage, exc.response.status_code, provider_error,
            )
            detail = "Google sign-in could not be verified. Please start again."
            if stage == "token_exchange" and provider_error in {"invalid_client", "unauthorized_client"}:
                detail = "Google rejected the configured OAuth client. The operator must check the client ID and client secret."
            elif stage == "token_exchange" and provider_error == "invalid_grant":
                detail = "Google rejected or expired this authorization code. Start a new Google sign-in from Mboa; do not refresh this callback page."
            elif stage == "token_exchange" and provider_error == "redirect_uri_mismatch":
                detail = "Google rejected the callback URL. The operator must register the exact Mboa callback URL for this OAuth client."
            elif exc.response.status_code == 429 or exc.response.status_code >= 500:
                detail = "Google is temporarily unavailable. Please try signing in again later."
            raise AuthError(502, detail) from exc
        except (httpx.HTTPError, jwt.PyJWTError, KeyError, TypeError, ValueError, StopIteration) as exc:
            logger.warning("Google identity verification failed (%s; stage=%s)", type(exc).__name__, stage)
            raise AuthError(502, "Google sign-in could not be verified. Please start again.") from exc

        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM users WHERE google_sub=?", (claims["sub"],)).fetchone()
            if saved["user_id"]:
                if row and row["id"] != saved["user_id"]:
                    raise AuthError(409, "That Google account is linked to another account.")
                db.execute("UPDATE users SET google_sub=? WHERE id=?", (claims["sub"], saved["user_id"]))
                user_id = saved["user_id"]
            elif row:
                user_id = row["id"]
            else:
                existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if existing:
                    return RedirectResponse(settings.public_url + "/#signin?error=google-link-required", 303)
                user_id = str(uuid4())
                name = claims.get("name", email.split("@")[0])
                db.execute(
                    "INSERT INTO users(id,email,display_name,verified,google_sub,created) VALUES (?,?,?,1,?,?)",
                    (user_id, email, str(name)[:100], claims["sub"], time.time()),
                )
        raw = await run_in_threadpool(store.new_session, user_id)
        response = RedirectResponse(settings.public_url + "/#translator", 303)
        set_session(response, raw)
        response.delete_cookie(OAUTH_COOKIE, path="/api/auth/google")
        return response

    return store
