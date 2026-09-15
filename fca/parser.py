"""Table-driven LL(1) predictive parser.

The parser keeps an explicit stack, consults ``M[A, a]`` for every expansion and
records a trace of (stack, remaining input, action) triples - which is exactly the
table that has to go into the project report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .analysis import Analysis, analyse
from .grammar import END, Grammar, Production, load_grammar
from .tokens import Cat, Token


@dataclass
class ParseNode:
    symbol: str
    token: Token | None = None
    children: list["ParseNode"] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def render(self, indent: str = "", last: bool = True) -> str:
        label = self.symbol
        if self.token is not None:
            label = f"{self.symbol}  \u00ab{self.token.surface}\u00bb"
        elif self.is_leaf:
            label = f"{self.symbol}  \u00abeps\u00bb"
        branch = "\u2514\u2500 " if last else "\u251c\u2500 "
        out = [indent + (branch if indent or not last else "") + label]
        child_indent = indent + ("   " if last else "\u2502  ")
        for i, child in enumerate(self.children):
            out.append(child.render(child_indent, i == len(self.children) - 1))
        return "\n".join(out)


@dataclass
class TraceStep:
    step: int
    stack: str
    remaining: str
    action: str


@dataclass
class ParseResult:
    accepted: bool
    tree: ParseNode | None
    trace: list[TraceStep]
    error: str = ""
    error_token: Token | None = None
    expected: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return self.accepted


class LL1Parser:
    """Predictive parser driven by a pre-computed LL(1) table."""

    MAX_TRACE = 400

    def __init__(self, grammar: Grammar, analysis: Analysis | None = None):
        self.grammar = grammar
        self.analysis = analysis or analyse(grammar)

    @classmethod
    def from_file(cls, path) -> "LL1Parser":
        return cls(load_grammar(path))

    def parse(self, tokens: list[Token]) -> ParseResult:
        table = self.analysis.table
        stream = [t for t in tokens]
        terminals = [t.cat.value for t in stream] + [END]

        root = ParseNode(self.grammar.start)
        stack: list[tuple[str, ParseNode | None]] = [(END, None), (self.grammar.start, root)]
        trace: list[TraceStep] = []
        pos = 0

        while stack:
            symbol, node = stack[-1]
            lookahead = terminals[pos]
            self._record(trace, stack, terminals, pos, symbol, lookahead)

            if symbol == END:
                stack.pop()
                if lookahead == END:
                    trace[-1].action = "accept"
                    return ParseResult(True, root, trace)
                return self._fail(trace, stream, pos, ("end of input",))

            if self.grammar.is_terminal(symbol):
                if symbol == lookahead:
                    stack.pop()
                    if node is not None and pos < len(stream):
                        node.token = stream[pos]
                    trace[-1].action = f"match {symbol}"
                    pos += 1
                    continue
                return self._fail(trace, stream, pos, (symbol,))

            prod = table.get((symbol, lookahead))
            if prod is None:
                return self._fail(trace, stream, pos, self._expected(symbol))

            stack.pop()
            trace[-1].action = f"output {prod}"
            children = [ParseNode(sym) for sym in prod.rhs]
            if node is not None:
                node.children = children
            for sym, child in reversed(list(zip(prod.rhs, children))):
                stack.append((sym, child))

        return self._fail(trace, stream, pos, ("end of input",))

    # -- helpers ---------------------------------------------------------

    def _expected(self, nonterminal: str) -> tuple[str, ...]:
        return tuple(
            sorted(term for (nt, term) in self.analysis.table if nt == nonterminal)
        )

    def _record(self, trace, stack, terminals, pos, symbol, lookahead) -> None:
        if len(trace) >= self.MAX_TRACE:
            return
        trace.append(
            TraceStep(
                step=len(trace) + 1,
                stack=" ".join(s for s, _ in stack),
                remaining=" ".join(terminals[pos : pos + 6])
                + (" ..." if len(terminals) - pos > 6 else ""),
                action="",
            )
        )

    def _fail(self, trace, stream, pos, expected) -> ParseResult:
        token = stream[pos] if pos < len(stream) else None
        where = f"token {pos + 1}" if token else "end of input"
        got = f"{token.cat.value} \u00ab{token.surface}\u00bb" if token else "$"
        message = (
            f"syntax error at {where}: found {got}, expected one of "
            + ", ".join(expected)
        )
        if trace:
            trace[-1].action = "error"
        return ParseResult(False, None, trace, message, token, tuple(expected))


def default_parser(path=None) -> LL1Parser:
    from .lexicon import ROOT

    return LL1Parser.from_file(path or ROOT / "grammar" / "fca.gram")
