"""Public, JSON-serializable grammar analysis and token parsing operations.

Invalid notation and unsafe/oversized transformations raise ``GrammarError``
(a ``ValueError``). Valid non-LL(1) grammars return analysis with diagnostics;
parsing them returns an explicit rejection rather than choosing a table entry.
"""

from functools import lru_cache
import json
from typing import Any

from .analysis import (
    build_table,
    calculate_first,
    calculate_follow,
    grammar_warnings,
    left_recursive_nonterminals,
    transform_grammar,
)
from .grammar import GrammarError, TERMINAL_CATEGORIES, TERMINAL_SET, read_grammar
from .predictive import parse_analysis

DEFAULT_GRAMMAR = """# Illustrative teaching starter, not a grammar collected from a corpus.
Sentence -> Subject VerbPhrase Ending | VerbPhrase Ending
Subject -> FRENCH_FUNCTION_WORD NOUN | FRENCH_FUNCTION_WORD | ENGLISH_FUNCTION_WORD | NOUN
VerbPhrase -> VERB Object | VERB | PIDGIN_MARKER VERB Object | PIDGIN_MARKER VERB
Object -> Object NOUN | NOUN
Ending -> PUNCTUATION | epsilon
"""

__all__ = [
    "DEFAULT_GRAMMAR",
    "GrammarError",
    "TERMINAL_CATEGORIES",
    "analyze_grammar",
    "parse_analysis",
    "parse_tokens",
]


def analyze_grammar(grammar_text: str) -> dict[str, Any]:
    """Calculate transformations, FIRST/FOLLOW, and all conflicting LL(1) cells.

    Epsilon productions are empty lists. FIRST uses ``epsilon``; FOLLOW and
    table lookaheads use ``$`` for end of input. Only unambiguous table cells
    appear in ``table``; every competing production is retained in ``conflicts``.

    Only the exact public teaching starter is cached, as immutable JSON.
    Decoding returns independent mutable results. Custom grammars (including
    their comments), corpus text and reviewed annotations are never cached here.
    """
    if isinstance(grammar_text, str) and grammar_text == DEFAULT_GRAMMAR:
        return json.loads(_default_analysis_json())
    return _analyze_grammar(grammar_text)


@lru_cache(maxsize=1)
def _default_analysis_json() -> str:
    return json.dumps(_analyze_grammar(DEFAULT_GRAMMAR))


def _analyze_grammar(grammar_text: str) -> dict[str, Any]:
    original = read_grammar(grammar_text)
    start = next(iter(original))
    transformed, steps = transform_grammar(original)
    first = calculate_first(transformed)
    follow = calculate_follow(transformed, start, first)
    table, conflicts = build_table(transformed, first, follow)
    recursive = left_recursive_nonterminals(transformed)
    terminals = sorted({
        symbol
        for alternatives in transformed.values()
        for rhs in alternatives
        for symbol in rhs
        if symbol in TERMINAL_SET
    })
    warnings = [
        "This category-level grammar has limited coverage: rejection does not prove a sentence "
        "is invalid Francanglais, and acceptance is not a linguistic validation.",
        "Results depend on lexer categories, including heuristic classifications, not word meanings.",
    ]
    if grammar_text.strip() == DEFAULT_GRAMMAR.strip():
        warnings.append("The default grammar is an illustrative teaching starter, not collected evidence.")
    missing_categories = sorted(TERMINAL_SET - set(terminals))
    if missing_categories:
        warnings.append("Lexer categories not covered by this grammar: " + ", ".join(missing_categories) + ".")
    if "UNKNOWN" in terminals:
        warnings.append("UNKNOWN is explicitly allowed here as a terminal category, never as a wildcard.")
    warnings.extend(grammar_warnings(transformed, start))
    if recursive:
        warnings.append(
            "Left recursion remains through nullable prefixes or cycles in: "
            + ", ".join(recursive)
            + ". Ordered substitution and direct elimination did not remove it; this grammar is not LL(1)."
        )
    if conflicts:
        cells = ", ".join(f"({item['nonterminal']}, {item['terminal']})" for item in conflicts[:10])
        if len(conflicts) > 10:
            cells += ", ..."
        warnings.append(
            f"LL(1) table conflicts in {len(conflicts)} cell(s): {cells}. "
            "Conflicting cells are omitted from the single-production table; "
            "all competing productions are listed in conflicts. Predictive parsing is disabled."
        )
    return {
        "original": original,
        "transformed": transformed,
        "start_symbol": start,
        "terminals": terminals,
        "nonterminals": list(transformed),
        "steps": steps,
        "first": {lhs: sorted(symbols) for lhs, symbols in first.items()},
        "follow": {lhs: sorted(symbols) for lhs, symbols in follow.items()},
        "table": table,
        "conflicts": conflicts,
        "is_ll1": not conflicts and not recursive,
        "warnings": warnings,
    }


def parse_tokens(grammar_text: str, tokens: list[dict[str, str]]) -> dict[str, Any]:
    """Analyze a grammar and parse one complete lexer category-token stream."""
    return parse_analysis(analyze_grammar(grammar_text), tokens)
