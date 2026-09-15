"""FIRST / FOLLOW sets and LL(1) parsing-table construction."""

from __future__ import annotations

from dataclasses import dataclass, field

from .grammar import END, Grammar, Production


@dataclass
class Conflict:
    nonterminal: str
    terminal: str
    kept: Production
    dropped: Production

    def __str__(self) -> str:  # pragma: no cover - display helper
        return (
            f"M[{self.nonterminal}, {self.terminal}] : "
            f"kept ({self.kept}) / dropped ({self.dropped})"
        )


@dataclass
class Analysis:
    """Everything needed to build and explain an LL(1) parser."""

    grammar: Grammar
    nullable: set[str] = field(default_factory=set)
    first: dict[str, set[str]] = field(default_factory=dict)
    follow: dict[str, set[str]] = field(default_factory=dict)
    table: dict[tuple[str, str], Production] = field(default_factory=dict)
    conflicts: list[Conflict] = field(default_factory=list)

    @property
    def is_ll1(self) -> bool:
        return not self.conflicts

    def first_of_sequence(self, symbols) -> set[str]:
        return first_of_sequence(self.grammar, self.first, self.nullable, symbols)


def compute_nullable(grammar: Grammar) -> set[str]:
    nullable: set[str] = set()
    changed = True
    while changed:
        changed = False
        for prod in grammar.productions:
            if prod.lhs in nullable:
                continue
            if all(sym in nullable for sym in prod.rhs):
                nullable.add(prod.lhs)
                changed = True
    return nullable


def compute_first(grammar: Grammar, nullable: set[str]) -> dict[str, set[str]]:
    first: dict[str, set[str]] = {nt: set() for nt in grammar.by_lhs}
    for terminal in grammar.terminals:
        first[terminal] = {terminal}

    changed = True
    while changed:
        changed = False
        for prod in grammar.productions:
            target = first[prod.lhs]
            before = len(target)
            for sym in prod.rhs:
                target |= first.get(sym, {sym})
                if sym not in nullable:
                    break
            if len(target) != before:
                changed = True
    return first


def first_of_sequence(
    grammar: Grammar, first: dict[str, set[str]], nullable: set[str], symbols
) -> set[str]:
    """FIRST of a string of grammar symbols; ``END`` is never included."""
    result: set[str] = set()
    for sym in symbols:
        result |= first.get(sym, {sym})
        if sym not in nullable:
            return result
    return result


def sequence_nullable(nullable: set[str], symbols) -> bool:
    return all(sym in nullable for sym in symbols)


def compute_follow(
    grammar: Grammar, first: dict[str, set[str]], nullable: set[str]
) -> dict[str, set[str]]:
    follow: dict[str, set[str]] = {nt: set() for nt in grammar.by_lhs}
    follow[grammar.start].add(END)

    changed = True
    while changed:
        changed = False
        for prod in grammar.productions:
            for i, sym in enumerate(prod.rhs):
                if grammar.is_terminal(sym):
                    continue
                rest = prod.rhs[i + 1 :]
                addition = first_of_sequence(grammar, first, nullable, rest)
                if sequence_nullable(nullable, rest):
                    addition = addition | follow[prod.lhs]
                if not addition <= follow[sym]:
                    follow[sym] |= addition
                    changed = True
    return follow


def build_ll1_table(
    grammar: Grammar, first: dict[str, set[str]], follow: dict[str, set[str]], nullable: set[str]
) -> tuple[dict[tuple[str, str], Production], list[Conflict]]:
    """Fill M[A, a]. On a clash the longer production wins, and the clash is reported.

    Preferring the longer alternative is the same policy a compiler uses for the
    dangling-else problem: take the larger construct and keep the parse deterministic.
    """
    table: dict[tuple[str, str], Production] = {}
    conflicts: list[Conflict] = []

    for prod in grammar.productions:
        heads = first_of_sequence(grammar, first, nullable, prod.rhs)
        if sequence_nullable(nullable, prod.rhs):
            heads = heads | follow[prod.lhs]
        for terminal in heads:
            key = (prod.lhs, terminal)
            existing = table.get(key)
            if existing is None:
                table[key] = prod
                continue
            keep, drop = (prod, existing) if len(prod.rhs) > len(existing.rhs) else (existing, prod)
            table[key] = keep
            conflicts.append(Conflict(prod.lhs, terminal, keep, drop))
    return table, conflicts


def analyse(grammar: Grammar) -> Analysis:
    """Run the whole pipeline: nullable -> FIRST -> FOLLOW -> LL(1) table."""
    nullable = compute_nullable(grammar)
    first = compute_first(grammar, nullable)
    follow = compute_follow(grammar, first, nullable)
    table, conflicts = build_ll1_table(grammar, first, follow, nullable)
    return Analysis(grammar, nullable, first, follow, table, conflicts)
