# Franc-anglais Compiler

A lexical and syntactic analyzer, and English translator, for the informal urban speech
of Yaoundé — Cameroonian Pidgin (Kamtok) and Camfranglais, including utterances that
mix either of them with English, and Camfranglais mixed with French.

Built for **CS4110 Compiler Construction**, ICT University, Summer 2026.

```
$ python main.py translate "Mola, le courant don kwenchi again, on va faire comment?"
Friend, the electricity has extinguished again, what can we do?

$ python main.py parse "Di pikin dem dei for haus." --tree
ACCEPTED  Di pikin dem dei for haus.
  categories: DET NOUN PLUR COP PREP NOUN PUNCT
```

No third-party packages. Python 3.10 or newer.

---

## 1. What it does

| Stage | Module | Output |
|---|---|---|
| Dictionary loading | [fca/lexicon.py](fca/lexicon.py) | ~880 vocabulary keys parsed from markdown tables |
| Lexical analysis | [fca/lexer.py](fca/lexer.py) | tokens tagged with class, language and gloss |
| Regex specification | [fca/regexspec.py](fca/regexspec.py) | one regex per token class, plus a generated Flex program |
| Language ID | [fca/langid.py](fca/langid.py) | the mixture profile of an utterance |
| Frequency analysis | [fca/frequency.py](fca/frequency.py) | counts, type/token ratio, spelling variation |
| Grammar tooling | [fca/grammar.py](fca/grammar.py), [fca/transformations.py](fca/transformations.py), [fca/analysis.py](fca/analysis.py) | left-recursion removal, left factoring, FIRST/FOLLOW, LL(1) table |
| Parsing | [fca/parser.py](fca/parser.py) | accept/reject, parse tree, stack trace, error position |
| Translation | [fca/translate.py](fca/translate.py), [fca/morphology.py](fca/morphology.py) | English output |
| Web interface | [fca/server.py](fca/server.py), [web/](web/) | browser front end over all of the above |

## 2. Quick start

```bash
cd francanglaiscompiler

python main.py serve                     # web interface at http://127.0.0.1:8000
python main.py repl                      # interactive: tokens, mixture, parse, translation
python main.py corpus                    # run the whole corpus, accept/reject + translation
python main.py report                    # write every report artefact to docs/analysis/
python -m unittest discover -s tests -t . # 62 tests
```

### Every command

```bash
python main.py tokens    "A no get moni for taxi."        # the token table
python main.py word      chop wahala njoh                 # dictionary lookup, all readings
python main.py translate "Make wi go maket." -v           # translation + rules applied
python main.py parse     "Na so." --tree --trace          # parse tree and the LL(1) trace
python main.py grammar   --first-follow --table           # FIRST/FOLLOW and M[A,a]
python main.py grammar   -g grammar/fca_raw.gram --transform   # the two transformations
python main.py freq                                       # frequency and variation
python main.py regex     --flex build/francanglais.l      # generate a LEX/Flex program
python main.py regex     --scan "a don tchop for kwatt"   # scan using the regexes alone
python main.py stats                                      # dictionary coverage
```

Add `--prefer pidgin` (or `camfranglais`, `french`) **before the sub-command** to break
language ties in favour of one dictionary — useful when a word such as `chop`, `wahala`
or `moto` belongs to several at once:

```bash
python main.py --prefer camfranglais tokens "A don chop."
```

## 3. Translating

Three kinds of input work:

```bash
# a single word - every reading is shown
$ python main.py word njoh
language      class  English
------------  -----  -------------------------------------------
CAMFRANGLAIS  ADV    free of charge; something obtained for nothing

# a whole utterance
$ python main.py translate "Abeg drop me for junction."
Please drop me at the street junction.

# a file, one utterance per line
$ python main.py translate -f data/corpus.txt
```

Mixtures are handled without being told which language is in play:

| Input | Mixture | English |
|---|---|---|
| `A don tchop ma moni.` | Pidgin + Camfranglais | I have eaten my money. |
| `A no fit download notin.` | Pidgin + English | I can not download anything. |
| `Le pays est dur oh!` | French + Camfranglais | Times are hard! |
| `Le reseau ndem again.` | French + Camfranglais + English | The network fails again. |

## 3a. The web interface

```bash
python main.py serve            # then open http://127.0.0.1:8000
python main.py serve --port 9000
```

A single page that runs the whole toolchain on whatever you type:

* **Auto-generate** — builds a fresh sentence in the selected language and translates it
  straight away. Useful when you want something to try without thinking one up.
* **Check language** — names the mixture and gives the share of each language.
* **Translate** — the English output, with the source mixture and any rules the
  translator had to apply.
* **Language** — the dictionary to generate from, and the tie-break for reading, which
  is the same thing `--prefer` does.
* **Analysis** — the accept/reject verdict, the category sequence, the full token table
  and the parse tree on demand. This is the panel to screenshot for the report.
* **Dictionary** — when the input is a single word, every reading it has.

The server is standard library only and binds to `127.0.0.1`. It exposes two endpoints:
`POST /api/analyze` returns the token stream, the mixture profile, the parse verdict and
the translation together, and `POST /api/sample` returns a generated sentence.

Generation ([fca/generate.py](fca/generate.py)) fills category sequences the LL(1)
grammar accepts with vocabulary from [data/generation.json](data/generation.json), then
parses each candidate and only returns one the parser accepts — so the button can never
produce something the analyzer then rejects. It obeys the same composition rule: a
Pidgin sentence draws only on Pidgin and English, a Camfranglais one only on
Camfranglais, French and English. Patterns the chosen family cannot fill are dropped,
which is why `make` and the plural `dem` never appear in a Camfranglais sentence.

## 4. How the pieces work
### 4.1 The dictionaries are the source of truth

`dictionary/pidgin.md`, `dictionary/camfranglais.md` and `dictionary/french_core.md` are
ordinary markdown tables. The loader reads the term column, the gloss column and the
section heading, and infers a grammatical category from them:

* a heading containing *verb* makes its rows verbs, *describing* makes them adjectives,
  *number* makes them numerals, and so on;
* a gloss beginning `to …` marks a verb regardless of the section;
* `data/pos_overrides.json` overrides both for the function words that carry the
  grammar — pronouns, tense markers, prepositions, question words.

To extend the vocabulary, add a row to a table. No code changes. `data/extra_lexicon.md`
holds the additions this project needed (determiners, transport and utility nouns, more
slang) so the two reference dictionaries stay untouched.

### 4.2 Lexical analysis

The scanner does **maximal munch over phrases**, not just words, because `no wahala`,
`njama njama` and `c'est comment` are single lexical items. It then resolves two kinds
of ambiguity:

**Language.** A word may be in several dictionaries. `chop`, `wahala`, `moto` and
`kombi` are shared between Pidgin and Camfranglais; `taxi`, `me` and `note` are shared
with English. Every token keeps the full set of languages that recognise it (`langs`),
which is what lets the mixture detector distinguish *this utterance is Pidgin* from
*this word merely could be Pidgin*.

The two varieties compose differently, and the analyzer keeps them apart:

| Variety | Composes with |
|---|---|
| Pidgin | Pidgin alone, or Pidgin + English |
| Camfranglais | Camfranglais + French (usually), Camfranglais alone, or French + English |

So a word shared by both is settled by the company it keeps rather than by a fixed
priority: the unambiguous words in the utterance vote for a family, and the shared ones
follow the winner. `A don chop di rais` reads `chop` as Pidgin; `La chop va tchop` reads
the same word as Camfranglais. A tie leaves the default order alone, and `--prefer`
overrides the whole mechanism. Only the same word class is ever swapped - Pidgin `go`
(future marker) and Camfranglais `go` (girl) are different words that happen to be
spelled alike.

**Category.** `chop` is a noun and a verb; `go` is a verb and the future marker; `di` is
the continuous marker and the definite article. These are settled from context — the
classic "lexer hack":

```
di chop         DET  NOUN     the food
a don chop      PRON TMA VERB I have eaten
a go maket      PRON VERB NOUN I go to the market
a go chop       PRON TMA  VERB I will eat
```

**French elision.** `j'ai`, `l'argent` and `qu'on` are scanned as two words, since the
clitic carries its own grammar. The split is skipped when the whole form is itself a
dictionary entry (`c'est comment`, `aujourd'hui`), and both halves are tagged French,
which is what stops `ai` (*have*) being read as Pidgin `ai` (*eye*).

Words in no dictionary are kept, marked `UNKNOWN`, and guessed as noun or verb from
their neighbours, so one unfamiliar word does not derail the parse.

### 4.3 The regular-expression specification

`fca/regexspec.py` makes the lexical specification explicit. `python main.py regex`
prints one regular expression per token class; `--scan` runs a single combined regex
over the input and produces the same token stream as the dictionary scanner (this is
asserted in the tests); `--flex` writes an equivalent LEX/Flex `.l` program:

```bash
python main.py regex --flex build/francanglais.l
flex build/francanglais.l && cc lex.yy.c -o francanglais
./francanglais < data/corpus.txt
```

### 4.4 Syntactic analysis

Two grammar files:

* `grammar/fca_raw.gram` — the rules as first drafted from the corpus. Left-recursive
  and unfactored on purpose.
* `grammar/fca.gram` — the working grammar: **45 productions, 15 non-terminals, LL(1)
  with zero conflicts**.

`python main.py grammar -g grammar/fca_raw.gram --transform` applies left-recursion
removal and left factoring to the raw grammar and prints every rewrite it makes, which
is the material for the corresponding section of the report.

The core of the working grammar:

```
Utterance -> Openers Clause Rest
Clause    -> QWORD QClause | MAKE Clause | NP Predicate | VG | eps
Predicate -> VG | ADJ Args | PP Args | ADV Args | eps
VG        -> NEG VG | TMA VG | VERB Args | COP Comp
Args      -> NP Args | PP Args | ADV Args | ADJ Args | PART Args | VG | eps
NP        -> PRON | DET AdjList NHead | POSS AdjList NHead | NUM AdjList NHead | NHead
NHead     -> NOUN Plur | UNKNOWN Plur
```

It is designed around what this variety actually does:

* `VG -> NEG VG | TMA VG | …` mirrors the marker stack `i no don di chop`;
* `Predicate -> ADJ Args | PP Args` allows the **zero copula** (`a hongri`, `a for haus`);
* `Args -> VG` allows **serial verbs** (`carry me go Mvog-Ada`);
* `NHead -> NOUN Plur` handles the post-nominal plural (`pikin dem`);
* two noun phrases in a row give the ditransitive (`gi mi moni`, `drop me for junction`).

Two restrictions were accepted to keep the grammar conflict-free, and both are worth
discussing in the report:

1. **A bare adjective cannot open a noun phrase.** `di big moto` is fine, `big moto dey
   come` is not, because a noun-initial `ADJ` would be ambiguous between a modifier and
   a predicate.
2. **A numeral must modify a noun.** `tu kolo` parses, a bare `fifti` as a whole
   utterance does not.

The parser is a table-driven predictive parser with an explicit stack. `--trace` prints
the (stack, remaining input, action) triple at every step; a rejection reports the
offending token, its position and the set of categories the table expected.

### 4.5 Translation

Transfer-based, in three stages.

**Lexical transfer.** Each token becomes its English gloss. `data/translation_overrides.json`
supplies equivalents where the dictionary *describes* a word instead of translating it
(`na wa` is glossed "Expression of astonishment", which is not English output).

**Structural transfer.** The parts that do not map word for word:

| Source | English | Rule |
|---|---|---|
| `a don chop` | I have eaten | `don` → perfect |
| `a di chop` | I am eating | `di` → progressive |
| `a go chop` | I will eat | `go` → future |
| `a bin chop` | I ate | `bin` → past |
| `a no fit chop` | I can not eat | negation + modal |
| `a no chop` | I do not eat | do-support |
| `yu sabi di tori?` | Do you know the story? | interrogative inversion |
| `di moto fain` | The motorcycle is beautiful | zero copula filled in |
| `i dey sell soya` | He is selling soya | `dey` + verb → progressive |
| `pikin dem` | children | post-nominal plural |
| `make wi go` | let us go | hortative, object pronoun |
| `moto la` | that motorcycle | post-nominal `la` → demonstrative |
| `a no fit download notin` | I can not download anything | negative concord resolved |
| `carry me go Mvog-Ada` | carry me to Mvog-Ada | serial `go` → directional |

**Generation.** `fca/morphology.py` inflects the English: third person, past, past
participle, gerund and plural, with an irregular-verb table and the usual spelling
rules. Articles are inserted before bare count nouns and withheld before mass nouns and
vocatives; pronouns take subject or object case according to position.

### 4.6 Known limits

* Word order is only lightly rearranged, so a predicative adjective after a long
  prepositional phrase can land in an odd place.
* Clefts (`na tu kolo a get`) parse but translate stiffly.
* One reading is chosen per ambiguous word; the alternatives are visible with
  `python main.py word <term>` but the translator does not hedge.

## 5. Corpus

`data/corpus.txt` currently holds **placeholder** statements covering the ten required
topics. **Replace them with your group's own transcriptions** — the format is one
utterance per line, `#` for comments, `##` for a topic heading. Everything else (parse
verdicts, translations, frequency tables, the report artefacts) is regenerated from
whatever is in that file.

`data/rejects.txt` holds sentences that must be *rejected*, which is how the grammar is
shown to discriminate rather than accept everything.

```
$ python main.py corpus
accepted 18/18

== negative tests (these must be rejected) ==
REJECTED  moni moni moni taxi taxi
REJECTED  for for for di
REJECTED  a don di di
...
```

## 6. Report artefacts

```bash
python main.py report -o docs/analysis
```

writes, ready to paste into the written report:

| File | Contents |
|---|---|
| `token-table.md` | every token in the corpus with class, language, gloss, origin |
| `regular-expressions.md` | the regular expression for each token class |
| `grammar.md` | raw grammar → left-recursion removal → left factoring → final LL(1) grammar |
| `first-follow-ll1.md` | FIRST/FOLLOW sets and the full LL(1) parsing table |
| `parse-results.md` | accepted/rejected verdict, mixture and translation per sentence |
| `frequency.md` | counts, classes, languages, type/token ratio, spelling variation |
| `francanglais.l` | the generated LEX/Flex program |

## 7. Layout

```
francanglaiscompiler/
├── main.py                     entry point
├── fca/
│   ├── tokens.py               token and category definitions
│   ├── lexicon.py              markdown dictionary loader
│   ├── lexer.py                scanner: maximal munch, language and category tagging
│   ├── regexspec.py            regex specification + Flex generator
│   ├── langid.py               language mixture detection
│   ├── frequency.py            token frequency and variation
│   ├── grammar.py              CFG representation and grammar-file parser
│   ├── transformations.py      left-recursion removal, left factoring
│   ├── analysis.py             FIRST, FOLLOW, LL(1) table
│   ├── parser.py               predictive parser, parse tree, trace
│   ├── morphology.py           English inflection
│   ├── translate.py            transfer-based translator
│   └── cli.py                  command line
├── dictionary/                 pidgin.md, camfranglais.md, french_core.md
├── data/                       corpus, negative tests, overrides, extra lexicon
├── grammar/                    fca.gram (LL(1)), fca_raw.gram (unnormalised)
└── tests/                       62 tests over the corpus
```

## 8. Mapping to the project brief

| Requirement | Where |
|---|---|
| Data collection, 10–15 transcribed statements | `data/corpus.txt` — **replace with your recordings** |
| Identify tokens: nouns, verbs, slang, code-mixed | `python main.py tokens`, `docs/analysis/token-table.md` |
| Regular expressions for token types | `python main.py regex`, `docs/analysis/regular-expressions.md` |
| LEX/FLEX program or custom lexical analyzer | `fca/lexer.py` plus the generated `francanglais.l` |
| Token frequency and variation | `python main.py freq` |
| Context-free grammar | `grammar/fca.gram` |
| Remove left recursion | `python main.py grammar --transform` |
| Left factoring | same command |
| FIRST and FOLLOW sets | `python main.py grammar --first-follow` |
| LL(1) parsing table | `python main.py grammar --table` |
| Test the grammar on collected sentences | `python main.py corpus` |
| Accepted / rejected | same command, plus `data/rejects.txt` |
| Parser reading tokenized input | `fca/parser.py` |
| Screenshots of a working analyzer | `python main.py serve`, or `python main.py repl` |
