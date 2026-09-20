# Mboa — Private Language Workspace

Mboa is an account-based web application for translation, terminology and
document/audio processing in French, English, Francanglais (Camfranglais) and
Cameroon Pidgin. Its seven areas are **Translate**, **Assistant**, **Terminology**,
**Dictionary**, **Documents & audio**, **History** and **Workspace settings**.

Each individual user has a private workspace and separate projects. Email and
password access includes email verification and recovery. Google sign-in is
available when the operator configures it. Local operation is for testing the
same application before hosting, not a separate unauthenticated product.

**Deployment status:** the software includes hosting controls and automated
tests, but a public launch still needs the owner's infrastructure, provider
configuration, human acceptance and operating policies listed below. There is
no claim of certified translation accuracy, production capacity or availability.
Payments, subscriptions and shared-team roles are not part of this release.

## Run the complete app locally

Requirements: Python 3.11+ and Node.js 22.12+ or a supported newer LTS. From the
repository root, install dependencies once:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Push-Location frontend
try { npm ci } finally { Pop-Location }
if (-not (Test-Path -LiteralPath backend\.env)) {
    Copy-Item -LiteralPath backend\.env.example -Destination backend\.env
}
```

Start the website and API together:

```powershell
.\start.ps1 -Build
```

Open **http://127.0.0.1:8000**. Use this exact origin consistently rather than
switching between `localhost` and `127.0.0.1`. For later starts without source
changes, use `.\start.ps1`. Stop with **Ctrl+C**.

The cross-platform equivalent, using the selected Python environment, is:

```powershell
.\.venv\Scripts\python.exe -m tools.run_app --build
```

The launcher does not silently install dependencies. It refuses non-loopback
development access and production code reload. `-Port 8001` / `--port 8001` is
supported; an explicitly configured `MBOA_PUBLIC_URL` must match the origin.
The built frontend is served by **FastAPI**, on the same origin as `/api`.
Vite is not required to remain running.

### Test your account

1. Select **Create an account**, use an email address you control and a unique
   password of at least 12 characters.
2. In default development mode, email is written to the private
   `.mboa\mail` outbox, **not sent to the internet**. Open your own generated
   `.eml` file, follow its verification link and press **Verify email**.
3. Sign in. New accounts start with an empty **General** project. No historical
   CSV data, student identities or other users' records are imported.
4. Try Dictionary → search `tchop` → **Open in translator** → **Translate**.
   The supplied `to eat` lookup works without an AI key.
5. Use **Save translation** to retain the result in **History**. Unsubmitted
   drafts disappear on reload; saving is always explicit.

Verification and recovery links are secrets. Do not publish the development
outbox or forward links to others. Production configuration rejects file-mail
mode and requires actual SMTP delivery.

### Optional development servers

For frontend hot reload, keep the API on port 8000 and run `npm run dev` in
`frontend`. Vite proxies `/api` from port 5173. Configure `MBOA_PUBLIC_URL` to
the browser origin for verification and Google callbacks, and use the same
hostname consistently. Add only required development origins to `CORS_ORIGINS`.
For a release-like local test, prefer the one-origin launcher above.

## Use the workspace

### Translation and terminology

- Exact, unambiguous approved terminology or supplied dictionary alignments
  take precedence over optional AI. Matching unrelated words is not a complete
  sentence translation. Ambiguous or unavailable local-only results produce an
  explicit error, not a fabricated answer.
- AI suggestions are labelled and carry the selected supporting evidence.
  Approval means **your review**, not independent linguistic certification.
  Editing evidence invalidates its previous approval.
- Projects separate terminology and saved work inside one account. Project
  switching and sign-out warn before clearing unsaved drafts and recordings.
- **Export results (JSON)** includes only displayed terminology and its review
  metadata. Referenced audio is not embedded; use a full backup for that.
- **History** stores explicitly saved translations/conversations. Open, search,
  rename, download, reuse as a draft or delete them. Reusing text never silently
  sends an AI request.
- **Workspace settings** exposes terminology revisions. Restoring one creates
  another revision and marks the term **unreviewed**. A stale workspace version
  prevents overwriting changes made since the recovery view was loaded.
- An empty project can be deleted after switching to another project. General
  cannot be deleted. A project with terminology, revisions or saved work is not
  silently destroyed.

### Dictionary and source limitations

The [core dictionary](dictionary/camfranglais.md) has 143 source rows and the
[supplement](dictionary/extra_lexicon.md) has 36: **179 references**, not 179
unique words or approved terminology. Repeated words and competing meanings
remain visible. Search retains source filename/line, topic and supplied origin.

These references have **English meanings only**. Etymological origin is neither
a French translation nor a part-of-speech annotation. French glosses and business
usage need human review. The dictionary is read-only and never populates private
terminology automatically. Confirm redistribution permissions before launch.

### Audio and documents

Browser recording is distinct from browser dictation and AI transcription:

- **Record audio** captures locally in the current tab. Stop, preview and
  download it before deciding to save. Recording alone does not upload anything.
- An explicit terminology save uploads the attachment privately to your account.
  Failed saves preserve the draft and report errors. Existing recordings are not
  silently deleted when a term or attachment reference is removed.
- Documents & audio uploads a chosen file to the application server on
  **Preview source text**. Text formats, DOCX and text-layer PDFs are extracted
  without AI. This is server processing, not on-device extraction.
- Images, scanned PDFs and media require fresh cloud-processing consent and an
  explicit preview action. Changing the file resets consent. Raw import uploads
  are temporary; save reviewed terms/results separately.
- Browser dictation/read-aloud may use browser-vendor services and approximate
  Francanglais/Pidgin with French/English voices. HTTPS or loopback and browser
  permission are required for microphone features. Typing and file selection
  remain available when recording is unsupported.

Inputs include UTF-8 TXT/Markdown/CSV/JSON, PDF, DOCX, PNG/JPEG/WebP,
MP3/WAV/M4A/OGG/FLAC and MP4/WebM/MOV. Limits are 12 MiB per input, 40 PDF
pages, 12 megapixels per image, 40,000 extracted characters and 100 structured
draft records. Translation input is at most 4,000 characters. Review each
complete passage; unsupported codecs or truncated provider output are errors.

## Private storage and recovery

The default private data root is `.mboa`; production should set `MBOA_DATA_DIR`
to an **absolute persistent directory outside the public web root**:

```text
.mboa\
  auth.sqlite3
  mail\                         development only
  workspaces\<account UUID>\
    workspace.sqlite3
    audio\
    backups\
      previews\
```

Account and workspace data use SQLite transactions. Per-account file locks
coordinate media/backup operations; request-local storage contexts prevent
process-global account/project switching. The server operator can access the
underlying infrastructure: this is account isolation, **not end-to-end
encryption**. Use restricted service-account/NTFS permissions or Unix permissions,
encrypted storage and off-host backups.

Per-account limits are 20 projects, 10,000 terminology entries, 500 saved items,
20,000 terminology revisions and 1,000 recordings / 128 MiB aggregate audio.
Saved conversations contain at most 100 messages. Limits produce explicit
errors; histories and revisions are not silently truncated to make a save succeed.

### In-app backups

In **Workspace settings**:

1. **Create verified backup**, then download the ZIP to protected storage.
2. Optionally enable daily or weekly backups with 1–10 automatic copies.
   The server checks schedules every minute while running. Failures are logged
   and the workspace displays the last failure; a later cycle retries.
3. To restore, select a ZIP and **Validate and preview backup**. Review counts
   and the replacement warning.
4. Type **REPLACE**. Restore requires an unchanged workspace version and creates
   a verified **pre-restore safety backup** before replacing logical records.

Backups include all projects, terminology, revisions, saved work and recordings,
but not account passwords, sessions or server provider configuration. A SHA-256
manifest detects tampering; it does **not** authenticate the archive's author.
Unsafe paths, duplicates, links, malformed data and missing audio are rejected.
Changed media with colliding filenames is remapped, not overwritten.

An in-app ZIP is limited to 32 MiB compressed / 160 MiB expanded; server backups
are capped at 512 MiB per account. At most three one-hour restore previews may
be pending. Manual and safety backups are not automatically pruned. Download
and deliberately delete old backups when necessary. Larger workspaces need
operator-level backup. Deleted records/media can remain in revisions and backups.

**Disaster recovery is separate:** in-app backups on the same disk do not protect
against disk loss. Stop the application or use a database-consistent snapshot
process to back up the entire data root, including `auth.sqlite3`, and protect
configuration separately. Rehearse restoration to an isolated instance before
reopening service. A workspace ZIP alone cannot recover account identities.

## Hosted deployment

This release targets **one durable application host**, behind an HTTPS reverse
proxy. It is not a stateless or multi-host shared-database service. Do not place
private SQLite data on ephemeral deployment storage or assume network filesystems
provide the required locking semantics.

1. Choose a host, domain and persistent storage; install server dependencies.
2. Build the frontend with `npm ci` and `npm run build`.
3. Configure secrets using environment variables or a restricted server-only
   environment file. See [the safe template](backend/.env.example).
4. Set `MBOA_ENVIRONMENT=production`, `MBOA_PUBLIC_URL=https://your-domain`
   and an absolute `MBOA_DATA_DIR`.
5. Configure SMTP with STARTTLS, a sender address and your provider's credentials.
   Test real verification and recovery delivery, including spam handling.
6. Optionally configure a Google **Web application** OAuth client. Register
   `https://your-domain/api/auth/google/callback` as its redirect URI and complete
   the authorized-domain/consent configuration. Existing password accounts must
   explicitly link Google while signed in; matching emails alone are not linked.
7. Start with `python -m tools.run_app` under a supervised service account. Bind
   to loopback when the reverse proxy is on the same host. For a controlled
   internal proxy network, explicitly set `--host` and firewall the backend.
8. Proxy **all paths**, not only `/api`, to the application. Terminate HTTPS,
   preserve the public Host header and set forwarded protocol/client address.
   Configure Uvicorn's `FORWARDED_ALLOW_IPS` to the actual trusted proxy addresses;
   never trust arbitrary forwarded headers from the internet.
9. Set proxy upload limits consistently with the 32 MiB backup upload plus
   multipart overhead. Set request timeouts to accommodate approved media work.
   Avoid logging query strings: they can contain OAuth codes or search text.
10. Configure restart-on-failure, disk and error monitoring, TLS renewal,
    restricted/off-host backups, retention and a tested recovery procedure.

Production enables Secure/HttpOnly/SameSite cookies, origin and CSRF checks,
HTTPS enforcement, trusted hosts, restrictive browser headers, request bounds
and persistent rate limits. Interactive API documentation is disabled.
CORS is **not** access control.

`GEMINI_API_KEY` is optional and server-only. Do not place it in `VITE_` variables
or commit it. The default model is configurable; access and charges depend on
the provider account. User/global daily limits default to 100/2,000 actual
outbound attempts, including retries. Exact local lookups consume no allowance.
The health indicator reports configuration, not successful provider acceptance.

Configuration precedence: explicit test settings, environment, `backend/.env`,
root `.env`, defaults. The example is not loaded automatically. Restart after
changes. No production mail, Google or Gemini credentials are included.

## API and automated verification

Except health and account-access endpoints, APIs require the account cookie.
Mutations require the matching `X-CSRF-Token` from `/api/auth/session` and the
configured Origin. Scoped requests use `X-Mboa-Project`; native media URLs can
use `?project=<id>`. Projects and full-workspace backups are account-scoped.
Never choose an account directory from a client-supplied identifier.

| Area | Endpoints |
| --- | --- |
| Accounts | `/api/auth/session`, `/register`, `/login`, `/logout`, `/verify-email`, `/resend-verification`, `/forgot-password`, `/reset-password`, `/profile`, `/google/start`, `/google/callback` under `/api/auth` |
| Language services | `/api/translate`, `/api/chat`, `/api/analyze`, `/api/dictionary` |
| Terminology/audio | `/api/metadata`, `/api/dataset`, `/api/dataset/{id}`, `/api/dataset/audio`, `/api/dataset/{id}/audio` |
| Imports | `/api/imports/preview`, `/api/imports/suggest` |
| Private organization | `/api/workspace/projects`, `/history`, `/revisions` under `/api/workspace` |
| Recovery | `/api/workspace/revisions/{id}/restore`, `/api/workspace/backups` with settings, preview, restore and download subroutes |

Run the existing checks from the repository root:

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
```

The complete Python suite includes preserved desktop regressions and therefore
needs `requirements-desktop.txt`. Install that optional manifest for the full
suite, not for normal web hosting. For server-only checks use
`python -m unittest discover -s backend -p "test_*.py" -t .`.
If Chromium is missing, install the existing test dependency with
`npx playwright install chromium` from `frontend`.

Unit tests isolate storage/providers/devices. Mocked browser tests verify UI
contracts; the separate live suite runs the real built website, account API,
SQLite, cookies, local email outbox and backup downloads on loopback port 4190.
Its accounts/content are synthetic, external processing is disabled and physical
devices are not used. Browser fixtures do not write into real user workspaces.
Full-stack success is not proof of real email, Google consent, live AI quality or
physical-device acceptance.

Both browser suites use the production bundle. Run `npm.cmd run build` after
frontend edits and before either suite; the mocked suite serves it with Vite
preview rather than exercising development-server compilation.

For repeatable private API measurements with 1,000 synthetic 500-character
entries, one warm-up and 20 measured runs:

```powershell
.\.venv\Scripts\python.exe -m tools.benchmark_workspace --output docs\evidence\hosted-benchmark.json
```

This checks exact response counts and verified backup creation against a 1,000 ms
local p95 budget. It uses a temporary account and real SQLite/ASGI handlers, not
live business data. It excludes network/TLS/browser rendering and is neither
concurrent-user load certification nor an 8 GB reference-machine result.

See [the documentation register](docs/README.md), [SRS](docs/srs.pdf),
[SDD](docs/sdd.pdf) and [UML atlas](docs/uml-atlas.pdf). Generated evidence records
describe their actual machine and test boundaries; remote CI is a separate gate.

## Owner actions before public launch

- Supply the hosting account, domain/HTTPS, durable storage, monitoring and
  off-host backup destination; approve capacity and recovery targets.
- Supply SMTP sender credentials and Google OAuth configuration; verify real
  account emails, Google consent, account linking and recovery.
- Decide the Gemini budget and authorize non-sensitive live trials; review
  translations/transcriptions with competent Francanglais/Pidgin speakers.
- Supply approved business terminology, reviewed French meanings and permission
  to redistribute the supplied reference material.
- Test microphone/speakers, denied permissions, disconnects, browser voices,
  real mobile devices and assistive technology.
- Approve privacy/retention/terms, support contacts and the final public launch.
  Decide how long deleted records, media and safety backups must be retained.
- Authorize publishing these changes and verify all remote CI jobs. A passing
  local run does not establish Windows 3.11/Linux or production-host acceptance.

## Preserved legacy scope

The [historical guide](README.legacy.md), desktop collector, compiler research
and [26 explicitly constructed examples](examples/camfranglais_statements.csv)
remain available for maintenance. They are not business onboarding or a genuine
fieldwork corpus. Hosted users never inherit the global CSV, academic profile,
student identities or screenshots.

The default API excludes academic routes. Isolated archive maintenance requires
the explicit `create_app(require_auth=False, include_academic=True)` factory;
there is no environment switch disabling hosted authentication, and production
rejects that combination. The standalone desktop collector still uses the legacy
CSV/audio storage, not a signed-in hosted workspace.
