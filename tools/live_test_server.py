"""Run the isolated full-stack browser fixture; never use this as a deployment command."""

import argparse
import os
import shutil
import sys
import tempfile
from contextlib import nullcontext
from pathlib import Path
from threading import Thread
from unittest.mock import patch

import uvicorn
from fastapi import FastAPI

from backend.web import install_web


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--frontend-dir", type=Path)
    parser.add_argument("--stop-on-stdin", action="store_true")
    args = parser.parse_args()
    root = args.data_dir.resolve()
    if (root.parent != Path(tempfile.gettempdir()).resolve() or
            not root.name.startswith("mboa-live-") or not root.is_dir() or any(root.iterdir())):
        parser.error("The browser fixture requires its own new, empty mboa-live-* temporary directory.")
    os.environ.update({
        "MBOA_DATA_DIR": str(root), "MBOA_ENVIRONMENT": "development",
        "MBOA_MAIL_MODE": "file",
        "MBOA_GOOGLE_CLIENT_ID": "", "MBOA_GOOGLE_CLIENT_SECRET": "",
        "MBOA_PUBLIC_URL": f"http://127.0.0.1:{args.port}",
    })

    def install_staged_web(app: FastAPI, *, frontend_dir: Path, production: bool = False,
                           public_url: str = "http://127.0.0.1:8000") -> None:
        staged = args.frontend_dir
        if staged is None or not (staged / "index.html").is_file():
            raise ValueError("The requested live-test frontend build is missing.")
        install_web(app, frontend_dir=staged, production=production, public_url=public_url)

    server = uvicorn.Server(uvicorn.Config(
        "backend.main:app", host="127.0.0.1", port=args.port, proxy_headers=False,
    ))

    def stop_after_parent_exits() -> None:
        sys.stdin.read()
        server.should_exit = True

    if args.stop_on_stdin:
        Thread(target=stop_after_parent_exits, daemon=True).start()
    try:
        with patch("backend.web.install_web", install_staged_web) if args.frontend_dir else nullcontext():
            server.run()
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
