"""Measure real private API/SQLite operations using an isolated synthetic account."""

import argparse
import hashlib
import json
import math
import platform
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from backend.auth import COOKIE, AuthSettings, digest
from backend.config import Settings
from backend.main import create_app
from backend.workspaces import WorkspaceStore
from tools.benchmark_collector import measure, physical_memory_bytes, synthetic_entries

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    ROOT / "backend" / "auth.py", ROOT / "backend" / "workspaces.py",
    ROOT / "backend" / "workspace_backups.py", ROOT / "backend" / "main.py",
    ROOT / "backend" / "collection.py", ROOT / "data_collector" / "dataset.py",
    Path(__file__).resolve(), ROOT / "tools" / "benchmark_collector.py",
)


def run_benchmark(*, rows: int = 1000, text_characters: int = 500, runs: int = 20, limit_ms: float = 1000) -> dict:
    if not 1 <= runs <= 60:
        raise ValueError("Use 1-60 measured runs so the benchmark respects normal account request limits.")
    if not math.isfinite(limit_ms) or limit_ms <= 0:
        raise ValueError("The local p95 budget must be positive and finite.")
    entries = synthetic_entries(rows, text_characters)
    for entry in entries:
        entry.update(id=str(uuid4()), category="Customer Service", notes="Synthetic private API performance fixture.")
    hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in SOURCES}
    provider_calls = []

    def reject_provider(request: httpx.Request):
        provider_calls.append(request)
        raise AssertionError("The local benchmark must never contact a provider.")

    with tempfile.TemporaryDirectory(prefix="mboa-workspace-benchmark-") as directory:
        root = Path(directory)
        accounts = AuthSettings(
            environment="development", data_dir=root, public_url="http://testserver",
            mail_mode="file", google_client_id="", google_client_secret=SecretStr(""),
        )
        app = create_app(
            Settings(gemini_api_key=SecretStr(" ")), auth_settings=accounts,
            transport=httpx.MockTransport(reject_provider),
        )
        user_id = str(uuid4())
        auth = app.state.auth_store
        with auth.connection() as db:
            db.execute(
                "INSERT INTO users(id,email,display_name,verified,created) VALUES (?,?,?,?,?)",
                (user_id, "benchmark@example.invalid", "Synthetic benchmark", 1, time.time()),
            )
        store = WorkspaceStore(root, user_id)
        store.save_all(entries)
        raw = auth.new_session(user_id)
        with TestClient(app, headers={"Origin": "http://testserver", "X-CSRF-Token": digest("csrf:" + raw)}) as client:
            client.cookies.set(COOKIE, raw)

            def read_entries(query: str, count: int):
                response = client.get("/api/dataset", params={"query": query})
                if response.status_code != 200:
                    raise RuntimeError(f"Read benchmark failed with HTTP {response.status_code}.")
                data = response.json()
                if data["total"] != rows or len(data["entries"]) != count:
                    raise RuntimeError("The measured response did not contain the expected project data.")

            def create_backup():
                response = client.post("/api/workspace/backups")
                if response.status_code != 201 or response.json()["size"] <= 0:
                    raise RuntimeError(f"Backup benchmark failed with HTTP {response.status_code}.")

            measurements = {
                "list_all": measure(lambda: read_entries("", rows), lambda: None, runs),
                "search_one": measure(lambda: read_entries(f"Synthetic benchmark entry {rows - 1}:", 1), lambda: None, runs),
                "create_verified_backup": measure(create_backup, lambda: None, runs),
            }
        if store.load_all() != entries or provider_calls:
            raise RuntimeError("The benchmark changed terminology or attempted external processing.")
    if any(hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path.relative_to(ROOT))] for path in SOURCES):
        raise RuntimeError("Application source changed during measurement; rerun against stable source.")
    p95_values: list[float] = []
    for measurement in measurements.values():
        p95 = measurement["p95_ms"]
        if not isinstance(p95, (int, float)):
            raise RuntimeError("The benchmark did not produce numeric p95 measurements.")
        p95_values.append(p95)
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixture": {"rows": rows, "text_characters": text_characters, "synthetic": True, "accounts": 1},
        "method": "One warm-up, then nearest-rank p95 of real authenticated ASGI TestClient requests and response checks",
        "limit_ms": limit_ms,
        "passed_on_this_machine": all(p95 <= limit_ms for p95 in p95_values),
        "environment": {
            "platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "physical_memory_bytes": physical_memory_bytes(),
        },
        "source_sha256": hashes,
        "measurements": measurements,
        "limitations": [
            "One synthetic account on this machine, not public concurrent-user capacity or an 8 GB reference-machine certification.",
            "Includes real SQLite, auth checks, serialization and verified ZIP writes; excludes TCP, TLS and browser rendering.",
            "No provider, SMTP, Google, microphone or real business data is used.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--text-characters", type=int, default=500)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--limit-ms", type=float, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_benchmark(rows=args.rows, text_characters=args.text_characters, runs=args.runs, limit_ms=args.limit_ms)
        serialized = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Private workspace benchmark failed: {exc}\n")
    print(serialized, end="")
    return 0 if report["passed_on_this_machine"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
