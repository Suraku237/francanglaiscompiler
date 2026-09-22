"""Repeatable, offline compiler microbenchmarks using only synthetic fixtures.

Run from the repository root with ``python -m tools.benchmark_compiler``.
These timings exclude storage, authentication, HTTP and browser rendering;
the fixtures are not collected Francanglais or linguistic accuracy evidence.
"""

import argparse
from collections.abc import Callable
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import timeit
from typing import Any

from compiler.lexer.frequency import compute_frequencies
from compiler.lexer.tokenizer import analyze_sentence, find_verb_phrases
from compiler.parser.grammar import MAX_NONTERMINALS
from compiler.parser.predictive import MAX_INPUT_TOKENS
from compiler.parser import service
from compiler.parser.service import DEFAULT_GRAMMAR, analyze_grammar, parse_analysis, parse_tokens

ROOT = Path(__file__).resolve().parents[1]
SOURCES = sorted((ROOT / "compiler" / "lexer").glob("*.py")) + sorted(
    (ROOT / "compiler" / "parser").glob("*.py")
) + [Path(__file__).resolve()]


def synthetic_cases() -> dict[str, Callable[[], Any]]:
    """Create fresh in-memory inputs, never read a user's corpus or annotations."""
    short = "Le taxi don refuse. drop me 12.5! go quartier and payer money."
    reviewed = {"syntheticnoun": "NOUN", "syntheticverb": "VERB"}
    repeated = " ".join(["syntheticnoun SYNTHETICVERB taxi +"] * (MAX_INPUT_TOKENS // 4))
    phrase_text = "DROP\tME; don  refuse; Hala me re\u0301seau money; come down."
    short_tokens = [token._asdict() for token in analyze_sentence("le moto block.")["tokens"]]
    frequency_tokens = analyze_sentence(repeated, reviewed)["tokens"]
    default_analysis = analyze_grammar(DEFAULT_GRAMMAR)
    repeated_analysis = analyze_grammar("S -> NOUN S | epsilon")
    boundary_tokens = [{"text": "taxi", "category": "NOUN"} for _ in range(MAX_INPUT_TOKENS)]
    oversized_tokens = boundary_tokens + [{"text": "taxi", "category": "NOUN"}]
    nullable_chain = "\n".join(
        [f"N{i} -> N{i + 1}" for i in range(MAX_NONTERMINALS - 1)]
        + [f"N{MAX_NONTERMINALS - 1} -> NOUN | epsilon"]
    )
    conflict = "S -> A | B\nA -> NOUN\nB -> NOUN"

    assert len(frequency_tokens) == MAX_INPUT_TOKENS
    assert parse_analysis(default_analysis, short_tokens)["accepted"]
    assert parse_analysis(repeated_analysis, boundary_tokens)["consumed"] == MAX_INPUT_TOKENS
    assert not parse_analysis(repeated_analysis, oversized_tokens)["accepted"]
    assert not analyze_grammar(conflict)["is_ll1"]
    return {
        "lexer_short": lambda: analyze_sentence(short),
        "lexer_reviewed_256": lambda: analyze_sentence(repeated, reviewed),
        "phrase_annotations": lambda: find_verb_phrases(phrase_text),
        "frequencies_256": lambda: compute_frequencies(frequency_tokens),
        "analyze_default": lambda: analyze_grammar(DEFAULT_GRAMMAR),
        "analyze_persisted_default": lambda: analyze_grammar(DEFAULT_GRAMMAR.strip()),
        "analyze_nullable_chain_50": lambda: analyze_grammar(nullable_chain),
        "analyze_conflict": lambda: analyze_grammar(conflict),
        "parse_default_with_analysis": lambda: parse_tokens(DEFAULT_GRAMMAR, short_tokens),
        "parse_persisted_default_with_analysis": lambda: parse_tokens(DEFAULT_GRAMMAR.strip(), short_tokens),
        "parse_prepared_default": lambda: parse_analysis(default_analysis, short_tokens),
        "parse_prepared_boundary_256": lambda: parse_analysis(repeated_analysis, boundary_tokens),
        "reject_oversized_257": lambda: parse_analysis(repeated_analysis, oversized_tokens),
    }


def _source_hashes() -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in SOURCES
    }


def _distribution(samples: list[float]) -> dict[str, Any]:
    return {
        "median_us": statistics.median(samples),
        "p95_batch_mean_us": sorted(samples)[math.ceil(len(samples) * 0.95) - 1],
        "min_us": min(samples),
        "max_us": max(samples),
        "samples_us": samples,
    }


def compare_default_preparation(samples: int, iterations: int) -> dict[str, Any]:
    text = DEFAULT_GRAMMAR.strip()
    operations = {
        "uncached": lambda: service._analyze_grammar(text),
        "cached": lambda: analyze_grammar(text),
    }
    assert operations["uncached"]() == operations["cached"]()
    timings: dict[str, list[float]] = {name: [] for name in operations}
    for sample in range(samples):
        order = ("uncached", "cached") if sample % 2 == 0 else ("cached", "uncached")
        for name in order:
            elapsed = timeit.Timer(operations[name]).timeit(number=iterations)
            timings[name].append(elapsed * 1_000_000 / iterations)
    return {
        "input": "Public starter after the same whitespace stripping used by the project profile.",
        "method": "Alternating-order paired batches in one process; same grammar preparation algorithm.",
        "uncached": _distribution(timings["uncached"]),
        "cached": _distribution(timings["cached"]),
        "median_speedup": statistics.median(timings["uncached"]) / statistics.median(timings["cached"]),
    }


def run_benchmark(*, samples: int = 15, iterations: int = 100) -> dict[str, Any]:
    """Report distributions of batch-average time per call, not request latencies."""
    if not 3 <= samples <= 100:
        raise ValueError("Use 3-100 measured samples.")
    if not 1 <= iterations <= 10_000:
        raise ValueError("Use 1-10000 iterations per sample.")
    hashes = _source_hashes()
    cases = synthetic_cases()
    measurements = {}
    for name, operation in cases.items():
        for _ in range(5):
            operation()
        batch_seconds = timeit.Timer(operation).repeat(repeat=samples, number=iterations)
        per_call_us = [elapsed * 1_000_000 / iterations for elapsed in batch_seconds]
        measurements[name] = _distribution(per_call_us)
    comparison = compare_default_preparation(samples, iterations)
    if hashes != _source_hashes():
        raise RuntimeError("Compiler source changed during measurement; rerun against stable source.")
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fixture": {
            "synthetic": True,
            "boundary_tokens": MAX_INPUT_TOKENS,
            "nullable_chain_nonterminals": MAX_NONTERMINALS,
            "reviewed_annotations": "Two synthetic per-call labels; no account or project data.",
        },
        "method": {
            "samples": samples,
            "iterations_per_sample": iterations,
            "warmups_per_case": 5,
            "timer": "timeit perf_counter; garbage collection disabled only inside each timed batch",
            "unit": "microseconds per call; each sample is a batch average",
        },
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "source_sha256": hashes,
        "measurements": measurements,
        "default_preparation_comparison": comparison,
        "limitations": [
            "Synthetic compiler microbenchmarks, not collected corpus or linguistic accuracy evidence.",
            "Warm repeated calls on one machine, not cold-start or concurrent-user capacity.",
            "p95 is over batch means, not individual end-to-end request latency.",
            "Excludes persistence, authentication, network, browser, and external services.",
            "The default grammar is an illustrative category-level teaching starter.",
            "The paired comparison isolates public-starter caching, not a whole-application or custom-grammar speedup.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = run_benchmark(samples=args.samples, iterations=args.iterations)
        serialized = json.dumps(report, indent=2) + "\n"
        if args.output:
            args.output.write_text(serialized, encoding="utf-8")
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"Compiler benchmark failed: {exc}\n")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
