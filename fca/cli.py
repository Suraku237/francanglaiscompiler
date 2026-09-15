"""Command-line front end.

Run ``python main.py --help`` for the full list. Each sub-command maps onto one
component of the project brief: ``tokens`` and ``freq`` for lexical analysis,
``grammar`` and ``parse`` for syntactic analysis, ``translate`` for the translator,
``corpus`` for the accept/reject table, and ``report`` to dump every artefact the
written report needs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import frequency, langid, regexspec
from .analysis import analyse
from .grammar import END, load_grammar
from .lexer import Lexer
from .lexicon import ROOT, load_lexicon
from .parser import LL1Parser
from .tokens import Cat, Lang
from .transformations import left_factor, remove_left_recursion
from .translate import Translator

GRAMMAR_FILE = ROOT / "grammar" / "fca.gram"
RAW_GRAMMAR_FILE = ROOT / "grammar" / "fca_raw.gram"
CORPUS_FILE = ROOT / "data" / "corpus.txt"
REJECTS_FILE = ROOT / "data" / "rejects.txt"


# -- shared helpers ------------------------------------------------------


def read_corpus(path: Path) -> list[str]:
    """Corpus format: '#' comments, blank lines ignored, one utterance per line."""
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join("-" * w for w in widths)
    out = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)), line]
    out += ["  ".join(str(c).ljust(widths[i]) for i, c in enumerate(row)) for row in rows]
    return "\n".join(out)


def markdown_table(rows: list[list[str]], headers: list[str]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def gather_text(args) -> list[str]:
    if getattr(args, "file", None):
        return read_corpus(Path(args.file))
    if args.text:
        return [" ".join(args.text)]
    return [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]


class Toolchain:
    """Lazily-built lexer, parser and translator sharing one lexicon."""

    def __init__(self, prefer: str | None = None, grammar_path: Path = GRAMMAR_FILE):
        self.lexicon = load_lexicon()
        preferred = Lang[prefer.upper()] if prefer else None
        self.lexer = Lexer(self.lexicon, preferred)
        self.grammar = load_grammar(grammar_path)
        self.analysis = analyse(self.grammar)
        self.parser = LL1Parser(self.grammar, self.analysis)
        self.translator = Translator(self.lexicon, self.lexer)


# -- sub-commands --------------------------------------------------------


def cmd_tokens(args) -> int:
    tool = Toolchain(args.prefer)
    for text in gather_text(args):
        tokens = tool.lexer.tokenize(text)
        print(f"\n{text}")
        rows = [
            [
                str(t.index),
                t.surface,
                t.cat.value,
                t.lang.value,
                (t.gloss[:44] + "...") if len(t.gloss) > 47 else t.gloss,
                t.section[:22],
            ]
            for t in tokens
        ]
        print(table(rows, ["#", "lexeme", "class", "language", "gloss", "section"]))
        print(f"\n  {langid.describe(tokens)}")
    return 0


def cmd_word(args) -> int:
    tool = Toolchain(args.prefer)
    for word in args.text:
        readings = tool.translator.translate_word(word)
        if not readings:
            print(f"{word}: not in any dictionary")
            continue
        print(f"\n{word}")
        print(table([list(r) for r in readings], ["language", "class", "English"]))
    return 0


def cmd_translate(args) -> int:
    tool = Toolchain(args.prefer)
    for text in gather_text(args):
        result = tool.translator.translate(text)
        if args.verbose:
            tokens = result.tokens
            print(f"\nsource     {text}")
            print(f"mixture    {langid.describe(tokens)}")
            print(f"english    {result.english}")
            for note in dict.fromkeys(result.notes):
                print(f"  note     {note}")
        else:
            print(result.english)
    return 0


def cmd_parse(args) -> int:
    tool = Toolchain(args.prefer)
    failures = 0
    for text in gather_text(args):
        tokens = tool.lexer.tokenize(text)
        result = tool.parser.parse(tokens)
        status = "ACCEPTED" if result.accepted else "REJECTED"
        print(f"\n{status}  {text}")
        print("  categories: " + " ".join(t.cat.value for t in tokens))
        if not result.accepted:
            failures += 1
            print(f"  {result.error}")
        if args.tree and result.tree:
            print(result.tree.render())
        if args.trace:
            rows = [[str(s.step), s.stack, s.remaining, s.action] for s in result.trace]
            print(table(rows, ["step", "stack", "input", "action"]))
    return 1 if failures and args.strict else 0


def cmd_grammar(args) -> int:
    grammar = load_grammar(Path(args.grammar) if args.grammar else GRAMMAR_FILE)

    if args.transform:
        print("== original ==\n" + grammar.to_text())
        step1, log1 = remove_left_recursion(grammar)
        print("\n== after left-recursion removal ==")
        for entry in log1:
            print("   - " + entry)
        print(step1.to_text())
        step2, log2 = left_factor(step1)
        print("\n== after left factoring ==")
        for entry in log2:
            print("   - " + entry)
        print(step2.to_text())
        grammar = step2

    result = analyse(grammar)

    if args.rules or not (args.first_follow or args.table or args.transform):
        print("\n== productions ==")
        for i, prod in enumerate(grammar.productions, 1):
            print(f"  {i:>3}. {prod}")

    if args.first_follow:
        rows = [
            [
                nt,
                "yes" if nt in result.nullable else "no",
                " ".join(sorted(result.first[nt])),
                " ".join(sorted(result.follow[nt])),
            ]
            for nt in grammar.nonterminals
        ]
        print("\n== FIRST / FOLLOW ==")
        print(table(rows, ["non-terminal", "nullable", "FIRST", "FOLLOW"]))

    if args.table:
        terminals = sorted({t for (_, t) in result.table}) or [END]
        rows = []
        for nt in grammar.nonterminals:
            row = [nt]
            for term in terminals:
                prod = result.table.get((nt, term))
                row.append(" ".join(prod.rhs) if prod else ("eps" if prod else ""))
                if prod is not None and not prod.rhs:
                    row[-1] = "eps"
            rows.append(row)
        print("\n== LL(1) parsing table ==")
        print(table(rows, ["M[A,a]"] + terminals))

    print(f"\nLL(1): {'yes' if result.is_ll1 else 'no'}   "
          f"({len(grammar)} productions, {len(grammar.nonterminals)} non-terminals)")
    for conflict in result.conflicts:
        print("  conflict " + str(conflict))
    return 0


def cmd_corpus(args) -> int:
    tool = Toolchain(args.prefer)
    corpus = read_corpus(Path(args.file) if args.file else CORPUS_FILE)
    rejects = read_corpus(Path(args.rejects) if args.rejects else REJECTS_FILE)

    rows = []
    accepted = 0
    for text in corpus:
        tokens = tool.lexer.tokenize(text)
        parsed = tool.parser.parse(tokens)
        accepted += parsed.accepted
        rows.append(
            [
                "OK" if parsed.accepted else "FAIL",
                text,
                tool.translator.translate_tokens(tokens, text).english,
            ]
        )
    print("== corpus ==")
    print(table(rows, ["parse", "source", "English"]))
    print(f"\naccepted {accepted}/{len(corpus)}")

    if rejects:
        rows = []
        for text in rejects:
            parsed = tool.parser.parse(tool.lexer.tokenize(text))
            rows.append(["REJECTED" if not parsed.accepted else "ACCEPTED (!)", text])
        print("\n== negative tests (these must be rejected) ==")
        print(table(rows, ["result", "source"]))
    return 0


def cmd_freq(args) -> int:
    tool = Toolchain(args.prefer)
    lines = read_corpus(Path(args.file)) if args.file else read_corpus(CORPUS_FILE)
    report = frequency.analyse_corpus(lines, tool.lexer)

    print(f"tokens {report.tokens}   types {report.types}   "
          f"type/token ratio {report.type_token_ratio:.2f}")
    print("\n== most frequent tokens ==")
    print(table([[t, str(n)] for t, n in report.most_common(args.top)], ["token", "count"]))
    print("\n== token classes ==")
    print(table([[c, str(n)] for c, n in report.by_category.most_common()], ["class", "count"]))
    print("\n== languages ==")
    print(table([[c, str(n)] for c, n in report.by_language.most_common()], ["language", "count"]))
    if report.by_section:
        print("\n== dictionary sections drawn on ==")
        print(table([[c, str(n)] for c, n in report.by_section.most_common(12)],
                    ["section", "count"]))
    variation = report.spelling_variation()
    if variation:
        print("\n== spelling variation ==")
        print(table([[k, ", ".join(v)] for k, v in variation.items()], ["normalised", "forms"]))
    if report.unknown:
        print("\n== not in any dictionary ==")
        print(table([[t, str(n)] for t, n in report.unknown.most_common()], ["token", "count"]))
    return 0


def cmd_regex(args) -> int:
    lexicon = load_lexicon()
    if args.flex:
        spec = regexspec.flex_specification(lexicon)
        out = Path(args.flex)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(spec, encoding="utf-8")
        print(f"wrote LEX/Flex specification to {out}")
        return 0
    if args.scan:
        for lexeme, cat in regexspec.scan(" ".join(args.scan), lexicon):
            print(f"{cat:<8} {lexeme}")
        return 0
    patterns = regexspec.category_patterns(lexicon)
    for cat, pattern in sorted(patterns.items()):
        shown = pattern if args.full else (pattern[:110] + " ...") if len(pattern) > 113 else pattern
        print(f"\n{cat}\n  {shown}")
    return 0


def cmd_stats(args) -> int:
    lexicon = load_lexicon()
    rows = [
        [lang.value, str(lexicon.count(lang))]
        for lang in (Lang.CAMFRANGLAIS, Lang.FRENCH)
    ]
    rows.append(["ENGLISH (core list)", str(len(lexicon.english))])
    rows.append(["ENGLISH (from glosses)", str(len(lexicon.english_extra))])
    print(table(rows, ["source", "entries"]))
    print(f"\nkeys {len(lexicon.entries)}   longest phrase {lexicon.max_words} words")
    return 0


def cmd_repl(args) -> int:
    tool = Toolchain(args.prefer)
    print("Franc-anglais compiler. Type an utterance, or ':q' to quit.")
    while True:
        try:
            text = input("\nfca> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if text in {":q", ":quit", "exit"}:
            return 0
        if not text:
            continue
        tokens = tool.lexer.tokenize(text)
        parsed = tool.parser.parse(tokens)
        print("  tokens  " + " ".join(f"{t.surface}/{t.cat.value}" for t in tokens))
        print("  mixture " + langid.describe(tokens))
        print("  syntax  " + ("ACCEPTED" if parsed.accepted else "REJECTED - " + parsed.error))
        print("  english " + tool.translator.translate_tokens(tokens, text).english)


def cmd_serve(args) -> int:
    from .server import serve

    serve(args.host, args.port)
    return 0


def cmd_report(args) -> int:
    """Write every artefact the written report needs into a folder."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tool = Toolchain(args.prefer)
    corpus = read_corpus(CORPUS_FILE)
    rejects = read_corpus(REJECTS_FILE)

    written: list[Path] = []

    # 1. token table over the whole corpus
    rows = []
    for text in corpus:
        for tok in tool.lexer.tokenize(text):
            if tok.cat is Cat.PUNCT:
                continue
            rows.append([tok.surface, tok.cat.value, tok.lang.value, tok.gloss[:60], tok.origin])
    written.append(_write(out / "token-table.md", "# Token table\n\n"
                          + markdown_table(rows, ["lexeme", "class", "language", "gloss", "origin"])))

    # 2. regular expressions
    patterns = regexspec.category_patterns(tool.lexicon)
    body = "\n\n".join(f"### {cat}\n\n```\n{pattern}\n```" for cat, pattern in sorted(patterns.items()))
    written.append(_write(out / "regular-expressions.md", "# Regular expressions per token class\n\n" + body))

    # 3. grammar + transformations
    raw = load_grammar(RAW_GRAMMAR_FILE)
    step1, log1 = remove_left_recursion(raw)
    step2, log2 = left_factor(step1)
    sections = [
        "# Grammar\n",
        "## Raw grammar as first drafted\n\n```\n" + raw.to_text() + "\n```",
        "## After left-recursion removal\n\n" + "\n".join(f"- {e}" for e in log1)
        + "\n\n```\n" + step1.to_text() + "\n```",
        "## After left factoring\n\n" + "\n".join(f"- {e}" for e in log2)
        + "\n\n```\n" + step2.to_text() + "\n```",
        "## Final LL(1) grammar used by the parser\n\n```\n" + tool.grammar.to_text() + "\n```",
    ]
    written.append(_write(out / "grammar.md", "\n\n".join(sections)))

    # 4. FIRST / FOLLOW and the LL(1) table
    a = tool.analysis
    ff = markdown_table(
        [[nt, "yes" if nt in a.nullable else "no",
          " ".join(sorted(a.first[nt])), " ".join(sorted(a.follow[nt]))]
         for nt in tool.grammar.nonterminals],
        ["non-terminal", "nullable", "FIRST", "FOLLOW"],
    )
    terminals = sorted({t for (_, t) in a.table})
    rows = []
    for nt in tool.grammar.nonterminals:
        row = [nt]
        for term in terminals:
            prod = a.table.get((nt, term))
            row.append(("eps" if prod is not None and not prod.rhs else " ".join(prod.rhs)) if prod else "")
        rows.append(row)
    written.append(_write(
        out / "first-follow-ll1.md",
        "# FIRST, FOLLOW and the LL(1) parsing table\n\n## FIRST / FOLLOW\n\n" + ff
        + "\n\n## LL(1) table M[A, a]\n\n" + markdown_table(rows, ["M[A,a]"] + terminals)
        + f"\n\nConflicts: {len(a.conflicts)}\n",
    ))

    # 5. accept / reject results with translations
    rows = []
    for text in corpus + rejects:
        tokens = tool.lexer.tokenize(text)
        parsed = tool.parser.parse(tokens)
        rows.append([
            text,
            "accepted" if parsed.accepted else "rejected",
            langid.profile(tokens).label,
            tool.translator.translate_tokens(tokens, text).english,
        ])
    written.append(_write(out / "parse-results.md", "# Parse results\n\n"
                          + markdown_table(rows, ["source", "verdict", "mixture", "English"])))

    # 6. frequency analysis
    report = frequency.analyse_corpus(corpus, tool.lexer)
    freq_md = [
        "# Token frequency and variation\n",
        f"- tokens: {report.tokens}\n- types: {report.types}\n"
        f"- type/token ratio: {report.type_token_ratio:.2f}\n",
        "## Most frequent tokens\n\n" + markdown_table(
            [[t, str(n)] for t, n in report.most_common(30)], ["token", "count"]),
        "## Token classes\n\n" + markdown_table(
            [[c, str(n)] for c, n in report.by_category.most_common()], ["class", "count"]),
        "## Languages\n\n" + markdown_table(
            [[c, str(n)] for c, n in report.by_language.most_common()], ["language", "count"]),
    ]
    variation = report.spelling_variation()
    if variation:
        freq_md.append("## Spelling variation\n\n" + markdown_table(
            [[k, ", ".join(v)] for k, v in variation.items()], ["normalised", "forms"]))
    written.append(_write(out / "frequency.md", "\n\n".join(freq_md)))

    # 7. the generated Flex program
    written.append(_write(out / "francanglais.l", regexspec.flex_specification(tool.lexicon)))

    for path in written:
        print("wrote " + str(path))
    return 0


def _write(path: Path, text: str) -> Path:
    path.write_text(text + "\n", encoding="utf-8")
    return path


# -- argument parsing ----------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="francanglais",
        description="Lexical and syntactic analyzer and English translator for "
                    "Camfranglais speech.",
    )
    parser.add_argument("--prefer", choices=["camfranglais", "french", "english"],
                        help="break language ties in favour of this dictionary")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_text(sp, with_file=True):
        sp.add_argument("text", nargs="*", help="text to analyze (or pipe on stdin)")
        if with_file:
            sp.add_argument("-f", "--file", help="read one utterance per line from a file")

    p = sub.add_parser("tokens", help="lexical analysis: show the token table")
    add_text(p)
    p.set_defaults(func=cmd_tokens)

    p = sub.add_parser("word", help="look one word up in every dictionary")
    p.add_argument("text", nargs="+")
    p.set_defaults(func=cmd_word)

    p = sub.add_parser("translate", help="translate a word or an utterance into English")
    add_text(p)
    p.add_argument("-v", "--verbose", action="store_true", help="show mixture and rules applied")
    p.set_defaults(func=cmd_translate)

    p = sub.add_parser("parse", help="syntactic analysis: accept or reject")
    add_text(p)
    p.add_argument("--tree", action="store_true", help="print the parse tree")
    p.add_argument("--trace", action="store_true", help="print the stack/input/action trace")
    p.add_argument("--strict", action="store_true", help="exit non-zero on rejection")
    p.set_defaults(func=cmd_parse)

    p = sub.add_parser("grammar", help="grammar rules, FIRST/FOLLOW, LL(1) table, transformations")
    p.add_argument("-g", "--grammar", help="grammar file (default grammar/fca.gram)")
    p.add_argument("--rules", action="store_true", help="list the productions")
    p.add_argument("--first-follow", action="store_true", help="print FIRST and FOLLOW sets")
    p.add_argument("--table", action="store_true", help="print the LL(1) parsing table")
    p.add_argument("--transform", action="store_true",
                   help="remove left recursion and left-factor, showing each step")
    p.set_defaults(func=cmd_grammar)

    p = sub.add_parser("corpus", help="run the whole corpus: parse verdict + translation")
    p.add_argument("-f", "--file", help="corpus file (default data/corpus.txt)")
    p.add_argument("--rejects", help="negative test file (default data/rejects.txt)")
    p.set_defaults(func=cmd_corpus)

    p = sub.add_parser("freq", help="token frequency and variation analysis")
    p.add_argument("-f", "--file", help="corpus file (default data/corpus.txt)")
    p.add_argument("--top", type=int, default=25)
    p.set_defaults(func=cmd_freq)

    p = sub.add_parser("regex", help="the regular-expression lexical specification")
    p.add_argument("--full", action="store_true", help="do not truncate the patterns")
    p.add_argument("--flex", nargs="?", const="build/francanglais.l",
                   help="write an equivalent LEX/Flex program")
    p.add_argument("--scan", nargs="*", help="scan text using the regexes alone")
    p.set_defaults(func=cmd_regex)

    p = sub.add_parser("stats", help="dictionary size and coverage")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("repl", help="interactive mode")
    p.set_defaults(func=cmd_repl)

    p = sub.add_parser("serve", help="run the web interface")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("report", help="write every report artefact to a folder")
    p.add_argument("-o", "--out", default="docs/analysis")
    p.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
