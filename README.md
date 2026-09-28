# Camfranglais — Compiler Construction

A deterministic lexical and syntactic analyzer for **CS4110, Summer 2026,
SET A**. The application is public: **no login or account is required**.
Anyone can analyze and save tests; **Collection, saved grammar and recordings
are read-only**.

**Website:** https://camfranglais.duckdns.org

The public bootstrap and no-login interface were observed working on
**27 September 2026**. This is a dated observation, not an uptime guarantee.

## Documents

| Document | PDF | Editable source |
| --- | --- | --- |
| 12-slide essentials presentation | [Slide preview](docs/camfranglais-presentation-12-slides.pdf) | [PowerPoint](docs/camfranglais-presentation-12-slides.pptx) |
| Two-page automata explanation | [Simple guide](docs/automata-guide.pdf) | [LaTeX](docs/automata-guide.tex) |
| Final coursework report | [Report](docs/final-report.pdf) | [LaTeX](docs/final-report.tex) |
| Software Requirements Specification | [SRS](docs/srs.pdf) | [LaTeX](docs/srs.tex) |
| Software Design Description | [SDD](docs/sdd.pdf) | [LaTeX](docs/sdd.tex) |
| Full-size UML and automata atlas | [Atlas](docs/uml-atlas.pdf) | [LaTeX](docs/uml-atlas.tex) |
| UML diagrams and compiler automata | [PNG images and PlantUML](docs/diagrams) | [Exact class inventory](docs/diagrams/class-coverage.json) |

The [documentation register](docs/README.md) explains the evidence, validation,
rebuild procedure and remaining human submission requirements. The report is
separate from the engineering SRS/SDD and must remain **25–30 actual PDF pages,
including its cover and front matter**.

The report's document-only revision **4.3**, dated 28 September 2026, uses
first-person group writing, a corpus-based linguistic discussion and a
complete topic-analysis table. It records the initial compiler input on
**22 September 2026**, credits all three group members jointly and contains
no unfinished fields. The application, raw statements, grammar and numerical
compiler results are unchanged.

The engineering documents remain at edition **4.1**, with a coordinated
navy, teal and gold design without signing areas.
The report explains the regex lexer's equivalent DFA and the bounded
LL(1) parser's pushdown control. Both automata are included alongside the
35 UML views in the SDD and 37-sheet atlas; they do not imply invented runtime
classes or an LR implementation.

The **12-slide presentation** keeps only the essentials for a roughly
ten-minute oral presentation: purpose, five-page workflow, genuine app
screenshots, key source filenames, compiler automata, results and limitations.
It includes the group's names/matricules and short speaker notes on every slide.
Text, cards, flow graphics and the outcome chart remain editable in PowerPoint;
the PDF is a fixed preview. The earlier 100-slide technical reference remains
available through the [documentation register](docs/README.md), separately
from the concise presentation.

## Five-screen workflow

1. **Franc Analyzer:** type or paste a statement and select **Analyze**.
   This publicly retains the original text, grammar and results, even when
   rejected. It does **not** add a Collection entry.
2. **Analysis:** inspect saved tests, vocabulary counts and separate CFG
   results. Expand token details, parser traces, transformations, FIRST/FOLLOW
   and the LL(1) table. Grammar is read-only.
3. **Collection:** search/filter existing raw expressions, meanings and
   annotations; inspect available audio. There are no public create, edit,
   delete or import controls.
4. **Dictionary:** search source-labelled reference vocabulary, including
   supplied categories, origins and distinct senses.
5. **Synthetic examples:** browse explicitly constructed practice material.
   Examples and dictionary entries do not automatically count as fieldwork.

Existing recorded read-aloud plays a saved recording when a compatible one
exists. There is **no browser speech synthesis, generated voice, voice cloning,
microphone capture or automatic transcription** in the public workflow.

There is no AI translator/chat, OCR, browser dictation, automatic explanation,
account/profile/logout screen, public administrator, editable grammar draft,
or in-app report/presentation generation. The LaTeX documents are maintained
outside the application.

### Two different verdicts

- **Vocabulary approval** fails exactly when a saved token is `UNKNOWN`.
  Recognized slang, `AMBIGUOUS` and other known categories pass.
- **CFG acceptance** means the category sequence fits the grammar used for that
  test. Known words can fail the grammar. Empty input has no `UNKNOWN`, but the
  saved corpus grammar rejects it.

Neither verdict certifies meaning, standard French correctness, pronunciation
or authentic collection. Raw spelling is never silently corrected.

### Public and immutable means what it says

Do not submit personal or confidential information. Saved tests are public
and have no public edit/delete operation or automatic purge. Their original
lexer/parser/grammar snapshots survive refresh and later reference changes.
Retrying the same request identifier returns the existing result; a deliberately
new completed test counts separately. Cancelling the browser request does not
guarantee that an in-flight server save was cancelled.

Analysis statistics include completed saved tests, including repetitions and
older snapshots. Untested Collection entries are not included.

## Corpus and honest coursework status

The documented snapshot contains:

- **12 supplied sentences + one Word annotation** in Collection.
- **81 token occurrences**, **55 case-folded forms**, **26 language-transition
  clues**, and two unresolved occurrences.
- A saved **corpus-derived grammar**, not just the illustrative starter:
  actual left-recursion elimination and factoring, 12 transformed
  nonterminals, 39 alternatives, 47 populated LL(1) cells and no conflicts.
- **10 accepted and 2 rejected original statements**. Both rejections occur
  at token six: `n'ais` and `alli` remain `UNKNOWN`.
- **938 dictionary entries**, from 878 supplied CSV rows plus retained distinct
  legacy senses; **26 synthetic examples** in a separate practice library.

The exact originals, computed tables and full traces are available in the
[public corpus snapshot](docs/evidence/final-corpus-20260927.json),
[analysis evidence](docs/evidence/final-analysis-20260927.json), and
[regression cases](compiler/tests/yaounde_cases.py).

The report distinguishes the **22 September compiler-input date** from the
**27 September analysis snapshot**. It describes corpus preparation and
text-based topic readings without assigning undocumented places, speaker
details or conversation dates. The 83.3% grammar-match rate describes this
fixed corpus.

The brief requires a group of three, 10–15 genuinely heard/manual transcriptions
and a 25–30-page report. The examination format is **three minutes per student**.
The group credited jointly for corpus entry and the report is:

| Name | Matricule |
| --- | --- |
| Kwete Ngouba Junior Rayan | ICTU20241377 |
| Djemtchimo Noukui Bruno Jonatan | ICTU20241585 |
| Amina Boubakary | ICTU20241870 |

These identities are printed in the documents; they do not create app accounts.
There are no signature fields or invented individual task assignments.

## Run locally

Use Python **3.11+** and Node.js **22.12+** or a supported newer LTS.
Install declared dependencies in a virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location frontend
try { npm.cmd ci } finally { Pop-Location }
if (-not (Test-Path -LiteralPath backend\.env)) {
    Copy-Item -LiteralPath backend\.env.example -Destination backend\.env
}
.\start.ps1 -Build
```

Open **http://127.0.0.1:8000** using that exact origin. Later starts can use
`.\start.ps1`; stop with **Ctrl+C**. The equivalent launcher is:

```powershell
.\.venv\Scripts\python.exe -m tools.run_app --build
```

The existing VS Code **Start Camfranglais locally** task is also available.
The launcher serves the frontend build and API together, does not silently
install dependencies, and rejects unsafe production reload or unintended
public development binding. `-Port 8001` / `--port 8001` is supported; an
explicit public URL must match the chosen origin.

A new empty data directory does not contain the group's private historical
databases/media. Its starter grammar is illustrative. Do not mistake a fresh
installation's data state for the documented shared corpus, and do not seed or
reset an existing live data directory with test fixtures.

## API boundary

`GET /api/public/session` returns `access_mode: "public_read_only"`, an anonymous
CSRF token and capabilities. The cookie is HttpOnly, SameSite=Lax and Secure in
production. **This is cross-site request protection, not login or identity.**
Public POSTs require the allowed Origin and `X-CSRF-Token`.

| Interface | Public behavior |
| --- | --- |
| `/api/health` | Read health: `status=ok`, `mode=compiler` |
| `/api/public/session` | Anonymous bootstrap and capabilities |
| `/api/analyze`, `/api/analyzer/analyze` | Bounded analysis with Origin/CSRF |
| `/api/analyzer/tests` and test detail | Create/read immutable saved tests |
| Metadata, dataset, dictionary, examples, analyzer state | Read-only data/grammar |
| `/api/readings/lookup` and existing audio bytes | Lookup/playback, not recording creation |
| Reference mutations | Server-side 403 |
| `/api/auth/*`, `/api/workspace/*`, `/api/coursework/*`, imports/admin/restore | Not exposed by the default public app |

New analysis requests with a stale/different grammar return **409** and require
reloading saved grammar. An identical retry of an already-completed test can
still retrieve its original snapshot after an operator changes grammar.

General JSON bodies are bounded to 1 MiB, text to 4,000 characters and grammar
to 12,000 characters. The parser has 256-token, 2,000-step and 1,024-stack-symbol
guards. Public requests are rate-limited to 120 per 60 seconds per client
address, excluding health; operational failures and 429 responses are explicit.
These are bounds, not throughput or availability certifications.

### Retained compatibility is not public functionality

The [application factory](backend/main.py) uses:

- `require_auth=None`: public read-only default.
- `require_auth=True`: explicit retained authenticated compatibility mode.
- `require_auth=False`: unrestricted legacy local maintenance, refused in production.

Existing accounts, historical owners, archives, revisions and media are
preserved. Public responses redact ownership presentation without changing
stored owners. An internal stable public actor supports idempotency without
creating a fake account.

## Storage, backups and deployment

Local storage defaults to `.mboa`. The current shared database is
`.mboa\shared-workspace\workspace.sqlite3`. Anonymous counters use a separate
`public-access.sqlite3`; legacy authentication databases are not reused as
public identity. Keep data, media, archives, private configuration and backups
outside the static frontend directory.

The selected production topology is:

| Setting | Value |
| --- | --- |
| VPS | Ubuntu 24.04, `109.199.120.38` |
| Public URL | `https://camfranglais.duckdns.org` |
| Private upstream | `127.0.0.1:2021` — **do not expose 2021 publicly** |
| Application | `/var/www/francanglaiscompiler` |
| Persistent data | `/var/lib/camfranglais` |
| Environment | `/etc/camfranglais.env` |
| Service | `camfranglais.service`, restricted service user |

Set `MBOA_ENVIRONMENT=production`, an HTTPS `MBOA_PUBLIC_URL`, and an absolute
persistent `MBOA_DATA_DIR`. Public startup does **not** require SMTP or Google
credentials. Nginx handles HTTPS on 443 and the configured port-80 redirect/
certificate flow. Preserve Host and forwarded protocol/client address; trust
only the real proxy addresses. Production disables interactive API docs.

Configured operator backup lifecycle remains, but its administration is not
public. Protect database-consistent off-host copies of the full data root and
configuration; same-disk ZIPs are not disaster recovery. Rehearse restoration
in isolation. Monitor storage growth because saved public tests are not
automatically purged.

For updates, preserve live data and private environment, back up before
replacement, validate Nginx before reloading, and verify health/public policy
afterward. This VPS hosts other sites: do not reset its firewall, remove
unrelated virtual hosts or restart unrelated services.

## Verification

Use the existing tools; synthetic test fixtures are not fieldwork:

```powershell
.\.venv\Scripts\python.exe -m unittest compiler.tests.test_yaounde_grammar backend.tests.test_yaounde_corpus
.\.venv\Scripts\python.exe -m unittest tools.tests.test_documentation_checks tools.tests.test_report_evidence
.\.venv\Scripts\python.exe -m tools.build_report_evidence --check
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
.\.venv\Scripts\python.exe -m tools.check_documentation
```

For application changes, use the existing broader suites as appropriate:

```powershell
.\.venv\Scripts\python.exe -m tools.run_python_tests
.\.venv\Scripts\python.exe -m pip check
Push-Location frontend
try {
    npm.cmd run typecheck
    npm.cmd test
    npm.cmd run build
    npm.cmd run test:e2e -- --workers=2
    npm.cmd run test:e2e:live
} finally { Pop-Location }
```

The full Python suite includes retained desktop tests that need the optional
[desktop requirements](requirements-desktop.txt).

**Known limitation:** the old expected set in
`GrammarNotationTests.test_every_real_lexer_category_is_a_supported_terminal`
does not include nine supported categories and remains a pre-existing failing
regression. The entire CI suite is not claimed green.

The 26 September release evidence recorded 186 backend/launcher/legacy-storage,
148 frontend unit and 68 mocked browser passes, passing type checks/build,
and 14 distinct live workflows across a full run and rerun. Two full-run
startup/teardown interruptions passed in the focused three-case mobile rerun;
this was not an uninterrupted 14/14 run. The seven corpus tests passed again
on 27 September. See the [documentation register](docs/README.md) for final
document checks and dated artifacts.

The [legacy root guide](README.legacy.md), [legacy documentation guide](docs/README.legacy.md)
and older [evidence records](docs/evidence) remain historical. They do not
describe the active public interface or certify current performance.
