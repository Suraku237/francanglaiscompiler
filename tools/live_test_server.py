"""Run the isolated full-stack browser fixture; never use this as a deployment command."""

import argparse
import os
import shutil
import tempfile
from pathlib import Path

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    root = args.data_dir.resolve()
    if (root.parent != Path(tempfile.gettempdir()).resolve() or
            not root.name.startswith("mboa-live-") or not root.is_dir() or any(root.iterdir())):
        parser.error("The browser fixture requires its own new, empty mboa-live-* temporary directory.")
    os.environ.update({
        "MBOA_DATA_DIR": str(root), "MBOA_ENVIRONMENT": "development",
        "MBOA_MAIL_MODE": "file", "GEMINI_API_KEY": " ",
        "MBOA_GOOGLE_CLIENT_ID": "", "MBOA_GOOGLE_CLIENT_SECRET": "",
        "MBOA_PUBLIC_URL": f"http://127.0.0.1:{args.port}",
    })
    try:
        uvicorn.run("backend.main:app", host="127.0.0.1", port=args.port, proxy_headers=False)
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
