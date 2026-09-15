# Franc-anglais Compiler

A lexical and syntactic analyzer, and English translator, for **Camfranglais** — the
urban youth speech of Yaoundé — including utterances that mix it with French and
English the way it is actually spoken.

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

Add `--prefer camfranglais` (or `french`) **before the sub-command** to break
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
| `Mbom, j'ai gauler ma bolo.` | Camfranglais + French | Guy, I have caught my job. |
| `Je ne peux pas telecharger.` | French + English | I can not download. |
| `Le pays est dur oh!` | French + Camfranglais | Times are hard! |
| `Le reseau ndem encore.` | French + Camfranglais | The network fails again. |

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
produce something the analyzer then rejects.

## 4. How the pieces work
### 4.1 The dictionaries are the source of truth

`dictionary/camfranglais.md` and `dictionary/french_core.md` are
ordinary markdown tables. The loader reads the term column, the gloss column and the
section heading, and infers a grammatical category from them:

* a heading containing *verb* makes its rows verbs, *describing* makes them adjectives,
  *number* makes them numerals, and so on;
* a gloss beginning `to …` marks a verb regardless of the section;
* `data/pos_overrides.json` overrides both for the function words that carry the
  grammar — pronouns, tense markers, prepositions, question words.

To extend the vocabulary, add a row to a table. No code changes. `data/extra_lexicon.md`
holds the additions this project needed (transport and utility nouns, university slang,
fillers) so the reference dictionary stays untouched.

### 4.2 Lexical analysis

The scanner does **maximal munch over phrases**, not just words, because `na wa`,
`njama njama` and `c'est comment` are single lexical items. It then resolves two kinds
of ambiguity:

**Language.** A word may be in both dictionaries. Camfranglais draws much of its
vocabulary from French, so `moto`, `petit`, `gros`, `chaud` and `marche` appear in each;
`taxi`, `note` and `pour` are shared with English. Every token keeps the full set of
languages that recognise it (`langs`), which is what lets the mixture detector
distinguish *this utterance is Camfranglais* from *this word merely could be*. Ties go
to Camfranglais, then French, then English, and `--prefer` overrides that.

**Category.** `tchop` is a noun and a verb; `a` is the perfect auxiliary and the
preposition *to*; `la` is a determiner and a post-nominal demonstrative. These are
settled from context — the classic "lexer hack":

```
il achete le tchop   PRON VERB DET NOUN   he buys the food
il va tchop          PRON TMA  VERB       he will eat
il a mange           PRON TMA  VERB       he has eaten
on va a l'amphi      PRON TMA  PREP DET NOUN   we go to the lecture theatre
```

**French elision.** `j'ai`, `l'argent` and `n'a` are scanned as two words, since the
clitic carries its own grammar. The split is skipped when the whole form is itself a
dictionary entry (`c'est comment`, `aujourd'hui`), and both halves are tagged French.

**French inflection.** A word that is not in the dictionary is retried without a final
`s` or `e`, which picks up plurals (`taxis` → `taxi`) and feminine adjectives
(`lente` → `lent`). The plural survives into the English output.

**`ne … pas`.** Only `ne` carries the negation; the trailing `pas` is re-tagged as a
particle so it does not negate the clause twice.

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
* `grammar/fca.gram` — the working grammar: **54 productions, 16 non-terminals, LL(1)
  with zero conflicts**.

`python main.py grammar -g grammar/fca_raw.gram --transform` applies left-recursion
removal and left factoring to the raw grammar and prints every rewrite it makes, which
is the material for the corresponding section of the report.

The core of the working grammar:

```
Utterance -> Openers Clause Rest
Clause    -> QWORD QClause | NP Predicate | VG | eps
Predicate -> VG | ADJ Args | PP Args | ADV Args | eps
VG        -> NEG VG | TMA VGTail | VERB Args | COP Comp
VGTail    -> PRON VGTail | PART VGTail | NEG VGTail | TMA VGTail
           | VERB Args | COP Comp | PP Args | NPBare Args | ADV Args | ADJ Args | eps
Args      -> NP Args | PP Args | ADV Args | ADJ Args | PART Args | VG | eps
NP        -> PRON | NPBare
NPBare    -> DET AdjList NHead | POSS AdjList NHead | NUM AdjList NHead | NHead
```

It is designed around what this variety actually does:

* `VG -> NEG VG | TMA VGTail` mirrors `il ne va pas manger`;
* `VGTail -> PRON VGTail` takes the French **object clitic** before the verb
  (`tu peux me deposer`);
* `VGTail -> PART VGTail` absorbs the trailing `pas` of `ne … pas`;
* `Predicate -> ADJ Args | PP Args` allows the **zero copula** (`la moto fain`,
  `je dans le kwatt`);
* `Args -> VG` allows **serial verbs** (`tu peux me carry go Mvog-Ada`);
* two noun phrases in a row give the ditransitive (`donne moi le mbourou`).

Two restrictions were accepted to keep the grammar conflict-free, and both are worth
discussing in the report:

1. **A bare adjective cannot open a noun phrase.** `le gros piol` is fine, `gros piol
   est la` is not, because a noun-initial `ADJ` would be ambiguous between a modifier
   and a predicate.
2. **A numeral must modify a noun.** `deux kolo` parses, a bare `cinquante` as a whole
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
| `il a tchop` | He has eaten | `a` → perfect |
| `il va tchop` | He will eat | `va` → future |
| `il peut tchop` | He can eat | `peut` → modal |
| `il faut tchop` | He must eat | `faut` → modal |
| `je ne tchop pas` | I do not eat | do-support, `pas` absorbed |
| `tu sabi le toli?` | Do you know the story? | interrogative inversion |
| `combien tu peux payer?` | How much can you pay? | wh-question inversion |
| `la moto fain` | The motorcycle is fine | zero copula filled in |
| `la route est gate` | The road is spoiled | copula + participle → passive |
| `tu peux me deposer` | you can drop me off | object clitic moved after the verb |
| `pas de monnaie` | not … change | partitive `de` dropped under negation |
| `les taxis` | the taxis | French plural carried into English |
| `moto la` | that motorcycle | post-nominal `la` → demonstrative |
| `j'ai pas de livre` | I do not have a book | bare auxiliary becomes a lexical verb |

**Generation.** `fca/morphology.py` inflects the English: third person, past, past
participle, gerund and plural, with an irregular-verb table and the usual spelling
rules. Articles are inserted before bare count nouns and withheld before mass nouns and
vocatives; pronouns take subject or object case according to position.

### 4.6 Known limits

* Word order is only lightly rearranged, so a predicative adjective after a long
  prepositional phrase can land in an odd place.
* French agreement is not checked: a generated `je va` is accepted and translated
  rather than corrected.
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
REJECTED  mbourou mbourou mbourou taxi taxi
REJECTED  avec avec avec le
REJECTED  il a le le
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
├── dictionary/                  camfranglais.md, french_core.md
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
