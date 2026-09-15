"""Context-free grammar representation and a plain-text grammar loader.

Grammar file syntax::

    # comment
    Clause -> NP Predicate | VG | eps

Symbols in ALL CAPS are terminals (they must be :class:`~fca.tokens.Cat` names);
CamelCase symbols are non-terminals. ``eps`` denotes the empty string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

EPSILON = "eps"
END = "$"

_RULE = re.compile(r"^\s*([A-Za-z_][\w']*)\s*->\s*(.*)$")


@dataclass(frozen=True)
class Production:
    lhs: str
    rhs: tuple[str, ...]

    def __str__(self) -> str:
        body = " ".join(self.rhs) if self.rhs else EPSILON
        return f"{self.lhs} -> {body}"

    @property
    def is_epsilon(self) -> bool:
        return not self.rhs


class Grammar:
    """An ordered set of productions with a designated start symbol."""

    def __init__(self, start: str, productions: list[Production], name: str = "grammar"):
        self.start = start
        self.name = name
        self.productions: list[Production] = []
        self.by_lhs: dict[str, list[Production]] = {}
        for prod in productions:
            self.add(prod)

    def add(self, prod: Production) -> None:
        bucket = self.by_lhs.setdefault(prod.lhs, [])
        if prod in bucket:
            return
        bucket.append(prod)
        self.productions.append(prod)

    @property
    def nonterminals(self) -> list[str]:
        return list(self.by_lhs)

    @property
    def terminals(self) -> list[str]:
        seen: dict[str, None] = {}
        for prod in self.productions:
            for sym in prod.rhs:
                if sym not in self.by_lhs:
                    seen.setdefault(sym, None)
        return list(seen)

    def is_terminal(self, symbol: str) -> bool:
        return symbol not in self.by_lhs

    def copy(self, name: str | None = None) -> "Grammar":
        return Grammar(self.start, list(self.productions), name or self.name)

    def to_text(self) -> str:
        lines: list[str] = []
        order = [self.start] + [nt for nt in self.by_lhs if nt != self.start]
        for nt in order:
            bodies = [" ".join(p.rhs) if p.rhs else EPSILON for p in self.by_lhs[nt]]
            lines.append(f"{nt} -> " + " | ".join(bodies))
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self.productions)

    def __str__(self) -> str:  # pragma: no cover - display helper
        return self.to_text()


def parse_grammar(text: str, name: str = "grammar") -> Grammar:
    """Read grammar rules from text. The first rule's LHS becomes the start symbol."""
    productions: list[Production] = []
    start = ""
    for line in _join_continuations(text):
        match = _RULE.match(line)
        if not match:
            raise ValueError(f"malformed grammar rule: {line!r}")
        lhs, bodies = match.group(1), match.group(2)
        start = start or lhs
        for body in bodies.split("|"):
            symbols = tuple(s for s in body.split() if s and s != EPSILON)
            productions.append(Production(lhs, symbols))
    if not start:
        raise ValueError("grammar contains no rules")
    return Grammar(start, productions, name)


def _join_continuations(text: str) -> list[str]:
    """Merge ``| alternative`` continuation lines into the rule above them."""
    rules: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        if stripped.startswith("|") and rules:
            rules[-1] += " " + stripped
        else:
            rules.append(stripped)
    return rules


def load_grammar(path: str | Path) -> Grammar:
    path = Path(path)
    return parse_grammar(path.read_text(encoding="utf-8"), path.stem)
