"""Measure the real desktop search/Stats handlers against isolated synthetic data."""

import argparse
import ctypes
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import tempfile
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from data_collector import dataset


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_uint32), ("load", ctypes.c_uint32),
        ("total_physical", ctypes.c_uint64), ("available_physical", ctypes.c_uint64),
        ("total_page_file", ctypes.c_uint64), ("available_page_file", ctypes.c_uint64),
        ("total_virtual", ctypes.c_uint64), ("available_virtual", ctypes.c_uint64),
        ("available_extended_virtual", ctypes.c_uint64),
    ]


def physical_memory_bytes() -> int:
    if os.name == "nt":
        memory = _MemoryStatus()
        memory.length = ctypes.sizeof(memory)
        query = ctypes.WinDLL("kernel32", use_last_error=True).GlobalMemoryStatusEx
        query.argtypes = [ctypes.POINTER(_MemoryStatus)]
        query.restype = ctypes.c_int
        if not query(ctypes.byref(memory)):
            raise ctypes.WinError(ctypes.get_last_error())
        return memory.total_physical
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")


def nearest_rank_p95(samples: Sequence[float]) -> float:
    if not samples or any(not math.isfinite(sample) or sample < 0 for sample in samples):
        raise ValueError("Supply finite, non-negative timing samples.")
    ordered = sorted(samples)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def synthetic_entries(rows: int, text_characters: int) -> list[dict[str, str]]:
    if not 1 <= rows <= 10000 or not 32 <= text_characters <= 4000:
        raise ValueError("Use 1-10,000 rows and 32-4,000 text characters.")
    entries = []
    for index in range(rows):
        prefix = f"Synthetic benchmark entry {index}: "
        entry = {field: "" for field in dataset.FIELDNAMES}
        entry.update(
            id=f"benchmark-{index}",
            text=(prefix + "x" * text_characters)[:text_characters],
            entry_type=dataset.ENTRY_TYPES[index % len(dataset.ENTRY_TYPES)],
            category=dataset.CATEGORIES[index % len(dataset.CATEGORIES)],
            notes="Synthetic performance fixture; not fieldwork.",
            contributor="Synthetic fixture",
            language="unspecified", review_status="unreviewed",
            timestamp="2000-01-01T00:00:00+00:00",
        )
        entries.append(entry)
    return entries


def measure(refresh: Callable[[], object], flush: Callable[[], object], runs: int) -> dict[str, object]:
    if not 1 <= runs <= 100:
        raise ValueError("Use 1-100 measured runs.")
    refresh()
    flush()
    samples = []
    for _ in range(runs):
        start = time.perf_counter_ns()
        refresh()
        flush()
        samples.append((time.perf_counter_ns() - start) / 1_000_000)
    return {
        "warmups": 1, "runs": runs, "samples_ms": samples,
        "p95_ms": nearest_rank_p95(samples),
        "mean_ms": statistics.fmean(samples),
        "min_ms": min(samples), "max_ms": max(samples),
    }


def run_benchmark(
    *, rows: int = 1000, text_characters: int = 500, runs: int = 20, limit_ms: float = 1000,
) -> dict[str, object]:
    if not math.isfinite(limit_ms) or limit_ms <= 0:
        raise ValueError("The p95 limit must be a positive, finite number of milliseconds.")
    if not 1 <= runs <= 100:
        raise ValueError("Use 1-100 measured runs.")
    entries = synthetic_entries(rows, text_characters)
    project_root = Path(__file__).resolve().parents[1]
    hashes = {
        name: hashlib.sha256((project_root / "data_collector" / name).read_bytes()).hexdigest()
        for name in ("App.py", "dataset.py", "audio_utils.py")
    }
    from data_collector import App as desktop

    if desktop.dataset is not dataset:
        raise RuntimeError("The collector does not share the isolated storage module; refusing to benchmark.")

    with tempfile.TemporaryDirectory(prefix="mboa-desktop-benchmark-") as temporary:
        root = Path(temporary)
        with (
            patch.object(dataset, "DATASET_PATH", str(root / "dataset.csv")),
            patch.object(dataset, "AUDIO_DIR", str(root / "audio")),
        ):
            dataset.save_all(entries)
            original_csv = (root / "dataset.csv").read_bytes()
            app = desktop.App()
            try:
                app.title("Synthetic collector benchmark - do not interact")
                app.geometry("920x780")
                app.tabs.set(desktop.BROWSE_TAB)
                app.search_entry.delete(0, "end")
                app.search_entry.insert(0, "Synthetic benchmark")
                app.update()
                search = measure(app._refresh_browse_list, app.update_idletasks, runs)
                if len(app.tree.get_children()) != rows:
                    raise RuntimeError("The search benchmark did not display every matching fixture row.")
                app.tabs.set(desktop.STATS_TAB)
                app.update()
                stats = measure(app._refresh_stats, app.update_idletasks, runs)
                if not str(app.stats_total_label.cget("text")).endswith(str(rows)):
                    raise RuntimeError("The Stats benchmark displayed an unexpected total.")
                tk_version = str(app.tk.call("info", "patchlevel"))
                if (root / "dataset.csv").read_bytes() != original_csv:
                    raise RuntimeError("A supposedly read-only benchmark changed its fixture CSV.")
            finally:
                app.destroy()
    for name, expected in hashes.items():
        if hashlib.sha256((project_root / "data_collector" / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError("Collector source changed during measurement; repeat with stable source.")
    search_p95 = search["p95_ms"]
    stats_p95 = stats["p95_ms"]
    if not isinstance(search_p95, (float, int)) or not isinstance(stats_p95, (float, int)):
        raise RuntimeError("The benchmark did not produce numeric p95 measurements.")
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixture": "Synthetic data, never research or linguistic evidence",
        "rows": rows, "text_characters": text_characters,
        "standard_nfr10_fixture": rows == 1000 and text_characters == 500 and runs == 20,
        "method": "One warm-up then nearest-rank p95 of real active-tab handlers plus Tk idle rendering",
        "limit_ms": limit_ms,
        "passed_on_this_machine": search_p95 <= limit_ms and stats_p95 <= limit_ms,
        "environment": {
            "platform": platform.platform(), "machine": platform.machine(),
            "processor": platform.processor(), "physical_memory_bytes": physical_memory_bytes(),
            "python": platform.python_version(), "tk": tk_version,
            "customtkinter": importlib.metadata.version("customtkinter"),
        },
        "source_sha256": hashes,
        "search": search, "stats": stats,
        "limitations": [
            "Results apply to the recorded machine and source hashes, not every supported device.",
            "No microphone, provider request, real corpus, or audio playback was exercised.",
        ],
    }


def main() -> int:
    from tkinter import TclError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=1000)
    parser.add_argument("--text-characters", type=int, default=500)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--limit-ms", type=float, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_benchmark(
            rows=args.rows, text_characters=args.text_characters, runs=args.runs, limit_ms=args.limit_ms,
        )
        serialized = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(serialized, encoding="utf-8")
    except (OSError, ValueError, TclError) as exc:
        parser.exit(1, f"Collector benchmark failed: {exc}\n")
    print(serialized, end="")
    return 0 if report["passed_on_this_machine"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
