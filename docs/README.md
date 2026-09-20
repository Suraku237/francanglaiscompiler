# Mboa business documentation

Version 2.0 describes the **authenticated hosted web application**, with local
pre-hosting testing. It replaces the earlier local-only deployment guidance.

## Documents and scope

- [SRS](srs.pdf), [LaTeX source](srs.tex): 19 business functional requirements,
  six non-functional requirements, data limits, traceability and owner gates.
- [SDD](sdd.pdf), [LaTeX source](sdd.tex): accounts, private SQLite projects,
  request binding, saved work, media, verified recovery, deployment and failure
  contracts.
- [UML atlas](uml-atlas.pdf), [source](uml-atlas.tex): **35** full-size sheets,
  including **11 class views** and **17 sequence views**.
- [Editable diagrams and rendered images](diagrams): 75 authored production
  classes in the [exact coverage inventory](diagrams/class-coverage.json).
  Protocols count; erased TypeScript interfaces, external types and test helpers
  do not. Actual references carry multiplicities; dependencies do not.
- [Current operating instructions](../README.md): one-command startup,
  configuration, backups and hosting.

Every sequence call/reply has an explicit activation box. The SDD embeds the
same large-format atlas images rather than shrinking complex diagrams to
unreadable A4 figures. Sources are rendered locally; project code is not sent
to online diagram services.

## Preserved historical material

[Previous SRS source](srs-legacy.tex), [previous SDD source](sdd-legacy.tex),
[previous documentation register](README.legacy.md) and [the archived local
guide](../README.legacy.md) preserve earlier academic/local context. They are
not current hosting instructions or evidence that human research was completed.
The three supplied identities are retained in the archived author records.

The SDD explicitly marks preserved desktop/compiler/coursework diagrams.
Hosted users cannot access the old global CSV, academic profile, constructed
examples or screenshot exports. The main business documents contain no school
submission checklist or proposed academic sprint-completion claim.

## Rebuild and verify

From the repository root, with Java and the already configured local tools:

```powershell
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
if ($LASTEXITCODE -ne 0) { throw "Documentation build failed." }
.\.venv\Scripts\python.exe -m tools.check_documentation
if ($LASTEXITCODE -ne 0) { throw "Documentation verification failed." }
```

The script renders every PlantUML source, then builds atlas → SRS → SDD.
Use `-SkipDiagrams` only when sources are unchanged. The VS Code **Build
documentation PDFs** task performs the full render/build.

The renderer uses an 8,192-pixel canvas limit because the complete hosted
component and deployment views exceed PlantUML's 4,096-pixel default. Check
the full image bounds after layout changes; a successful render alone does
not establish that a diagram is unclipped.

The checker rejects missing production classes, undeclared mapped classes,
duplicate/missing sheets, unbalanced sequence calls, stale embedded image
pixels and LaTeX reference/layout warnings. It is not weakened for new classes
or existing archived source.

## Verification boundaries

The current [hosted verification record](evidence/hosted-verification.json)
records an earlier full run of 360 passing Python tests, 124 frontend unit/component tests, 30 mocked
browser tests and six real local desktop/mobile workflows. App/test types,
production build, dependency consistency, workflow syntax and the unchanged
strict documentation checker passed.

The final Python suite also passed from clean tracked sources without private
CSV/environment files. The [published CI run](https://github.com/Suraku237/francanglaiscompiler/actions/runs/35502314890)
passed its frontend/browser and documentation jobs, but exposed a Python test
that depended on the ignored local CSV. The synthetic-fixture correction is
verified locally; it still needs publication and a passing full CI rerun.

The subsequent Google callback diagnostics update passed **46 account/web-boundary
tests**. A separate owner-assisted **real Google sign-in** succeeded on loopback
after reloading the updated private configuration. The callback, authenticated
Google-linked/verified-email session and private workspace access were checked.
This local success does not verify production consent/redirect settings,
explicit account linking, SMTP delivery or the VPS deployment.

The later bounded Gemini retry change passed **197 backend tests**. The
[live translation record](evidence/translation-verification.json) contains one
successful AI-only French-to-English sample; three measured directions failed
with provider availability/quota errors, and eight were not attempted. It is
not an all-language or native-speaker quality certification. The two affected
sequence views and all published PDFs were rebuilt and strictly verified.

The [real email acceptance record](evidence/email-verification.json) adds
**22 passing HTTP checks** with real SMTP and owner-confirmed receipt of three
test messages. Verification/resend, single-use links, password recovery,
revocation of old sessions and preserved private data passed in isolated
temporary storage. The owner's Google account was unaffected. This is local
SMTP/API acceptance, not a new browser-form run or production VPS mail approval.

The [local document acceptance record](evidence/document-verification.json)
adds **23 passing import tests** and **4 real desktop/mobile-layout browser
workflows** with passing app/test type checks. All six local formats passed
representative previews, draft handoff and explicit unreviewed saving. A
reproduced PDF page-separator counting defect was corrected at the exact
40,000-character boundary. Invalid files and missing cloud consent produce
explicit errors; test accounts and temporary storage were removed. The local
server was restarted without losing the owner's Google session. No Gemini
calls or real emails were used, and cloud OCR/transcription remain unverified.

The [audio acceptance record](evidence/audio-verification.json) subsequently
records **72 targeted backend tests**, **19 audio unit tests**, **4 mocked audio
browser tests**, and **all 10 current real desktop/mobile-layout workflows**
passing. Native recording, muted playback, byte-preserving private audio
storage/download, range requests, access controls, explicit attachment removal
and consent errors were checked without AI or real SMTP. Existing live accounts
were reused for the audio scenarios without relaxing production rate limits.
Only test fixtures/coverage changed for audio; physical devices, browser
dictation, audible speech output and cloud transcription remain separate gates.

The owner subsequently confirmed physical microphone recording and audible
playback in Chrome/Edge. The reported VS Code-only playback failure was also
reproduced with a synthetic local WebM blob in its embedded browser, yielding
media error 4 and an FFmpeg demuxer open failure. This is recorded separately
from the automated results; use Chrome/Edge for audio acceptance. Browser
dictation, read-aloud, physical-mobile and cloud-transcription checks remain.

The published SRS has **9 pages**, the SDD **46 pages**, and the atlas **35 sheets**.
All 75 production classes and 17 explicitly activated sequence views passed
the source/PDF checks. Published PDFs match the final build byte-for-byte.

Run the commands in the [main README](../README.md) to repeat verification.
The [hosted performance measurements](evidence/hosted-benchmark.json) cover
1,000 synthetic entries and real private API/SQLite/ZIP operations. All three
local p95 values are below the 1,000 ms budget on the recorded machine.
Older files in [evidence](evidence) remain historical, not current totals.

The automated layers are:

1. Isolated Python tests across accounts, API, storage, providers, archive code,
   desktop behavior, snapshot recovery and maintenance tools.
2. Frontend app/test type checks, unit/component regressions and production build.
3. Mocked desktop/mobile browser workflows, including synthetic audio capture.
4. Real local desktop/mobile browser accounts, local-email verification/reset,
   cross-tab sign-out, private data, history, revisions, backup replacement and
   local document extraction/review and native synthetic audio capture/playback.
5. Workflow syntax, diagram rendering, LaTeX and strict PDF verification.

No automated check here establishes real SMTP deliverability, Google consent,
Gemini quality, physical microphone/speaker operation, assistive-technology
acceptance, reference-machine compliance or hosted availability. The original
desktop benchmark was measured on approximately 31.8 GiB RAM, not 8 GB.
The hosted benchmark used that same memory configuration and excludes
network/TLS, browser rendering and concurrent-user load certification.

## Release-owner checklist

- Hosting/domain/HTTPS, durable private storage, trusted proxy, monitoring,
  service account and protected off-host recovery.
- Production VPS SMTP delivery/recovery and sender/domain checks (local SMTP and
  inbox acceptance passed); production Google consent/domain/redirect settings
  and explicit account linking (local Google sign-in passed); provider budget
  and authorized non-sensitive trials.
- Reviewed business terminology/French meanings and redistribution permission
  for supplied references.
- Physical devices, real mobile browsers, browser voice and assistive technology.
- Privacy, retention/deletion, terms/support and approved capacity/recovery goals.
- Publication of the final local test fix and verification records, a passing
  complete remote CI workflow and launch approval. Local success is not a public
  deployment.
