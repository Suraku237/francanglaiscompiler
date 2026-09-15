"""Grammar transformations required before LL(1) table construction.

Two classical algorithms:

* :func:`remove_left_recursion` - Aho, Sethi & Ullman's substitution method, which
  removes indirect left recursion by ordering the non-terminals and then removes
  immediate left recursion by introducing a tail non-terminal ``A'``.
* :func:`left_factor` - repeatedly extracts the longest common prefix shared by two or
  more alternatives of the same non-terminal.

Both return a *new* grammar and a log of the steps, so the report can show the
before/after of every rewrite.
"""

from __future__ import annotations

from .grammar import Grammar, Production


def _fresh(name: str, taken: set[str]) -> str:
    candidate = name + "'"
    while candidate in taken:
        candidate += "'"
    return candidate


def remove_left_recursion(grammar: Grammar) -> tuple[Grammar, list[str]]:
    """Return an equivalent grammar with no left recursion, plus a step log."""
    log: list[str] = []
    order = list(grammar.by_lhs)
    bodies: dict[str, list[tuple[str, ...]]] = {
        nt: [p.rhs for p in grammar.by_lhs[nt]] for nt in order
    }
    taken = set(order)

    for i, a_i in enumerate(order):
        # Substitute earlier non-terminals to expose indirect left recursion.
        for a_j in order[:i]:
            expanded: list[tuple[str, ...]] = []
            changed = False
            for rhs in bodies[a_i]:
                if rhs and rhs[0] == a_j:
                    changed = True
                    for inner in bodies[a_j]:
                        expanded.append(tuple(inner) + tuple(rhs[1:]))
                else:
                    expanded.append(rhs)
            if changed:
                log.append(f"substituted {a_j} into {a_i}")
                bodies[a_i] = _dedupe(expanded)

        recursive = [rhs[1:] for rhs in bodies[a_i] if rhs and rhs[0] == a_i]
        if not recursive:
            continue

        rest = [rhs for rhs in bodies[a_i] if not (rhs and rhs[0] == a_i)]
        tail = _fresh(a_i, taken)
        taken.add(tail)
        if not rest:
            rest = [()]  # A -> A alpha only: keep the language non-empty
        bodies[a_i] = _dedupe([tuple(rhs) + (tail,) for rhs in rest])
        bodies[tail] = _dedupe([tuple(alpha) + (tail,) for alpha in recursive] + [()])
        order.append(tail)
        log.append(f"removed immediate left recursion on {a_i} (new symbol {tail})")

    productions = [Production(nt, rhs) for nt in order for rhs in bodies.get(nt, [])]
    return Grammar(grammar.start, productions, grammar.name + "+norec"), log


def left_factor(grammar: Grammar) -> tuple[Grammar, list[str]]:
    """Return an equivalent left-factored grammar, plus a step log."""
    log: list[str] = []
    bodies: dict[str, list[tuple[str, ...]]] = {
        nt: _dedupe([p.rhs for p in grammar.by_lhs[nt]]) for nt in grammar.by_lhs
    }
    order = list(bodies)
    taken = set(order)

    changed = True
    while changed:
        changed = False
        for nt in list(order):
            prefix = _longest_common_prefix(bodies[nt])
            if not prefix:
                continue
            shared = [rhs for rhs in bodies[nt] if _starts_with(rhs, prefix)]
            others = [rhs for rhs in bodies[nt] if not _starts_with(rhs, prefix)]
            tail = _fresh(nt, taken)
            taken.add(tail)
            order.append(tail)
            bodies[tail] = _dedupe([rhs[len(prefix) :] for rhs in shared])
            bodies[nt] = _dedupe(others + [tuple(prefix) + (tail,)])
            log.append(
                f"factored {nt}: common prefix {' '.join(prefix)!r} -> {tail}"
            )
            changed = True

    productions = [Production(nt, rhs) for nt in order for rhs in bodies.get(nt, [])]
    return Grammar(grammar.start, productions, grammar.name + "+factored"), log


def normalise(grammar: Grammar) -> tuple[Grammar, list[str]]:
    """Left-recursion removal followed by left factoring."""
    step1, log1 = remove_left_recursion(grammar)
    step2, log2 = left_factor(step1)
    return step2, log1 + log2


# -- helpers -------------------------------------------------------------


def _dedupe(items: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    seen: dict[tuple[str, ...], None] = {}
    for item in items:
        seen.setdefault(tuple(item), None)
    return list(seen)


def _starts_with(rhs: tuple[str, ...], prefix: tuple[str, ...]) -> bool:
    return len(rhs) >= len(prefix) and rhs[: len(prefix)] == prefix


def _longest_common_prefix(rhss: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Longest prefix shared by at least two alternatives, or ``()``."""
    best: tuple[str, ...] = ()
    for i, first in enumerate(rhss):
        for second in rhss[i + 1 :]:
            length = 0
            while (
                length < len(first)
                and length < len(second)
                and first[length] == second[length]
            ):
                length += 1
            if length > len(best):
                best = first[:length]
    return best
