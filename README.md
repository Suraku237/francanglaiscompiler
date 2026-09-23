# Mboa — Compiler Construction Lab

**A non-AI, authenticated workspace for CS4110 Compiler Construction, SET A,
Summer 2026.** Collect genuine manually transcribed statements from Yaoundé,
inspect a custom regex lexer, build and transform a CFG, compute FIRST/FOLLOW
sets and an LL(1) table, and run the implemented parser against your own corpus.

The assignment is due **29 September 2026**. A group of **three** must collect
**10–15 real statements**, submit a **25–30-page report, never over 30 pages**,
and give a **10-minute presentation/demo**, allowing **three minutes per member**
and one shared minute. The SRS, SDD and UML atlas below describe the software;
they are **not the final coursework report**.

> **Evidence is still missing.** At the 22 September scope review, the legacy
> CSV and three inspected hosted workspaces contained **zero entries**. The
> supplied 179 dictionary rows are references and the 26 practice statements
> are constructed examples, not fieldwork. The default CFG is illustrative,
> not derived from a collected corpus. The user will provide a text file of
> genuine manual transcriptions. No field observations, screenshots, findings
> or completed report are invented.

## What the product does

- **Compiler lab:** five assignment sections, shown one at a time: Data
  collection, Lexical analysis, Syntactic analysis, Parser tests, and Report &
  presentation. It opens directly on the sentence lexer, not a research dashboard.
- **Collection:** preserve exact manually transcribed wording, glosses and notes;
  save provenance, explicitly review entries and attach private recordings.
- **Dictionary and Synthetic examples:** read-only source-labelled references
  and clearly constructed material for learning/testing, never automatic fieldwork.
- **Private access:** accounts and selection of existing projects. Statements
  are entered and reviewed directly in Collection.

The main navigation has only **Compiler lab, Collection, Dictionary and Synthetic
examples**. History, Workspace settings and Document import are no longer app
screens; their old links return to Compiler lab. This interface cleanup does not
delete accounts, projects, stored history, recordings, revisions or backups.
Authenticated maintenance APIs remain available for compatibility and recovery.

There is **no AI generation, translator, chat assistant, automatic explanation,
remote transcription, OCR or browser dictation**. No model key is needed.
Optional read-aloud selects only voices the browser reports as `localService`;
without a suitable French/English voice it shows an error, with no remote-voice
fallback. Voice availability and that locality claim depend on browser/OS
implementation, not an application guarantee about all underlying network use.
Google sign-in and SMTP remain optional/required identity
services as configured, not language providers.

### Find the assignment outputs in Compiler lab

1. **Data collection:** open Collection, select **Add entry**, and explicitly
   save each of the required 10–15 manually transcribed statements.
2. **Lexical analysis:** enter a sentence and select **Analyze tokens**. Expand
   **Regular expressions & classification rules** for the custom specification.
   **Analyze saved statements** computes corpus token tables, frequencies and
   variation using the current grammar as part of the shared analysis.
3. **Syntactic analysis:** edit the CFG and select **Analyze grammar & saved
   corpus** to see recursion removal, factoring, FIRST/FOLLOW and the LL(1) table.
   Grammar computation works even when the saved corpus is empty.
4. **Parser tests:** parse one input or **Run saved-statement tests** to inspect
   acceptance/rejection and stack traces. These results test grammar coverage,
   not linguistic correctness.
5. **Report & presentation:** enter group names/matricules and the linguistic
   discussion, attach actual analyzer screenshots, then download the draft ZIP.
   Review the report's 25–30-page limit, source/tests and ten-minute presentation.

Switching sections preserves input and project drafts. **Save project** persists
grammar and report fields; running analysis does not save them. Keyboard users
can move between tabs with Left/Right, Home and End.

## Run locally

Requirements: Python 3.11+ and Node.js 22.12+ or a supported newer LTS.
From the repository root, install the declared dependencies:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location frontend
try { npm ci } finally { Pop-Location }
if (-not (Test-Path -LiteralPath backend\.env)) {
    Copy-Item -LiteralPath backend\.env.example -Destination backend\.env
}
.\start.ps1 -Build
```

Open **http://127.0.0.1:8000** and use that exact origin consistently.
FastAPI serves the production frontend and `/api` together. Later starts without
source changes can use `.\start.ps1`; stop with **Ctrl+C**. The equivalent launcher
is `.\.venv\Scripts\python.exe -m tools.run_app --build`.
It does not silently install dependencies, expose a development server on the
public network or enable production reload. `-Port 8001` / `--port 8001` is
supported; an explicit `MBOA_PUBLIC_URL` must match.

1. Create an account using your own email and a unique password of at least
   12 characters.
2. In default development mode, open your own verification message in the
   private `.mboa\mail` outbox. It is **not sent to the internet**. Follow the
   link, verify and sign in. Links are secrets; never publish the outbox.
3. The account starts with an empty **General** project. Existing private
   accounts and data are preserved; the legacy CSV, group identities and
   screenshots are not automatically imported.
4. Open the compiler workflow, inspect the explicitly illustrative grammar,
   then add only statements you genuinely collected. Saving remains explicit.

For frontend hot reload, keep the API on port 8000 and run `npm run dev` in
`frontend`. Configure `MBOA_PUBLIC_URL` to the browser origin for account links
and Google callbacks; add only needed origins to `CORS_ORIGINS`. Vite is optional
for development, not a production requirement.

## Complete the assignment honestly

### 1. Collect and manually transcribe

The brief suggests commuting, connectivity, electricity, markets, rain, fuel,
roadside businesses, bendskins, security and university life. These are suggested
contexts, not a requirement to fabricate one statement for every topic.
Listen and write the **exact words**, including slang, accents, mixing,
incomplete sentences and mistakes. Keep the raw text separate from glosses.
Record contributor, location/context, collection method and limitations without
exposing unnecessary speaker-identifying information; obtain appropriate consent.

Keep the original transcript separately. In Collection, use **Add entry**, copy
the exact statement into Expression, select **Sentence**, and add meanings and
available provenance without inventing missing facts. Save it as unreviewed
until its annotations have been checked. Word/Phrase
annotations can support classification but do not inflate the 10–15-statement
target. A manual-transcription checkbox is self-attestation, not software proof.

On create/edit, the backend keeps raw statement text, both glosses and notes
exact, but its existing `ShortText` validation trims leading/trailing whitespace
from supplied `contributor` and `source_location` values. This save-time metadata
normalization does not rewrite the transcription or migrate existing records.

The document author group is:

| Member | Student ID |
| --- | --- |
| Kwete Ngouba Junior Rayan | ICTU20241377 |
| Djemtchimo Noukui Bruno Jonatan | ICTU20241585 |
| Amina Boubakary | ICTU20241870 |

Enter the three members in the intended project profile; new accounts do not
inherit these names.

### 2. Inspect lexical analysis

Review regex rules, nouns, verbs, slang, multiword phrases and code-mixed spans.
The lexer is deterministic. Approved, explicitly language-labelled **Word**
annotations can extend its lookup; sentence text is not model training.
Conflicting labels do not silently choose a category. Preserve and discuss
`UNKNOWN` tokens and morphological `_LIKE` guesses rather than presenting them
as validated linguistic truth.

Frequency and variation tables use saved project entries. Accent/case/spelling
groups are possible orthographic variants, not proven semantic equivalents.
The [core dictionary](dictionary/camfranglais.md) and
[supplement](dictionary/extra_lexicon.md) have English meanings, duplicate forms
and competing senses. Origin is neither a French gloss nor a part-of-speech label.
The [practice library](examples) is constructed material, not collected evidence.

The current lexer preserves decomposed accents and raw, source-ordered phrase
annotations; multiword matches do not replace the parser's underlying tokens.
A [source-verified synthetic benchmark](compiler/output/benchmark_verified.json)
measured about **5× faster repeated public-starter preparation** from its narrow
cache, not faster custom grammars, every algorithm or end-to-end application
latency. See the [measurement method and limitations](docs/README.md#compiler-measurement-boundary).

### 3. Construct and test your grammar

Replace or justify the illustrative CFG using structures actually observed in
your statements. Review the before/after transformation steps for left-recursion
removal and left factoring, FIRST/FOLLOW sets, table entries and conflicts.
The implemented option is **LL(1)**; LR/SLR is an alternative in the brief, not an
additional implemented parser.

Run single-input traces and the saved corpus. The parser consumes token
**categories**, reports acceptance/rejection and does not arbitrarily resolve a
conflicting table. Acceptance means fit to the submitted grammar, not authentic
fieldwork, correct natural language or a complete multilingual language model.
Explain rejections and grammar limitations in your own words.

### 4. Capture, export and review

Attach only **actual screenshots of your working analyzer**. Export the
coursework ZIP for a **DRAFT HTML report**, editable PowerPoint, raw data,
token/frequency/grammar/table/parse artifacts and source snapshots.
The shared account lock keeps profile, corpus and screenshot reads coherent
against concurrent workspace mutations throughout analysis/export.
The 25-section draft is not a guarantee of 25 printed pages. Add original discussion,
check screenshots and print pagination, then ensure the final report is
25–30 pages and never exceeds 30.

Rehearse the ten-minute group demonstration: three minutes per member and a
one-minute shared introduction/conclusion. A populated checklist/export is not
submission approval. The final report remains incomplete until genuine data,
corpus-derived grammar reasoning, human discussion, evidence and pagination have
been reviewed.

## Files, recordings and limits

Text extraction runs locally **on the application server**, not necessarily on
the user's device. Importing uploads the selected file only when Preview is
requested. It neither saves entries automatically nor contacts a language
provider. Scanned/image-only PDFs, images and media are not transcribed; provide
a manual text transcript instead. A partly text-layer PDF can omit scanned
content, so inspect warnings and the complete source.

Browser recording captures locally in the current tab until an explicit save.
Stop, preview and optionally download it before attachment. A failed save
preserves the draft. Audio attachments do not turn into transcripts; microphone
permission and HTTPS or loopback are required. Chrome/Edge is preferable for
manual audio checks; embedded browser codec support can differ.

| Boundary | Limit |
| --- | --- |
| Raw entry / individual analysis input | 4,000 characters |
| Coursework corpus analysis | 500 entries / 100,000 text characters |
| CFG text | 12,000 characters, with additional parser work/size guards |
| Imported file / extracted text | 12 MiB / 40,000 characters |
| PDF / structured import drafts | 40 pages / 100 records |
| Coursework screenshots per project | 6; 2 MiB each; 12 megapixels |
| Account projects / entries | 20 / 10,000 |
| Saved history / entry revisions | 500 / 20,000 |
| Private recordings | 1,000 files / 128 MiB aggregate |

Limits are software bounds, not assignment targets or load certifications.
Screenshot PNG/JPEG inputs are decoded and normalized to bounded PNG storage.
The screenshot JSON route allows 3 MiB for base64 transport; other JSON requests
retain the generic 1 MiB cap. The coursework ZIP does not embed raw recordings;
use a workspace backup to preserve recordings and coursework together.
Storage or validation failures are explicit, not silently successful.

## Private storage and recovery

The default root is `.mboa`. Use an absolute persistent directory outside the
public web root for `MBOA_DATA_DIR` in production.

```text
.mboa\
  auth.sqlite3
  mail\                         development only
  workspaces\<account UUID>\
    workspace.sqlite3           projects, entries, revisions, history,
                                coursework profiles and screenshots
    audio\
    backups\
      previews\
```

Authentication chooses the server-owned account directory. Request-local
contexts select the project for both dataset and coursework storage.
Coursework profiles are JSON rows; screenshots are project-bound ID/name/base64
rows in the same account SQLite database. Screenshot downloads enforce the same
owner/project boundary. New profile/screenshot mutations increment the workspace
version. These are not globally shared academic files.

Legacy AI-generated saved translations/conversations remain in storage and
are accessible through the authenticated maintenance API and backups; there is
no History screen. Retaining the records does not re-enable generation.
No original accounts are migrated or deleted by this product change.
The standalone desktop collector and explicitly unauthenticated maintenance
factory can still access the legacy CSV/profile/screenshots. Normal application
startup is authenticated, and production refuses `require_auth=False`.

The authenticated workspace maintenance API retains verified ZIP creation,
download, daily/weekly scheduling and restore previews; there is no Settings
screen. Operators must authenticate as the owner and explicitly confirm
**REPLACE** before a restore.
Restore requires an unchanged version and creates a verified safety backup.
The **workspace document format is 2**, including coursework and screenshots;
format-1 documents remain restorable without those fields. The outer ZIP
**manifest stays format 1**. Checksums detect altered bytes, not archive authorship.
Unsafe paths, invalid records and missing media are rejected.

ZIP limits are 32 MiB compressed / 160 MiB expanded, with 512 MiB of server
backups per account and at most three one-hour pending previews. Automatic
retention is 1–10 copies; manual and safety backups are not silently pruned.
Backups contain private project data and media, not passwords, sessions or
server credentials. They are **not end-to-end encrypted** and same-disk copies
are not disaster recovery. Restrict filesystem access and protect an off-host,
database-consistent copy of the entire data root, including `auth.sqlite3`,
and configuration separately. Rehearse recovery in an isolated instance.

## Hosted deployment

Use one durable application host behind an HTTPS reverse proxy, not ephemeral
storage or an assumed multi-host SQLite cluster.

1. Build the frontend, configure `MBOA_ENVIRONMENT=production`, an HTTPS
   `MBOA_PUBLIC_URL`, and an absolute persistent `MBOA_DATA_DIR`.
2. Configure SMTP with STARTTLS and verify account verification/recovery mail.
   Production rejects development file-mail mode.
3. Optionally configure a Google Web OAuth client and the exact
   `<MBOA_PUBLIC_URL>/api/auth/google/callback` redirect. Existing password
   accounts must explicitly link Google through the authenticated maintenance
   API before using it; matching email is not automatic linking. Otherwise use
   the existing password and the sign-in screen's recovery flow.
4. Supervise `python -m tools.run_app` under a restricted service account.
   Bind the backend to loopback or a firewalled private interface.
5. Proxy all paths, preserve Host and set forwarded protocol/client address.
   Trust only the actual proxy addresses through `FORWARDED_ALLOW_IPS`.
6. Set upload/time limits consistently, avoid query-string logging, monitor
   errors/disk, renew TLS and maintain protected off-host backups.

Cookie/session, Origin, CSRF, trusted-host, HTTPS, request-bound and persistent
rate controls remain; CORS is not access control. Interactive API docs are
disabled in production. `httpx` remains required for Google identity exchanges.
Configuration precedence is explicit settings, environment, `backend\.env`,
root `.env`, defaults; restart after changes. Existing private `.env` files must
not be printed, committed or overwritten. Old `GEMINI_*` variables, if present
in private configuration, are unused and confer no language capability.

## API and verification

Health returns `{"status":"ok","mode":"compiler"}`. Private endpoints require
the account cookie. Mutations require the session's `X-CSRF-Token` and allowed
Origin; selected projects use `X-Mboa-Project`, with `?project=<id>` for native
media/image URLs. Project management and full-workspace backups are account-scoped.

| Area | Routes |
| --- | --- |
| Accounts | `/api/auth/session`, registration/login/logout, verification/recovery, profile, optional Google start/callback |
| Collection / lexer | `/api/metadata`, `/api/dataset`, `/api/dataset/{id}`, audio routes, `/api/analyze` |
| References / practice | `/api/dictionary`, `/api/examples` |
| Local import | `/api/imports/preview` |
| Compiler coursework | `/api/coursework`, `/project`, `/analyze`, `/parse`, `/screenshots`, `/screenshots/{id}`, `/export` under `/api/coursework` |
| Private recovery | projects, legacy history, revisions and backups under `/api/workspace` |

`/api/translate`, `/api/chat`, `/api/imports/suggest` and
`/api/coursework/explain` are removed, not optional provider-backed modes.

Use the existing checks; do not treat historical counts as current results:

```powershell
.\.venv\Scripts\python.exe -m tools.run_python_tests
.\.venv\Scripts\python.exe -m pip check
Push-Location frontend
try {
    npm run typecheck
    npm test
    npm run build
    npm run test:e2e -- --workers=2
    npm run test:e2e:live
} finally { Pop-Location }
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
.\.venv\Scripts\python.exe -m tools.check_documentation
```

The full Python suite includes preserved desktop tests and needs the optional
`requirements-desktop.txt`; server-only discovery can use
`.\.venv\Scripts\python.exe -m unittest discover -s backend -p "test_*.py" -t .`.
Install missing declared test dependencies only when needed. Browser suites use
the built bundle and synthetic isolated fixtures, not genuine field statements.

See the [documentation register](docs/README.md), [SRS](docs/srs.pdf),
[SDD](docs/sdd.pdf) and [UML atlas](docs/uml-atlas.pdf) for current scope and
verified document results. Existing [evidence records](docs/evidence) are kept
unaltered as historical records. Previous Gemini, translation, assistant,
dictation and cloud-media acceptance does **not** test this non-AI architecture;
old suite totals are not current verification or coursework completion.
