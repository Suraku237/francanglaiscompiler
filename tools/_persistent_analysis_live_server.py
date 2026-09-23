from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI

from backend.web import install_web
from tools.live_test_server import main


def install_preview(
    app: FastAPI, *, frontend_dir: Path, production: bool = False,
    public_url: str = "http://127.0.0.1:8000",
) -> None:
    preview = Path(__file__).resolve().parents[1] / "frontend" / ".playwright" / "persistent-analysis-build"
    if not preview.joinpath("index.html").is_file():
        raise RuntimeError("Build the isolated persistent-analysis preview before running live tests.")
    install_web(app, frontend_dir=preview, production=production, public_url=public_url)


if __name__ == "__main__":
    with patch("backend.web.install_web", install_preview):
        main()
