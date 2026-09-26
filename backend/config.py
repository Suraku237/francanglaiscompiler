from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MBOA_", env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8", extra="ignore",
    )

    environment: Literal["development", "production"] = "development"
    data_dir: Path = BACKEND_DIR.parent / ".mboa"
    public_url: str = "http://127.0.0.1:8000"

    @model_validator(mode="after")
    def valid_server(self):
        url = urlsplit(self.public_url)
        if (url.scheme not in ("http", "https") or not url.hostname or url.username or
                url.password or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("MBOA_PUBLIC_URL must be an HTTP(S) origin without credentials or a path.")
        if self.environment == "production" and (
            url.scheme != "https" or url.hostname in ("localhost", "127.0.0.1", "::1")
        ):
            raise ValueError("Production requires a public HTTPS origin.")
        self.public_url = self.public_url.rstrip("/")
        self.data_dir = self.data_dir.absolute()
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(BACKEND_DIR.parent / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
