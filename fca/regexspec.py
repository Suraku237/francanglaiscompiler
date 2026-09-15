"""Regular-expression specification of the token classes.

The scanner in :mod:`fca.lexer` is dictionary-driven, which is convenient but hides the
underlying lexical specification. This module makes that specification explicit:

* :func:`category_patterns` gives one regular expression per token class;
* :func:`master_pattern` combines them into a single maximal-munch scanner that can be
  run directly with :func:`re.finditer`, proving the specification is complete;
* :func:`flex_specification` emits an equivalent LEX/Flex ``.l`` program.
"""

from __future__ import annotations

import re

from .lexicon import Lexicon, load_lexicon
from .tokens import Cat

#: Patterns that are not tied to any particular dictionary entry.
GENERAL_PATTERNS: dict[str, str] = {
    "NUM": r"\d+(?:[.,]\d+)?",
    "PUNCT": r"[.,!?;:]",
    "UNKNOWN": r"[A-Za-z\u00C0-\u00FF]+(?:['\u2019-][A-Za-z\u00C0-\u00FF]+)*",
}


def _term_regex(term: str) -> str:
    """``no wahala`` -> ``no\\s+wahala`` so spacing in the source is flexible."""
    return r"\s+".join(re.escape(part) for part in term.split())


def category_terms(lex: Lexicon | None = None) -> dict[str, list[str]]:
    """Dictionary terms grouped by the category the scanner assigns them."""
    lex = lex or load_lexicon()
    groups: dict[str, list[str]] = {}
    for term, entries in lex.entries.items():
        for entry in entries:
            groups.setdefault(entry.cat.value, [])
            if term not in groups[entry.cat.value]:
                groups[entry.cat.value].append(term)
    for cat, terms in groups.items():
        terms.sort(key=lambda t: (-len(t), t))
    return groups


def category_patterns(lex: Lexicon | None = None) -> dict[str, str]:
    """One regular expression per token class, longest alternative first."""
    patterns = {
        cat: r"\b(?:" + "|".join(_term_regex(t) for t in terms) + r")\b"
        for cat, terms in category_terms(lex).items()
    }
    for cat, pattern in GENERAL_PATTERNS.items():
        patterns.setdefault(cat, pattern)
    return patterns


def master_pattern(lex: Lexicon | None = None) -> tuple[re.Pattern, dict[str, Cat]]:
    """A single maximal-munch scanner regex plus the term-to-category map."""
    lex = lex or load_lexicon()
    lookup: dict[str, Cat] = {}
    for term, entries in lex.entries.items():
        lookup[term] = entries[0].cat

    terms = sorted(lookup, key=lambda t: (-len(t), t))
    alternation = "|".join(_term_regex(t) for t in terms)
    pattern = (
        rf"(?P<DICT>\b(?:{alternation})\b)"
        rf"|(?P<NUM>{GENERAL_PATTERNS['NUM']})"
        rf"|(?P<PUNCT>{GENERAL_PATTERNS['PUNCT']})"
        rf"|(?P<WORD>{GENERAL_PATTERNS['UNKNOWN']})"
    )
    return re.compile(pattern, re.IGNORECASE), lookup


def scan(text: str, lex: Lexicon | None = None) -> list[tuple[str, str]]:
    """Scan with the regular expressions alone. Returns ``(lexeme, category)``."""
    from .lexicon import normalize

    regex, lookup = master_pattern(lex)
    out: list[tuple[str, str]] = []
    for match in regex.finditer(text):
        lexeme = match.group(0)
        if match.lastgroup == "DICT":
            cat = lookup.get(normalize(lexeme), Cat.UNKNOWN)
            out.append((lexeme, cat.value))
        elif match.lastgroup == "NUM":
            out.append((lexeme, Cat.NUM.value))
        elif match.lastgroup == "PUNCT":
            out.append((lexeme, Cat.PUNCT.value))
        else:
            out.append((lexeme, Cat.UNKNOWN.value))
    return out


def flex_specification(lex: Lexicon | None = None) -> str:
    """Emit an equivalent LEX/Flex program for the same token classes."""
    groups = category_terms(lex)
    rules: list[str] = []
    ordered = sorted(
        ((term, cat) for cat, terms in groups.items() for term in terms),
        key=lambda pair: (-len(pair[0]), pair[0]),
    )
    for term, cat in ordered:
        literal = '"' + term.replace('"', '\\"') + '"'
        rules.append(f"{literal:<28} {{ emit(\"{cat}\", yytext); }}")

    body = "\n".join(rules)
    return f"""%{{
/* ------------------------------------------------------------------
 * francanglais.l - lexical specification for Yaoundé street speech.
 * Generated from dictionary/*.md by fca/regexspec.py. Do not edit by
 * hand: regenerate with  python main.py regex --flex
 *
 * Build:  flex francanglais.l && cc lex.yy.c -o francanglais
 * Run:    ./francanglais < corpus.txt
 * ------------------------------------------------------------------ */
#include <stdio.h>
static void emit(const char *cat, const char *lexeme) {{
    printf("%-8s %s\\n", cat, lexeme);
}}
%}}

%option noyywrap
%option caseless

DIGIT   [0-9]
LETTER  [A-Za-z]
WORD    {{LETTER}}+('{{LETTER}}+)?

%%

{body}

{{DIGIT}}+                   {{ emit("NUM", yytext); }}
[.,!?;:]                     {{ emit("PUNCT", yytext); }}
{{WORD}}                     {{ emit("UNKNOWN", yytext); }}
[ \\t\\r\\n]+                  ; /* skip whitespace */
.                            {{ emit("UNKNOWN", yytext); }}

%%

int main(void) {{
    yylex();
    return 0;
}}
"""
