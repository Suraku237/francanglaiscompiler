"""Bounded, semantics-preserving CFG rewrites and fixed-point LL(1) analysis."""

from typing import Any

from .grammar import END, EPSILON, Grammar, GrammarError, Production, snapshot

MAX_TRANSFORMED_NONTERMINALS = 200
MAX_TRANSFORMED_ALTERNATIVES = 600
MAX_TRANSFORMED_RHS_LENGTH = 100
MAX_TRANSFORMED_SYMBOLS = 6_000
MAX_TRANSFORMATION_STEPS = 200
MAX_EXPANSION_ATTEMPTS = 20_000
MAX_SNAPSHOT_UNITS = 100_000


def nullable_nonterminals(grammar: Grammar) -> set[str]:
    nullable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for lhs, alternatives in grammar.items():
            if lhs not in nullable and any(
                all(symbol in nullable for symbol in rhs) for rhs in alternatives
            ):
                nullable.add(lhs)
                changed = True
    return nullable


def _size(grammar: Grammar) -> int:
    return len(grammar) + sum(1 + len(rhs) for alts in grammar.values() for rhs in alts)


def _check_expansion(grammar: Grammar) -> None:
    if len(grammar) > MAX_TRANSFORMED_NONTERMINALS:
        raise GrammarError("Transformation expansion limit: too many generated nonterminals.")
    alternatives = [rhs for productions in grammar.values() for rhs in productions]
    if len(alternatives) > MAX_TRANSFORMED_ALTERNATIVES:
        raise GrammarError("Transformation expansion limit: too many alternatives.")
    if any(len(rhs) > MAX_TRANSFORMED_RHS_LENGTH for rhs in alternatives):
        raise GrammarError("Transformation expansion limit: a generated right-hand side is too long.")
    if sum(map(len, alternatives)) > MAX_TRANSFORMED_SYMBOLS:
        raise GrammarError("Transformation expansion limit: too many production symbols.")


class _Transformations:
    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []
        self.expansions = 0
        self.snapshot_units = 0

    def append(self, alternatives: list[Production], rhs: Production) -> None:
        self.expansions += 1
        if self.expansions > MAX_EXPANSION_ATTEMPTS:
            raise GrammarError("Transformation expansion work limit exceeded.")
        if len(rhs) > MAX_TRANSFORMED_RHS_LENGTH:
            raise GrammarError("Transformation expansion limit: a generated right-hand side is too long.")
        if rhs not in alternatives:
            if len(alternatives) >= MAX_TRANSFORMED_ALTERNATIVES:
                raise GrammarError("Transformation expansion limit: too many alternatives.")
            alternatives.append(rhs)

    def record(self, operation: str, before: Grammar, after: Grammar, description: str) -> None:
        _check_expansion(after)
        if len(self.steps) >= MAX_TRANSFORMATION_STEPS:
            raise GrammarError("Transformation step limit exceeded.")
        self.snapshot_units += _size(before) + _size(after)
        if self.snapshot_units > MAX_SNAPSHOT_UNITS:
            raise GrammarError("Transformation snapshot-size limit exceeded.")
        self.steps.append({
            "operation": operation,
            "before": before,
            "after": snapshot(after),
            "description": description,
        })


def _new_nonterminal(grammar: Grammar, base: str, suffix: str) -> str:
    number = 1
    while f"{base}_{suffix}{number}" in grammar:
        number += 1
    return f"{base}_{suffix}{number}"


def _remove_left_recursion(grammar: Grammar, log: _Transformations) -> None:
    original_order = list(grammar)
    for index, lhs in enumerate(original_order):
        for earlier in original_order[:index]:
            if not any(rhs and rhs[0] == earlier for rhs in grammar[lhs]):
                continue
            before = snapshot(grammar)
            replacements: list[Production] = []
            for rhs in grammar[lhs]:
                if rhs and rhs[0] == earlier:
                    for prefix in grammar[earlier]:
                        log.append(replacements, prefix + rhs[1:])
                else:
                    log.append(replacements, rhs.copy())
            grammar[lhs] = replacements
            log.record(
                "substitute_indirect_left_recursion",
                before,
                grammar,
                f"Substitute {earlier}'s alternatives into leading occurrences in {lhs}. "
                "This is the ordered substitution stage of indirect left-recursion elimination.",
            )

        recursive = [rhs[1:] for rhs in grammar[lhs] if rhs and rhs[0] == lhs]
        if not recursive:
            continue
        bases = [rhs for rhs in grammar[lhs] if not rhs or rhs[0] != lhs]
        if any(not suffix for suffix in recursive):
            raise GrammarError(
                f"Degenerate left recursion in {lhs} -> {lhs}: the recursive suffix is empty."
            )
        if not bases:
            raise GrammarError(
                f"Degenerate left recursion in {lhs}: there is no nonrecursive alternative, "
                "so this nonterminal cannot derive a finite token sequence."
            )
        nullable = nullable_nonterminals(grammar)
        if any(all(symbol in nullable for symbol in suffix) for suffix in recursive):
            raise GrammarError(
                f"Unsafe left-recursion rewrite in {lhs}: a recursive suffix is nullable; "
                "remove the nullable recursive cycle before predictive parsing."
            )
        before = snapshot(grammar)
        helper = _new_nonterminal(grammar, lhs, "LR")
        grammar[lhs] = [base + [helper] for base in bases]
        grammar[helper] = [suffix + [helper] for suffix in recursive] + [[]]
        log.record(
            "eliminate_direct_left_recursion",
            before,
            grammar,
            f"Replace {lhs} -> {lhs} alpha | beta with {lhs} -> beta {helper} "
            f"and {helper} -> alpha {helper} | {EPSILON}, for every alpha and beta.",
        )


def _factor_once(grammar: Grammar, lhs: str, log: _Transformations) -> bool:
    groups: dict[str, list[Production]] = {}
    for rhs in grammar[lhs]:
        if rhs:
            groups.setdefault(rhs[0], []).append(rhs)
    group = next((items for items in groups.values() if len(items) > 1), None)
    if group is None:
        return False
    prefix = group[0].copy()
    for rhs in group[1:]:
        length = 0
        while length < min(len(prefix), len(rhs)) and prefix[length] == rhs[length]:
            length += 1
        prefix = prefix[:length]
    before = snapshot(grammar)
    helper = _new_nonterminal(grammar, lhs, "LF")
    alternatives: list[Production] = []
    inserted = False
    for rhs in grammar[lhs]:
        if rhs and rhs[0] == prefix[0]:
            if not inserted:
                alternatives.append(prefix + [helper])
                inserted = True
        else:
            alternatives.append(rhs.copy())
    grammar[lhs] = alternatives
    grammar[helper] = [rhs[len(prefix):] for rhs in group]
    log.record(
        "left_factor",
        before,
        grammar,
        f"Factor the common prefix {' '.join(prefix)!r} from {lhs}; "
        f"move the remaining alternatives to {helper}, using {EPSILON} for an empty suffix.",
    )
    return True


def transform_grammar(original: Grammar) -> tuple[Grammar, list[dict[str, Any]]]:
    grammar = snapshot(original)
    log = _Transformations()
    _remove_left_recursion(grammar, log)
    if not log.steps:
        log.record(
            "left_recursion_check",
            snapshot(grammar),
            grammar,
            "No direct or ordered indirect left-recursion rewrite was needed. "
            "Nullable-prefix left recursion is checked separately after transformation.",
        )
    factoring_start = len(log.steps)
    changed = True
    while changed:
        changed = False
        for lhs in list(grammar):
            if _factor_once(grammar, lhs, log):
                changed = True
    if len(log.steps) == factoring_start:
        log.record(
            "left_factoring_check",
            snapshot(grammar),
            grammar,
            "No alternatives share a nonempty literal symbol prefix; no factoring was needed.",
        )
    return grammar, log.steps


def first_of_sequence(rhs: Production, first: dict[str, set[str]]) -> set[str]:
    result: set[str] = set()
    for symbol in rhs:
        if symbol not in first:
            result.add(symbol)
            return result
        result.update(first[symbol] - {EPSILON})
        if EPSILON not in first[symbol]:
            return result
    result.add(EPSILON)
    return result


def calculate_first(grammar: Grammar) -> dict[str, set[str]]:
    first: dict[str, set[str]] = {lhs: set() for lhs in grammar}
    changed = True
    while changed:
        changed = False
        for lhs, alternatives in grammar.items():
            for rhs in alternatives:
                additions = first_of_sequence(rhs, first) - first[lhs]
                if additions:
                    first[lhs].update(additions)
                    changed = True
    return first


def calculate_follow(
    grammar: Grammar, start: str, first: dict[str, set[str]]
) -> dict[str, set[str]]:
    follow: dict[str, set[str]] = {lhs: set() for lhs in grammar}
    follow[start].add(END)
    changed = True
    while changed:
        changed = False
        for lhs, alternatives in grammar.items():
            for rhs in alternatives:
                trailer = follow[lhs].copy()
                for symbol in reversed(rhs):
                    if symbol in grammar:
                        additions = trailer - follow[symbol]
                        if additions:
                            follow[symbol].update(additions)
                            changed = True
                        if EPSILON in first[symbol]:
                            trailer = trailer | (first[symbol] - {EPSILON})
                        else:
                            trailer = first[symbol] - {EPSILON}
                    else:
                        trailer = {symbol}
    return follow


def build_table(
    grammar: Grammar, first: dict[str, set[str]], follow: dict[str, set[str]]
) -> tuple[dict[str, dict[str, Production]], list[dict[str, Any]]]:
    table: dict[str, dict[str, Production]] = {lhs: {} for lhs in grammar}
    conflicts: list[dict[str, Any]] = []
    for lhs, alternatives in grammar.items():
        candidates: dict[str, list[Production]] = {}
        for rhs in alternatives:
            leading = first_of_sequence(rhs, first)
            lookaheads = leading - {EPSILON}
            if EPSILON in leading:
                lookaheads |= follow[lhs]
            for terminal in sorted(lookaheads):
                productions = candidates.setdefault(terminal, [])
                if rhs not in productions:
                    productions.append(rhs.copy())
        for terminal in sorted(candidates):
            productions = candidates[terminal]
            if len(productions) == 1:
                table[lhs][terminal] = productions[0].copy()
            else:
                # A single-production cell cannot represent a conflict: leave it absent.
                conflicts.append({
                    "nonterminal": lhs,
                    "terminal": terminal,
                    "productions": productions,
                })
    return table, conflicts


def left_recursive_nonterminals(grammar: Grammar) -> list[str]:
    nullable = nullable_nonterminals(grammar)
    edges: dict[str, set[str]] = {lhs: set() for lhs in grammar}
    for lhs, alternatives in grammar.items():
        for rhs in alternatives:
            for symbol in rhs:
                if symbol in grammar:
                    edges[lhs].add(symbol)
                if symbol not in nullable:
                    break
    recursive: list[str] = []
    for lhs in grammar:
        pending = list(edges[lhs])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == lhs:
                recursive.append(lhs)
                break
            if current not in visited:
                visited.add(current)
                pending.extend(edges[current] - visited)
    return recursive


def grammar_warnings(grammar: Grammar, start: str) -> list[str]:
    reachable = {start}
    pending = [start]
    while pending:
        lhs = pending.pop()
        for rhs in grammar[lhs]:
            for symbol in rhs:
                if symbol in grammar and symbol not in reachable:
                    reachable.add(symbol)
                    pending.append(symbol)
    productive: set[str] = set()
    changed = True
    while changed:
        changed = False
        for lhs, alternatives in grammar.items():
            if lhs not in productive and any(
                all(symbol not in grammar or symbol in productive for symbol in rhs)
                for rhs in alternatives
            ):
                productive.add(lhs)
                changed = True
    warnings = []
    unreachable = [lhs for lhs in grammar if lhs not in reachable]
    if unreachable:
        warnings.append("Nonterminals unreachable from the start symbol: " + ", ".join(unreachable) + ".")
    unproductive = [lhs for lhs in grammar if lhs not in productive]
    if unproductive:
        warnings.append(
            "Nonterminals unable to derive a finite token sequence: " + ", ".join(unproductive) + "."
        )
    return warnings
