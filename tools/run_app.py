"""Start Camfranglais's website and API together on one origin."""

import argparse
import ipaddress
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parents[1]


class LaunchError(Exception):
    pass


class LaunchSettings(Protocol):
    environment: str
    public_url: str
    model_fields_set: set[str]


def _port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("The port must be a number between 1 and 65535.") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("The port must be between 1 and 65535.")
    return port


def is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def load_settings() -> LaunchSettings:
    try:
        from pydantic import ValidationError
        from backend.config import ServerSettings
    except ImportError as exc:
        raise LaunchError(
            "Backend dependencies are missing. Install requirements.txt in the project's virtual environment."
        ) from exc
    try:
        return ServerSettings()
    except ValidationError as exc:
        messages = [
            f"{'.'.join(str(item) for item in error['loc']) or 'configuration'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise LaunchError("Invalid application configuration: " + "; ".join(messages)) from exc


def ensure_frontend(root: Path, *, build: bool) -> None:
    frontend = root / "frontend"
    if build:
        if not (frontend / "node_modules").is_dir():
            raise LaunchError("Frontend dependencies are missing. Run npm ci in the frontend directory.")
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        if npm is None:
            raise LaunchError("Node.js/npm is required to build the frontend. Install a supported Node.js LTS.")
        try:
            subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
        except subprocess.CalledProcessError as exc:
            raise LaunchError("The frontend build failed. Resolve the reported errors before starting.") from exc
    if not (frontend / "dist" / "index.html").is_file():
        raise LaunchError("The frontend build is missing. Run this launcher with --build.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=_port, default=8000)
    parser.add_argument("--build", action="store_true", help="Type-check and rebuild the frontend before starting.")
    parser.add_argument("--reload", action="store_true", help="Reload backend code during local development only.")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 11):
            raise LaunchError("Python 3.11 or newer is required.")
        settings = load_settings()
        production = settings.environment == "production"
        if not is_loopback(args.host) and not production:
            raise LaunchError(
                "Non-loopback listening requires MBOA_ENVIRONMENT=production and valid hosted settings."
            )
        if production and args.reload:
            raise LaunchError("Automatic code reload is not permitted in production.")
        ensure_frontend(ROOT, build=args.build)
        if not production and "public_url" not in settings.model_fields_set:
            hostname = "localhost" if args.host.casefold() == "localhost" else "127.0.0.1"
            os.environ["MBOA_PUBLIC_URL"] = f"http://{hostname}:{args.port}"
        import uvicorn
        uvicorn.run(
            "backend.main:app", host=args.host, port=args.port, reload=args.reload,
            app_dir=str(ROOT), proxy_headers=production,
        )
    except (LaunchError, OSError) as exc:
        print(f"Camfranglais could not start: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
