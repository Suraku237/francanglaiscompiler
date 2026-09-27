"""Reproduce coursework tables from a public, read-only corpus snapshot."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.analyzer import analyze_manual
from backend.dictionary import load_dictionary
from backend.token_statistics import token_statistics
from compiler.lexer import lexicon
from compiler.lexer.reference import CSV_PATH, load_classified_lexicon
from compiler.parser.service import analyze_grammar
from compiler.parser.yaounde import GRAMMAR
from compiler.tests.yaounde_cases import CORPUS_CASES

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = Path("docs") / "evidence" / "final-corpus-20260927.json"
ANALYSIS = Path("docs") / "evidence" / "final-analysis-20260927.json"
TERMINALS = {
    "FRENCH_FUNCTION_WORD": "FF", "ENGLISH_FUNCTION_WORD": "EF",
    "NOUN": "N", "VERB": "V", "ADJECTIVE": "ADJ", "ADVERB": "ADV",
    "AMBIGUOUS": "AMB", "PIDGIN_MARKER": "PID", "PUNCTUATION": "PUNC",
    "UNKNOWN": "UNK", "SLANG": "SL", "NUMBER": "NUM",
}
NONTERMINALS = {
    "Utterance": "Ut", "Clause": "Cl", "SubjectTail": "St",
    "BareSubjectTail": "Bt", "PredicateTail": "Pt", "LinkedPhrase": "Lp",
    "ModifiedNominal": "Mn", "AdverbTail": "At", "ComplementTail": "Ct",
    "Nominal": "Nm", "Nominal_LR1": "Nr", "Utterance_LF1": "Uf",
}
CONTROLS = (
    ("C01", "", False, "Empty input: no Clause derivation."),
    ("C02", "school", False, "Noun-only fragment lacks a predicate."),
    ("C03", "je", False, "Incomplete subject-led clause."),
    ("C04", "je suis kass.", True, "One optional punctuation token."),
    ("C05", "je suis kass?!", False, "Two punctuation tokens exceed the one-token suffix."),
    ("C06", "je je suis", False, "Unsupported category order, despite known words."),
    ("C07", "je suis alli", False, "UNKNOWN is not a grammar terminal."),
)


def tex(value: object) -> str:
    replacements = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
        "&": r"\&", "#": r"\#", "_": r"\_", "%": r"\%",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def symbol(value: str) -> str:
    if value == "epsilon":
        return r"\(\epsilon\)"
    return r"\texttt{" + tex(TERMINALS.get(value, NONTERMINALS.get(value, value))) + "}"


def rhs(values: list[str]) -> str:
    return " ".join(symbol(value) for value in values) if values else symbol("epsilon")


def table(headers: list[str], rows: list[list[str]], columns: str) -> str:
    return "\n".join([
        r"\par\noindent",
        r"\begin{tabularx}{\linewidth}{@{}" + columns + r"@{}}",
        r"\toprule", " & ".join(r"\textbf{" + header + "}" for header in headers) + r"\\",
        r"\midrule",
        *(" & ".join(row) + r"\\" for row in rows),
        r"\bottomrule", r"\end{tabularx}\par", "",
    ])


def side_by_side(blocks: list[str]) -> str:
    return "\n".join(
        r"\begin{minipage}[t]{0.48\linewidth}" + "\n" + block
        + "\n" + r"\end{minipage}"
        + (r"\hfill" if index % 2 == 0 else r"\par\bigskip")
        for index, block in enumerate(blocks)
    )


def source_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8-sig").encode("utf-8")).hexdigest()


def compute_evidence(root: Path) -> dict[str, Any]:
    corpus = json.loads((root / SNAPSHOT).read_text(encoding="utf-8"))
    statements = corpus["statements"]
    if corpus["format"] != 1 or [entry["text"] for entry in statements] != [case.text for case in CORPUS_CASES]:
        raise ValueError("The documentation corpus must match all twelve exact regression inputs in order.")
    if corpus["saved_grammar"].strip() != GRAMMAR.strip():
        raise ValueError("The documentation snapshot no longer matches the corpus grammar source.")
    learned = corpus["reviewed_lexicon"]
    if not isinstance(learned, dict) or any(
        not isinstance(word, str) or category not in lexicon.TERMINAL_CATEGORIES
        for word, category in learned.items()
    ):
        raise ValueError("The snapshot contains an invalid reviewed lexicon.")
    grammar = analyze_grammar(corpus["saved_grammar"])
    results = []
    for entry, case in zip(statements, CORPUS_CASES, strict=True):
        result = analyze_manual(entry["text"], grammar, learned)
        lexical, parsed = result["lexical"], result["parse"]
        if tuple(token["category"] for token in lexical["tokens"]) != case.categories or parsed["accepted"] != case.accepted:
            raise ValueError(f"Computed result changed for {entry['id']}; review the corpus before publishing.")
        results.append({
            **entry, "lexical": lexical, "parse": parsed,
            "vocabulary_accepted": not lexical["statistics"]["unknown_tokens"],
            "rationale": case.reason,
        })
    controls = []
    for identifier, text, expected, rationale in CONTROLS:
        result = analyze_manual(text, grammar, learned)
        if result["parse"]["accepted"] != expected:
            raise ValueError(f"Boundary control {identifier} did not match its expected result.")
        controls.append({
            "id": identifier, "text": text, "accepted": expected, "rationale": rationale,
            "vocabulary_accepted": not result["lexical"]["statistics"]["unknown_tokens"],
            "parse": result["parse"],
        })
    source_paths = [
        *(root / "compiler" / "lexer").glob("*.py"),
        *(root / "compiler" / "parser").glob("*.py"),
        root / "compiler" / "tests" / "yaounde_cases.py",
        root / "backend" / "analyzer.py", root / "backend" / "token_statistics.py",
        root / "backend" / "dictionary.py", CSV_PATH,
        *(root / "dictionary").glob("*.md"),
        root / SNAPSHOT,
    ]
    return {
        "format": 1, "snapshot_date": corpus["snapshot_date"],
        "source_revision": corpus["source_revision"],
        "provenance_status": corpus["provenance_status"],
        "corpus_snapshot": SNAPSHOT.as_posix(),
        "source_hash_encoding": "UTF-8 without BOM; CRLF and CR normalized to LF; no other text changes.",
        "source_sha256": {
            path.relative_to(root).as_posix(): source_fingerprint(path)
            for path in sorted(set(source_paths))
        },
        "dictionary_entries": len(load_dictionary()),
        "reference_csv_rows": len(load_classified_lexicon()),
        "statistics": token_statistics(
            token for result in results for token in result["lexical"]["tokens"]
        ),
        "grammar": grammar, "results": results, "controls": controls,
    }


def render_fragments(evidence: dict[str, Any]) -> dict[str, str]:
    results, grammar, stats = evidence["results"], evidence["grammar"], evidence["statistics"]
    productions = [
        (lhs, production) for lhs, alternatives in grammar["transformed"].items()
        for production in alternatives
    ]
    production_ids = {(lhs, tuple(production)): f"P{index:02d}" for index, (lhs, production) in enumerate(productions, 1)}
    accepted = sum(result["parse"]["accepted"] for result in results)
    switches = sum(len(result["lexical"]["code_mixed_spans"]) for result in results)
    counts = {
        "CorpusTokens": stats["total_tokens"], "CorpusForms": len(stats["frequencies"]),
        "CorpusAccepted": accepted, "CorpusRejected": len(results) - accepted,
        "CorpusSwitches": switches, "DictionaryCount": evidence["dictionary_entries"],
        "ReferenceRows": evidence["reference_csv_rows"],
        "GrammarProductions": len(productions),
        "GrammarCells": sum(len(row) for row in grammar["table"].values()),
    }
    fragments = {"metrics.tex": "\n".join(
        r"\newcommand{\%s}{%s}" % (name, value) for name, value in counts.items()
    ) + "\n"}
    for part, entries in (("a", results[:6]), ("b", results[6:])):
        fragments[f"statements-{part}.tex"] = table(
            ["ID", "Exact raw statement", "Supplied French meaning"],
            [[tex(entry["id"]), r"\texttt{" + tex(entry["text"]) + "}", tex(entry["french_gloss"])] for entry in entries],
            r"L{0.7cm} >{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}X",
        )
    for part, entries in zip(("a", "b", "c"), (results[:4], results[4:8], results[8:]), strict=True):
        blocks = []
        for entry in entries:
            tokens = entry["lexical"]["tokens"]
            blocks.append(
                r"\textbf{" + entry["id"] + r"}\hfill " + str(len(tokens)) + " tokens\n\n"
                + r"{\raggedright\texttt{" + tex(entry["text"]) + r"}\par}" + "\n\n"
                + table(
                    ["No.", "Raw token", "Label"],
                    [[str(index), r"\texttt{" + tex(token["text"]) + "}", symbol(token["category"])]
                     for index, token in enumerate(tokens, 1)], "r X l",
                )
            )
        fragments[f"tokens-{part}.tex"] = side_by_side(blocks) + "\n"
    fragments["categories.tex"] = table(
        ["Category", "Code", "Count", "Share"],
        [[tex(category), symbol(category), str(count), f"{100 * count / stats['total_tokens']:.1f}\\%"]
         for category, count in sorted(stats["category_counts"].items(), key=lambda item: (-item[1], item[0]))],
        "X l r r",
    )
    repeated = [item for item in stats["frequencies"] if item["count"] > 1]
    fragments["frequencies.tex"] = table(
        ["Case-folded form", "Occurrences"],
        [[r"\texttt{" + tex(item["token"]) + "}", str(item["count"])] for item in repeated], "X r",
    )
    singletons = [item["token"] for item in stats["frequencies"] if item["count"] == 1]
    fragments["singletons.tex"] = ", ".join(r"\texttt{" + tex(word) + "}" for word in singletons) + ".\n"
    fragments["language-spans.tex"] = table(
        ["ID", "Exact emitted transition endpoints"],
        [[entry["id"], "; ".join(r"\texttt{" + tex(span) + "}" for span in entry["lexical"]["code_mixed_spans"]) or "None emitted"]
         for entry in results],
        r"L{0.7cm} >{\raggedright\arraybackslash}X",
    )
    fragments["grammar-original.tex"] = table(
        ["LHS", "Original alternatives"],
        [[symbol(lhs), r" \(\mid\) ".join(rhs(production) for production in alternatives)]
         for lhs, alternatives in grammar["original"].items()],
        r"L{0.9cm} >{\raggedright\arraybackslash}X",
    )
    fragments["productions.tex"] = side_by_side([
        table(
            ["ID", "Transformed production"],
            [[production_ids[(lhs, tuple(production))], symbol(lhs) + r" \(\rightarrow\) " + rhs(production)]
             for lhs, production in part],
            r"l >{\raggedright\arraybackslash}X",
        )
        for part in (productions[:20], productions[20:])
    ]) + "\n"
    fragments["first-follow.tex"] = table(
        ["NT", "FIRST", "FOLLOW"],
        [[symbol(lhs), ", ".join(symbol(value) for value in grammar["first"][lhs]),
          ", ".join(symbol(value) for value in grammar["follow"][lhs])]
         for lhs in grammar["nonterminals"]],
        r"L{1.8cm} >{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}X",
    )
    terminals = [*grammar["terminals"], "$"]
    fragments["ll1-table.tex"] = table(
        ["NT", *(symbol(terminal) for terminal in terminals)],
        [[symbol(lhs), *(production_ids[(lhs, tuple(grammar["table"][lhs][terminal]))]
                        if terminal in grammar["table"][lhs] else "--" for terminal in terminals)]
         for lhs in grammar["nonterminals"]],
        "l " + " ".join(">{\\centering\\arraybackslash}X" for _ in terminals),
    )

    def trace(entry: dict[str, Any]) -> str:
        rows = []
        for index, step in enumerate(entry["parse"]["trace"], 1):
            action = step["action"]
            if not isinstance(action, str):
                raise ValueError("Parse trace actions must be text.")
            if action.startswith("Apply "):
                lhs, raw_rhs = action.removeprefix("Apply ").split(" -> ")
                production = () if raw_rhs == "epsilon" else tuple(raw_rhs.split())
                action = production_ids[(lhs, production)]
            elif action.startswith("Match "):
                action = "match " + TERMINALS.get(action[6:], action[6:])
            elif action.startswith("Accept:"):
                action = "accept"
            elif action.startswith("Reject:"):
                action = "reject"
            else:
                raise ValueError(f"Unexpected parse trace action: {action}")
            rows.append([str(index), rhs(step["stack"]), rhs(step["remaining"]), tex(action)])
        return table(["Step", "Stack (top at right)", "Remaining input", "Action"], rows,
                     r"r >{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}X l")

    fragments["trace-accepted.tex"] = trace(results[1])
    fragments["trace-rejected-a.tex"] = trace(results[8])
    fragments["trace-rejected-b.tex"] = trace(results[9])
    fragments["outcomes.tex"] = table(
        ["ID", "Tokens", "Vocabulary", "CFG", "Consumed", "Trace rows"],
        [[entry["id"], str(len(entry["lexical"]["tokens"])),
          "Pass" if entry["vocabulary_accepted"] else "Fail",
          "Accept" if entry["parse"]["accepted"] else "Reject",
          str(entry["parse"]["consumed"]), str(len(entry["parse"]["trace"]))]
         for entry in results], "l r X X r r",
    )
    fragments["controls.tex"] = table(
        ["ID", "Constructed control", "Vocabulary", "CFG"],
        [[entry["id"], r"\texttt{" + tex(entry["text"]) + "}" if entry["text"] else "(empty)",
          "Pass" if entry["vocabulary_accepted"] else "Fail", "Accept" if entry["accepted"] else "Reject"]
         for entry in evidence["controls"]], "l X l l",
    )
    return fragments


def write_or_check(root: Path, *, check: bool) -> dict[str, int]:
    evidence = compute_evidence(root)
    outputs = {
        ANALYSIS: json.dumps(evidence, indent=2, ensure_ascii=True) + "\n",
        **{Path("docs") / "report-data" / name: text for name, text in render_fragments(evidence).items()},
    }
    for relative, content in outputs.items():
        destination = root / relative
        if check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != content:
                raise ValueError(f"Missing or stale report evidence: {relative}")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
    return {
        "generated_files": len(outputs), "statements": len(evidence["results"]),
        "tokens": evidence["statistics"]["total_tokens"],
        "accepted": sum(result["parse"]["accepted"] for result in evidence["results"]),
        "rejected": sum(not result["parse"]["accepted"] for result in evidence["results"]),
        "boundary_controls": len(evidence["controls"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if any committed evidence/table differs.")
    args = parser.parse_args()
    try:
        summary = write_or_check(ROOT, check=args.check)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"Coursework evidence generation failed: {exc}\n")
    print(json.dumps({"verified" if args.check else "generated": True, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
