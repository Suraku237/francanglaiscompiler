# Mboa — Francanglais & Cameroon Pidgin learning studio

A Python + React language workspace for understanding Francanglais (Camfranglais)
and **Cameroon Pidgin**, comparing expressions with French and English, and growing
a reviewed local dataset. Translation works in both directions between the four
languages, using approved dataset evidence first and clearly labeled Gemini
suggestions for gaps. Documents, images, audio and video can supply text for
review, translation, conversation or new dataset entries.

Francanglais and Cameroon Pidgin are distinct, variable ways of speaking, not
interchangeable labels or Nigerian Pidgin defaults. This is **not a dictionary of
every possible word**: the compiler exposes unknown vocabulary and grammar limits,
while people review and extend the evidence. The CS4110 compiler lab remains a
separate educational workspace within the app.

## Web application

### What is included

- **Python / FastAPI backend** in `backend/`: dataset-first translation,
  evidence-grounded Gemini chat, local lexical analysis, reviewed file imports,
  and CSV collection CRUD.
- **React / TypeScript / Vite frontend** in `frontend/`: translation with
  everyday, polite or street registers, vocabulary explanations, assistant
  conversations with evidence, language comparison, import previews, and
  collection search/editing/statistics.
- **Voice assistance**: dictate French or English in supported browsers, review
  the transcript, then explicitly submit it. Read translations and assistant
  replies aloud with the browser's voices, or stop playback.
- **Shared data**: the web app, optional desktop collector and lexer all use
  `data_collector/dataset.csv`. No migration or overwrite of existing entries is
  required. Older CSV headers are read with safe defaults: missing language is
  `unspecified`, review status is `unreviewed`, and lexical category is empty.
  The next explicit save upgrades the header without inventing approval or
  language labels. CSV writes use a cross-process lock and atomic replacement.

### The learning loop

1. Collect an expression exactly as observed, or open **Import & learn** to
   preview a file. Imported data and AI candidates are **unreviewed**.
2. Review its language, French/English meanings and context in the collection
   editor. Optionally label the lexical category of a **Word**.
3. Explicitly approve the record after checking it. Approval is a local human
   decision, not a guarantee of universal spelling or meaning.
4. Translate with **Use dataset** enabled. An unambiguous approved whole-entry
   alignment can be returned locally, without a Gemini call. Matching separate
   words is not treated as a reliable full-sentence translation.
5. When coverage is incomplete or ambiguous, enabled AI fallback receives only
   bounded relevant approved expressions and glosses, and returns a labeled
   suggestion. Evidence cards identify the supplied records; they do **not**
   certify every generated word. Disable fallback for a strict local lookup.
6. Ask the assistant to translate or explain using the dataset. Select the
   translation direction; its reply includes the evidence supplied to Gemini.
   New model output is never automatically added to the dataset.

Approved word-category entries can extend local lexical classification. This
does not train or fine-tune Gemini, guarantee full language coverage, or make an
arbitrary sentence satisfy the editable coursework grammar. Unreviewed and
unclassified records remain available for human review, not trusted translation.

### Supported file inputs

Open **Import & learn**, choose a file, and press **Preview source text**:

| Input | Processing |
| --- | --- |
| UTF-8 TXT, Markdown, CSV, JSON | Local text extraction; CSV with a `text` column and JSON record arrays / `{"entries": [...]}` also preview aligned entries |
| PDF | Local text-layer extraction; scanned pages require consented Gemini OCR |
| DOCX | Local body text and tables; images, headers, footnotes and text boxes may need manual transcription |
| PNG, JPEG, WebP | Gemini OCR, only with explicit cloud-processing consent |
| MP3, WAV, M4A, OGG, FLAC | Gemini transcription, only with explicit consent |
| MP4, WebM, MOV | Gemini dialogue transcription / visible text, only with explicit consent |

Limits: **12 MB per file**, **40 PDF pages**, **12 megapixels per image**,
**40,000 extracted characters**, and **100 aligned records per structured import**.
Use short media clips; an AI response cut off by its output limit is an error,
not a successful partial transcript. Unsupported extensions, invalid signatures,
encrypted PDFs, oversized files, malformed records and unreadable text produce
explicit errors. A container extension alone cannot guarantee codec compatibility.
Renaming an unsupported file does not convert it.

Long text is split into complete passages of at most 4,000 characters without
silently dropping the rest. Review every passage separately. The translator and
assistant receive only the passage you explicitly open and submit. Local PDF
layout order and AI transcription can be wrong: verify accents, slang, negation
and speaker wording against the source. Textless PDF pages are disclosed.

You can review a passage as an entry or ask Gemini for vocabulary candidates.
Candidates must quote text actually present in the passage; their glosses and
language/category labels still need human review. CSV/JSON approval flags cannot
bypass that review. Previews live only in the browser tab until reload; this app
does not retain uploaded raw files, and does not use Gemini's persistent Files
API. Provider data policies still apply to inline media requests. Import only
content you have permission to process.

### Start locally (PowerShell)

Requirements: Python 3.11+ and Node.js 22.12+ (or a supported newer LTS).
Run the following from the repository root:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
```

Edit `backend/.env` locally and set `GEMINI_API_KEY` to your key from
[Google AI Studio](https://aistudio.google.com/apikey). **Do not paste the key
into the React app, a chat, or version control.** Never use a `VITE_` variable
for this secret. The server reads this file regardless of its working directory.

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
```

The model is configurable: choose an available text-generation model supporting
Gemini `generateContent` structured JSON output. Access, pricing and quotas
depend on your Google account. Restart the backend after changing configuration.

**Terminal 1, from the repository root:**

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2:**

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite forwards `/api` to
`http://127.0.0.1:8000`. Interactive backend API docs are at
**http://127.0.0.1:8000/docs**. Both processes must be running.

Without a Gemini key, collection, local document preview, lexical analysis and
unambiguous approved dataset translations still work. Unsupported local lookups
and requests requiring Gemini give a clear error; there are no fabricated
offline translations.
The health indicator checks whether a key is configured, not whether Google has
validated it.

Configuration precedence is: explicitly supplied settings (tests), process
environment variables, `backend/.env`, root `.env`, then defaults. A blank key
in a higher-priority source intentionally disables AI. `.env.example` is a
blank template and is **not loaded**. Put the actual key in `.env`, not in the
example; the example may be committed. If a key was ever published, rotate it
in Google AI Studio.

The default model is `gemini-3.6-flash`; model access may change with your
account or provider availability. A transient provider HTTP 503 is retried
once against the same model, within the original total request timeout.
Authentication, quota and other errors are surfaced without automatic model
substitution or fabricated answers.

### Voice, privacy and translation quality

- Microphone access requires **localhost or HTTPS**, permission, and a browser
  implementing speech recognition (try a current Chrome or Edge). Feature
  availability depends on the browser/OS; typing always remains available.
- Recognition may send audio to the browser vendor's speech service. It is not
  guaranteed offline. Browser dictation does not upload recordings to this app;
  explicit file imports are a separate consented workflow. Existing collected
  audio filenames are preserved.
- Submitting translation/chat sends that text and, for chat, recent conversation
  context to **Google Gemini** when AI is needed. With dataset grounding enabled,
  selected approved expression/gloss matches are also sent. The full CSV,
  contributor names, source locations, notes and collected recordings are not
  attached to these requests. Turn dataset use off to omit retrieved examples.
  Do not submit sensitive data.
- Chat uses a bounded recent history; clearing the chat resets the browser
  conversation. AI output is not automatically saved as collected research data.
- Browser voices are not native Francanglais or Cameroon Pidgin voices; French
  and English recognition/read-aloud are approximations for these languages.
  Pronunciation and regional slang vary.
- AI translations are suggestions, not a verified Francanglais/Pidgin dictionary.
  Review them with local speakers. The existing lexer is also heuristic, and
  labels unknown words rather than pretending they are known.

### Configuration and deployment

`backend/.env.example` documents the key, model, timeout (default 45 seconds),
and allowed frontend origins (`CORS_ORIGINS`, a JSON array).
The frontend uses relative `/api` requests and never needs a Gemini key.

```powershell
cd frontend
npm run build
npm run preview
```

The build is in `frontend/dist/`. Preview requires the Python backend too.
For deployment, serve that directory using your web host and reverse-proxy
`/api` to FastAPI, or configure explicit frontend origins for a separate host.
Use HTTPS for voice access. **This is a local/trusted-user app, not an
authenticated public service.** Before exposing it publicly, add authentication,
authorization for dataset changes, request/rate limits and deployment-level
secret management. CORS alone is not access control.

Back up the CSV and audio directory. Do not edit the CSV manually while an app
is writing to it. All API writes preserve existing IDs, timestamps and audio
metadata when editing; malformed CSV files produce an error rather than being
silently replaced.

### Verified backup and recovery

Close the desktop collector and stop the API before taking a snapshot, including
any recording or screenshot upload. Store backups in an access-restricted
location; they contain collected text, contributor details and recordings.
Checksums detect changes, not the authenticity of fieldwork or the trustworthiness
of an unknown backup.

From the repository root, choose **new** destination names:

```powershell
New-Item -ItemType Directory -Force .backups | Out-Null
.\.venv\Scripts\python.exe -m tools.data_snapshot backup --destination .backups\before-review
.\.venv\Scripts\python.exe -m tools.data_snapshot verify .backups\before-review
.\.venv\Scripts\python.exe -m tools.data_snapshot restore .backups\before-review --destination .backups\restore-check
.\.venv\Scripts\python.exe -m tools.data_snapshot verify .backups\restore-check
```

The [snapshot tool](tools/data_snapshot.py) preserves CSV bytes (including
supported legacy headers), managed audio including unreferenced recordings,
the saved coursework profile, and screenshots. Configuration files such as the
root `.env`, locks and incomplete atomic-write files are not part of that
payload. A SHA-256 manifest verifies the complete file inventory and referenced
audio. Missing media, corrupt files, unsafe paths, links and detected concurrent
changes are explicit failures. A failed snapshot is not published.

Restore refuses an existing destination: it **never overwrites the live
collection**. To recover real data, first preserve the current data, verify a
snapshot, restore to a new directory, and inspect the restored rows/media.
Only then, with all apps still stopped, deliberately copy the verified data
and corresponding media/profile files into the managed data directory. Copy
the CSV last; do not copy the snapshot manifest or delete unrelated files.
Reopen the application and check the expected counts and referenced recordings.
Keep the pre-recovery copy until those checks pass. Access permissions and
encryption for the backup location remain the operator's responsibility.
If the current CSV is already malformed, preserve a separate manual copy
before troubleshooting: the tool deliberately refuses to label a malformed
CSV as a verified snapshot.

`.backups/` is ignored by Git, but an external protected backup location is
preferable for disaster recovery. `--source <folder>` supports rehearsal with
an isolated data directory. Automated round-trip and corruption tests use
synthetic temporary fixtures, never the group's actual corpus.

### API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | API status, configured-model name, key-present flag |
| POST | `/api/translate` | `text`, source/target languages (`fr`/`en`/`francanglais`/`pidgin`), `explanation_language`, `tone`, `use_dataset`, `allow_ai`; translation, origin, evidence, coverage and lexer output |
| POST | `/api/chat` | `message`, explanation `language`, bounded `history`, source/target languages, `use_dataset`; assistant reply and supplied evidence |
| POST | `/api/analyze` | Analyze `text` locally with reviewed word categories and the base lexer |
| POST | `/api/imports/preview` | Multipart `file` and `allow_cloud_processing=true/false`; transcript, passages, warnings and unreviewed structured drafts |
| POST | `/api/imports/suggest` | Reviewed `text` and language context; unreviewed AI vocabulary candidates, never a save |
| GET | `/api/metadata` | Collection topics, entry types, dataset languages and lexical categories |
| GET | `/api/dataset?query=...` | Search entries; whole-collection counts |
| POST | `/api/dataset` | Create a reviewed or unreviewed entry; language, aligned glosses, review status and optional word category |
| PATCH | `/api/dataset/{id}` | Edit supplied fields, preserving other metadata |
| DELETE | `/api/dataset/{id}` | Delete a collection entry |

Text inputs are limited to 4,000 characters. Chat accepts at most six complete
user/assistant exchanges (12 messages, 24,000 history characters).
Duplicate collection text within the same language returns HTTP 409.
Validation failures return 422, oversized imports 413, unsupported formats 415,
missing configuration 503, provider/network errors 502, quota limits 429 and
provider timeouts 504. Provider response bodies and keys are not exposed.

### Verification

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
.\.venv\Scripts\python.exe -m tools.run_python_tests
if ($LASTEXITCODE -ne 0) { throw "Python tests failed." }
Push-Location frontend
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "Frontend installation failed." }
    npm test
    if ($LASTEXITCODE -ne 0) { throw "Frontend component tests failed." }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    npx playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "Browser installation failed." }
    npm run test:e2e
    if ($LASTEXITCODE -ne 0) { throw "Frontend browser tests failed." }
}
finally {
    Pop-Location
}
```

Python tests use temporary CSV files and a mocked Gemini HTTP transport:
they make **no real Gemini requests**, require no API key and do not modify
your collected dataset. They cover language directions, approved local matching,
evidence privacy, chat, malformed/blocked AI responses, timeouts, quotas, imports
and review gates, input validation, CRUD, concurrent/atomic CSV writes, and
collector/lexer behavior. Desktop audio/device failures are mocked; snapshot
tests verify exact-byte recovery, missing/corrupt media and refusal to overwrite
existing data. Frontend component and browser tests use controlled API fixtures,
not a running research backend or live AI service.

[CI](.github/workflows/ci.yml) runs Python regressions on Windows with Python
3.11 and 3.14, frontend/component/browser checks on Node.js 22, and a fresh
PlantUML/LaTeX build with checksum-verified tools. Its documentation check compares
the production-class inventory with the actual Python source, checks every
diagram reference, and verifies that the current diagram pixels are embedded
in the published SDD. A workflow definition is not evidence that a remote
GitHub run has already completed; inspect the repository's Actions results.

For an isolated performance measurement, use a graphical desktop session and
do not interact with the temporary benchmark window:

```powershell
.\.venv\Scripts\python.exe -m tools.benchmark_collector --output docs\.build\collector-benchmark.json
```

This exercises the actual active-tab search and Stats handlers, including Tk
idle rendering, over 1,000 synthetic 500-character entries. Each operation has
one warm-up and 20 measured runs; the reported p95 is the nearest-rank value
and the default limit is 1,000 ms. The report records hardware, runtime, raw
timings and source hashes, and exits unsuccessfully if the limit is exceeded.
The real CSV is never used or replaced. Passing on one recorded machine is
not a claim of identical performance on all machines.

Rebuild and verify the documentation separately:

```powershell
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
.\.venv\Scripts\python.exe -m tools.check_documentation
```

Actual translation quality, account/model access and physical microphone
behavior require a live check on your machine. Before release, exercise mic
permission denial, missing/disconnected devices, Record/Stop, attachment and
playback, browser dictation availability, network/provider errors and a reviewed
translation example. Use non-sensitive examples and explicit cloud consent;
passing mocked tests is not proof of provider access or linguistic accuracy.

---

## CS4110 SET A coursework workspace

The **Compiler lab** workspace maps the application to the three-page
*Compiler Construction SET A Summer 2026* brief supplied for this project.
Translation, chat and voice are extensions; they do **not** replace the compiler
assignment or its fieldwork.

| Brief requirement | Application support | Your group's remaining responsibility |
| --- | --- | --- |
| Three members; 10-15 real manually transcribed statements | Group profile, collection provenance, sentence count, ten-topic coverage and explicit authenticity confirmation | Actually listen and transcribe; preserve the exact wording and document contributions |
| Nouns, verbs, slang and code-mixing | Per-entry token tables, verb/slang phrases and inferred language transitions | Review classifications and extend the small lexicons using field evidence |
| Custom lexical specification | Python regex lexer, visible rules, and source export | Explain the classification choices and their limitations |
| Frequency and variation | Corpus frequencies, category totals, unknown terms and observed spelling/case/accent groups | Interpret the results; spelling groups are not semantic equivalences |
| CFG tied to collected language | Editable grammar plus a saved design rationale | Adapt the teaching starter to your own observations |
| Remove left recursion and left-factor | Calculated transformations with before/after rules | Explain which transformations apply and why |
| FIRST/FOLLOW and parsing table | Fixed-point sets, LL(1) table and explicit conflict detection | Resolve conflicts or document limitations; LL(1) is the selected alternative to LR/SLR |
| Working parser over tokenized inputs | Table-driven stack trace, full-input acceptance/rejection, corpus-wide tests | Review expected outcomes and explain rejected examples |
| Report, screenshots and discussion | Printable 25-section HTML report draft, genuine screenshot attachments, original write-up fields, CSV/JSON appendices | Complete and proofread the report; verify final print/PDF is 25-30 pages and no more than 30 |
| Source and own-data test cases | Actual source bundle and generated regression cases from the saved corpus | Independently check expectations; snapshots are not linguistic ground truth |
| PowerPoint and demonstration | Editable `.pptx` with ten minutes of timing notes | Personalize/rehearse: three minutes per member, then a shared one-minute wrap-up |

### Suggested workflow

1. In **Collection**, enter your group's exact manual transcriptions. Mark
   full statements as `Sentence`, choose topics, and record contributors and
   source locations. Words and phrases are useful but do not inflate the
   required 10-15 sentence count.
2. In **Compiler lab**, enter three distinct names, your collection method,
   grammar rationale, original discussion and limitations. Confirm manual
   transcription only if true. Save the profile.
3. Edit the CFG and run the analyzer. Each line uses
   `Nonterminal -> symbol symbol | epsilon`; the first left-hand side is
   the start symbol. Terminals are lexer category names, not quoted words.
   Use `epsilon` explicitly for an empty production.
4. Inspect transformation steps, FIRST/FOLLOW, table conflicts, lexical
   reports and each collected entry's parser result. Test individual
   expressions without adding them to the dataset. Unknown symbols are
   retained; the parser never silently discards them.
5. **Ask AI** only when desired. This sends the grammar, practice text,
   question and selected calculated results to Gemini. It does not
   automatically include the collection, group profile or screenshots.
   AI suggestions do not change the saved grammar or override the parser.
6. Upload actual PNG/JPEG screenshots of the running analyzer (up to six,
   2 MB and 12 megapixels each). These remain local.
7. Save before exporting. The ZIP uses the **saved** grammar/profile and
   current collected CSV. It includes `report.html`, `presentation.pptx`,
   lexical/parser CSV and JSON files, screenshots, source, and own-data
   regression tests. No `.env` files or API keys are included. The archive
   **does include your collected text and contributor names**; share it
   only with authorized course recipients.

The report is an editable/printable **draft**, not a claim that the assignment is
finished. Its 25 sections are not a guarantee of 25 printed pages: long tables,
grammar steps and screenshots can add pages. Check print preview and revise
layout/content to satisfy the 25-30 page requirement. Missing fieldwork and
discussion are explicitly marked rather than fabricated. Full tables remain
in appendix files if a report section shows only a bounded preview.

Project metadata and screenshots persist in `data_collector/coursework/`
(ignored by Git). The coursework analyzer is designed for a small course
corpus, with limits of 500 entries and 100,000 text characters. Grammar and
parser limits produce explicit errors instead of hanging.

### Fieldwork information the group must provide

The software can prepare and verify the workflow, but must not invent these
inputs. A CSV, spreadsheet or clearly structured text table is sufficient:

| Input | What to provide |
| --- | --- |
| Group identity | Three names, matricules, and each member's actual contribution |
| Genuine speech | 10-15 exact manually transcribed full statements, not dictionary/AI/demo substitutes; keep the original spelling and code mixing |
| Topic and language | One required topic per statement and the observed language; use `mixed` or `unspecified` when genuinely uncertain |
| Provenance | Who in the group collected it, general location/context and when it was heard, where known; omit unnecessary speaker-identifying details |
| Meanings | French/English glosses only where known, with uncertainty or ambiguity noted |
| Method and permission | How transcription and review were performed, appropriate permission/consent, and any restrictions on sharing text or audio |
| Interpretation | Observed patterns, grammar rationale, discussion, limitations and independently reviewed expected parser outcomes |

Audio is optional. The application generates record IDs and timestamps;
do not invent collection dates, identities, permissions or findings to fill
blanks. Mark approval and manual transcription only after genuine human review.
The SRS/SDD author fields and research-dependent deliverables remain pending
until the group supplies this information. They are separate from the required
25-30-page coursework report.

Additional endpoints: `GET /api/coursework`,
`PUT /api/coursework/project`, `POST /api/coursework/analyze`,
`POST /api/coursework/parse`, `POST /api/coursework/explain`,
`POST /api/coursework/screenshots`,
`GET /api/coursework/screenshots/{image_id}`,
`DELETE /api/coursework/screenshots/{image_id}`, and `GET /api/coursework/export`.
The API docs describe the request shapes.

Run the coursework, compiler and existing API tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
.\.venv\Scripts\python.exe -m unittest discover -s compiler\tests -v
```

## Original CS4110 project

**Lexical and Syntactic Analysis of Informal Urban Communication in Yaoundé**
CS4110 Compiler Construction, Summer 2026, ICT University — due Tue Sept 29, 2026.

Yaoundé speech mixes French, English, Pidgin, and local-language slang
("Francanglais" / Camfranglais). This project builds a mini-language
analyzer for it: collect real, manually transcribed statements, then
run lexical analysis (tokenizing + classifying) and syntactic analysis
(a hand-built grammar + a working parser) over them.

## Phase 1 — Dataset Collection ✅

`data_collector/` is a CustomTkinter desktop app for building the
dataset, split into three files:
- `app.py` — the GUI (three tabs: Collect, Browse & Edit, Stats)
- `dataset.py` — all dataset CRUD (load/append/update/delete/count)
- `audio_utils.py` — recording, saving, and playback helpers

**Optional desktop setup** (separate GUI/audio dependencies):
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe data_collector\App.py
```

**Collect tab** — add new entries into `data_collector/dataset.csv`:
- `text` — the exact words transcribed, slang/accent/mistakes included
- `entry_type` — word, phrase, or sentence
- `french_gloss`, `english_gloss` — standard-language meaning
- `category` — one of the assignment's 10 required topics: taxi/commuting,
  internet connectivity, electricity supply, market bargaining, rainy
  season, fuel scarcity, roadside business, bendskin communication,
  security checkpoint, campus life (+ "other")
- `source_location` — where it was heard, e.g. "taxi, Mvan" / "Marché
  Mokolo" / "ICT campus"
- `notes` — register, accent, incomplete-sentence notes
- `audio_filename` — optional; recorded live (mic) or attached from
  an existing file. **Not required by the assignment** (which calls
  for manual transcription), but kept as extra raw material for the
  word-prediction extension below
- `contributor` (group name/members), `timestamp`
- `language`, `review_status`, `lexical_category` — review metadata shared with
  the web collection. New material is unreviewed; unspecified language is not
  silently interpreted as Francanglais. Review changes before approving them.

A duplicate warning appears if the text you're typing already exists
in the dataset. A "Recently added" list shows your last few entries.
Shortcuts: `Ctrl+Enter` saves, `Esc` clears the form.

**Browse & Edit tab** — search, edit, delete, and play back audio for
any existing entry via a sortable table.

**Stats tab** — live counts by entry type and by category, so you can
see coverage gaps (e.g. "no rainy-season entries yet") while collecting.

Live recording needs `sounddevice`/`soundfile` and a working mic
backend (PortAudio). If that's not available, "Attach file..." works
with zero extra setup. Playback falls back to your OS's default
player if `sounddevice` isn't available.

Target: **10–15 real-life statements per group of 3**, spread across
the 10 topics above.

## Phase 2 — Lexical Analysis ✅

`compiler/lexer/` implements the custom lexical specification:
- `lexicon.py` — word lists (nouns, verbs, slang, Pidgin markers,
  French/English function words) and the multi-word verb-phrase
  patterns. **Grow these from your real collected data.**
- `tokenizer.py` — the segmentation regex + per-token classifier +
  code-mixed span detection + verb-phrase matching
- `frequency.py` — token frequency and category-composition counts
- `regex_specification.md` — the written spec for the report (exactly
  what the assignment asks for under "Create a custom lexical
  specification using regular expressions for token types")

**Run it**
```bash
python compiler/run_lexer.py
```
It reads `data_collector/dataset.csv`. If that's still empty, it runs
against 10 built-in placeholder sentences instead (clearly logged as
such) so the pipeline is testable before real data collection is done
— **replace these with your group's real data before writing up
results**. Output goes to `compiler/output/`:
- `token_table.csv` — every token from every sentence, tagged
- `frequency_report.csv` — token frequency, most common first

A console summary also prints category counts, code-mixed span count,
and the top 15 most frequent tokens.

## Phase 3 — Syntactic Analysis

Implemented under `compiler/parser/` and exposed in the Compiler lab:
editable CFGs, left-recursion removal, factoring, FIRST/FOLLOW, LL(1)
table construction with conflict detection, predictive parsing, and
accept/reject traces on your collected data. The default is a teaching
starter, not a grammar inferred from observations you have not collected.

## Phase 4 — Deliverables

- **Report (25–30 pages)**: raw statements, token tables, regex
  rules, grammar rules, the parsing table/automaton, screenshots of
  the working analyzer, and a discussion of why Yaoundé communication
  is linguistically complex.
- **Source code**: lexer, parser, and test cases drawn from the
  group's own data.
- **Slide deck**: presentation/demo material.

Use the coursework export to assemble these artifacts, then supply/review
your group's own evidence, discussion, final pagination and demonstration.

## Stretch — Word/Sentence Prediction (extension, not graded)

Once there's a real dataset (and optionally audio), a rule-based +
statistical model can be trained on the known French↔English blending
patterns to guess whether a novel word plausibly *is* Francanglais,
and to generate new sentences in the same style. This sits outside
the CS4110 rubric — built after the required phases are solid.