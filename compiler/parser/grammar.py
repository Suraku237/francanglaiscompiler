"""Read the deliberately small, unquoted grammar notation used by the workbench."""

from difflib import get_close_matches
import re

from ..lexer.lexicon import TERMINAL_CATEGORIES

EPSILON = "epsilon"
END = "$"
TERMINAL_SET = frozenset(TERMINAL_CATEGORIES)

MAX_GRAMMAR_CHARACTERS = 12_000
MAX_NONTERMINALS = 50
MAX_ALTERNATIVES = 150
MAX_RHS_LENGTH = 20
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

Production = list[str]
Grammar = dict[str, list[Production]]


class GrammarError(ValueError):
    """Invalid grammar notation or a grammar exceeding safe processing limits."""


def snapshot(grammar: Grammar) -> Grammar:
    return {lhs: [rhs.copy() for rhs in alternatives] for lhs, alternatives in grammar.items()}


def read_grammar(grammar_text: str) -> Grammar:
    """Merge repeated definitions, retain source order, and validate every symbol."""
    if not isinstance(grammar_text, str):
        raise GrammarError("Grammar text must be a string.")
    if len(grammar_text) > MAX_GRAMMAR_CHARACTERS:
        raise GrammarError(f"Grammar exceeds the {MAX_GRAMMAR_CHARACTERS}-character limit.")

    grammar: Grammar = {}
    references: list[tuple[int, str]] = []
    alternative_count = 0
    for line_number, raw_line in enumerate(grammar_text.splitlines(), 1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.count("->") != 1:
            raise GrammarError(f"Line {line_number}: expected one '->' in a production.")
        lhs, rhs_text = (part.strip() for part in line.split("->", 1))
        if not IDENTIFIER.fullmatch(lhs):
            raise GrammarError(f"Line {line_number}: invalid nonterminal name {lhs!r}.")
        if lhs in TERMINAL_SET or lhs == EPSILON:
            raise GrammarError(f"Line {line_number}: {lhs!r} is reserved and cannot be a nonterminal.")
        if lhs not in grammar:
            if len(grammar) >= MAX_NONTERMINALS:
                raise GrammarError(f"Grammar exceeds the {MAX_NONTERMINALS}-nonterminal limit.")
            grammar[lhs] = []
        for alternative in rhs_text.split("|"):
            alternative_count += 1
            if alternative_count > MAX_ALTERNATIVES:
                raise GrammarError(f"Grammar exceeds the {MAX_ALTERNATIVES}-alternative limit.")
            symbols = alternative.split()
            if not symbols:
                raise GrammarError(
                    f"Line {line_number}: empty alternative; write '{EPSILON}' explicitly."
                )
            if len(symbols) > MAX_RHS_LENGTH:
                raise GrammarError(
                    f"Line {line_number}: a right-hand side exceeds {MAX_RHS_LENGTH} symbols."
                )
            if EPSILON in symbols:
                if symbols != [EPSILON]:
                    raise GrammarError(f"Line {line_number}: '{EPSILON}' must stand alone.")
                symbols = []
            for symbol in symbols:
                if not IDENTIFIER.fullmatch(symbol):
                    raise GrammarError(
                        f"Line {line_number}: invalid symbol {symbol!r}; use unquoted "
                        "nonterminal identifiers or lexer category names, not literal words."
                    )
                references.append((line_number, symbol))
            if symbols not in grammar[lhs]:
                grammar[lhs].append(symbols)
    if not grammar:
        raise GrammarError("Grammar must contain at least one production.")

    known = list(grammar) + list(TERMINAL_CATEGORIES)
    for line_number, symbol in references:
        if symbol not in grammar and symbol not in TERMINAL_SET:
            matches = get_close_matches(symbol, known, n=1, cutoff=0.6)
            suggestion = f" Did you mean {matches[0]!r}?" if matches else ""
            raise GrammarError(
                f"Line {line_number}: unknown symbol {symbol!r}; define this nonterminal "
                f"(check its spelling) or use a lexer category.{suggestion}"
            )
    return grammar
