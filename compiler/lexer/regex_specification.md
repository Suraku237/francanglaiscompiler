# Lexical Specification

This is the custom lexical specification for the Francanglais analyzer,
implemented in `compiler/lexer/`. It satisfies the assignment's
requirement for "regular expressions for token types" plus a custom
lexical analyzer (Python).

## 1. Tokenization (segmentation)

Raw text is split into tokens using a single regex
(`compiler/lexer/tokenizer.py`, `TOKEN_SPLIT_RE`):

```python
COMBINING_MARKS = r"\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f"
LETTERS = rf"[^\W\d_]+(?:[{COMBINING_MARKS}]+[^\W\d_]*)*"
WORD = rf"{LETTERS}(?:['\u2018\u2019\u02bc-]{LETTERS})*"
TOKEN_PATTERN = WORD + r'|\d+(?:[.,]\d+)?|[.,!?;:"()]|\S'
```

Internal apostrophes and hyphens keep `j'ai`, `n'y` and `go-slow` together.
The five supported combining-mark blocks attach to preceding letters, so
decomposed accents remain inside their original word. A standalone combining
mark remains an unsupported token; this is not a complete Unicode grapheme parser.

The last alternative prevents the parser from accepting a sentence after
silently dropping unsupported symbols. These symbols are retained as `UNKNOWN`.
Raw spelling, accents, straight/curly apostrophes and case are not rewritten.

## 2. Token classification (lexical categories)

Without a supplied learned lexicon, each WORD token is classified in this order against
`compiler/lexer/lexicon.py`:

| Order | Category                | How it's recognized                                         |
|-------|--------------------------|--------------------------------------------------------------|
| 1     | NUMBER / PUNCTUATION     | Regex rules in `TOKEN_REGEX_RULES`                            |
| 2     | SLANG                    | Exact match against `SLANG_WORDS`                             |
| 3     | PIDGIN_MARKER            | Exact match against `PIDGIN_MARKERS`                          |
| 4     | NOUN                     | Exact match against `NOUN_LEXICON`                            |
| 5     | VERB                     | Exact match against `VERB_LEXICON`                            |
| 6     | FRENCH_FUNCTION_WORD     | Exact match against `FRENCH_FUNCTION_WORDS`                   |
| 7     | ENGLISH_FUNCTION_WORD    | Exact match against `ENGLISH_FUNCTION_WORDS`                  |
| 8     | ENGLISH_VERB_LIKE        | Fallback heuristic: ends in `-ing` / `-ed`                    |
| 9     | FRENCH_VERB_LIKE         | Fallback heuristic: ends in `-er` / `-ir` / `-re` (len > 3)    |
| 10    | UNKNOWN                  | None of the above matched                                     |

Why lexicon lists rather than pure regex for NOUN/VERB/SLANG: these are
open-class, semantically defined categories (what a word *means*, not
its surface shape), so — like a real POS tagger — they're recognized
by lookup against a curated word list, not by pattern alone. The
regex layer handles the categories that genuinely are structural
(numbers, punctuation) and the two morphological fallback rules.
**These lists are a starting point and should be extended from your
own collected `dataset.csv`** before finalizing frequency results.

The API, coursework parser/analyzer, command-line corpus runner and exported
own-data regression tests supply an optional learned lexicon. Only explicitly
`approved` `Word` rows labeled `francanglais` or `pidgin`, containing exactly one
token and a supported `lexical_category`, contribute. Reviewed labels take
precedence over the static word lists, after the structural number/punctuation
rules. Conflicting labels are excluded. Matching uses Unicode NFC, case folding
and straight/left-curly/right-curly/modifier-apostrophe normalization without removing accents.
The ASCII matching path uses equivalent lowercasing to avoid unnecessary Unicode work.
Structural regular expressions are precompiled and must match the entire token.
Sentence/phrase rows,
unreviewed rows and unspecified/mixed-language rows do not teach token categories;
no entry acts as a wildcard. Calling `analyze_sentence(text)` without the optional
lexicon retains the deterministic base behavior and never reads the CSV.

## 3. Multi-word verb phrases / idioms

Some verb meanings in Camfranglais are idiomatic phrases rather than
single words (e.g. "drop me", "dey for front"). These are matched
against the whole sentence with their own regex patterns in
`lexicon.VERB_PHRASES`, e.g.:

```text
\bdrop\s+me\b
\bhala\s+me\b(?:\s+[\w<supported combining marks>]+){0,3}\s+money\b
\bdey\s+for\s+front\b
\bje\s+wanda\b  (slang phrase)
```

`<supported combining marks>` denotes the explicit `COMBINING_MARKS` ranges
above; the actual compiled regular expressions are returned by the compiler API.
Verb and slang phrase helpers use the same complete-token boundaries:
matches cannot begin or end inside a hyphenated/apostrophe word or before an
attached combining mark. Case-insensitive candidates must also pass
accent-preserving normalized matching. Returned annotations retain the exact
source case and spacing, preserve repeated occurrences and follow source order.
They annotate, but never replace or collapse, the individual tokens supplied to
the parser. For example, `DROP ME` remains `VERB UNKNOWN` with the base lexicon.

## 4. Code-mixed span detection

A token's inferred language (FR / EN / PID) comes from its category
via `LANGUAGE_MAP`. Walking through a sentence's tokens, any time the
running language changes between two lexically-tagged tokens (skipping
over neutral/unknown words in between), that transition is recorded as
a code-mixed span — e.g. `"Le ... don"` (French → Pidgin) or
`"for ... le"` (English → French).

## 5. Frequency & variation analysis

`compiler/lexer/frequency.py` counts the supplied tokens:
- raw token frequency (lowercased), for the top-N frequency report
- token counts per lexical category, to see the overall composition
  (e.g. how much of the corpus is Pidgin markers vs French function
  words vs unclassified content)

Both lists and single-use iterators produce complete text and category counts.
Raw accented spellings are not silently merged. The coursework report separately
shows observed spelling/case/accent variation candidates, not semantic synonyms.
Counts cover the saved entries supplied to the report; imported reference
dictionaries and constructed practice examples are not automatically added.

## 6. Performance and reproducibility

Regexes are prepared once; caller-provided reviewed annotations are consulted
afresh, not cached across projects. Grammar analysis caches only the public
illustrative starter and its whitespace-stripped saved form. Its cache contains
one immutable JSON value and returns independent decoded results; custom
grammars, private comments, corpus text and annotations are not cached there.
All grammar and parser bounds and conflict checks remain in force.

Run `python -m tools.benchmark_compiler --samples 21 --iterations 150` from
the repository root. The synthetic benchmark includes lexer, phrase, frequency,
grammar and parser-boundary cases, plus an alternating-order comparison of
cached versus uncached preparation of the actual saved starter. Its timings
are batch-average microbenchmarks, not HTTP latency or linguistic accuracy.
Earlier before/after captures are historical measurements, not guarantees that
every operation improved or that deterministic analysis replaces translation.

## Known limitations (worth naming in the report)

- The lexicon-lookup approach can't classify a word it hasn't seen —
  every UNKNOWN token in `output/token_table.csv` is a candidate to
  add to the lexicon once you review your real data.
- The two morphological fallback rules (`-ing`/`-ed`, `-er`/`-ir`/`-re`)
  are heuristics, not certainties — e.g. a French noun ending in
  `-ère` would be mis-tagged FRENCH_VERB_LIKE. Worth spot-checking
  these in the token table before citing counts in the report.
- Code-mixed span detection works at the token-transition level, not
  full grammatical analysis — it's a proxy for "this sentence mixes
  languages," not a syntactic parse (that's Phase 3).