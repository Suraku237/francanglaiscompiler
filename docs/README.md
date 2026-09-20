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

Run the commands in the [main README](../README.md). The verification record
in [evidence](evidence) must identify the actual source/environment and executed
results; older files remain historical evidence, not current totals.

The automated layers are:

1. Isolated Python tests across accounts, API, storage, providers, archive code,
   desktop behavior, snapshot recovery and maintenance tools.
2. Frontend app/test type checks, unit/component regressions and production build.
3. Mocked desktop/mobile browser workflows, including synthetic audio capture.
4. Real local desktop/mobile browser accounts, local-email verification/reset,
   cross-tab sign-out, private data, history, revisions and backup replacement.
5. Workflow syntax, diagram rendering, LaTeX and strict PDF verification.

No automated check here establishes real SMTP deliverability, Google consent,
Gemini quality, physical microphone/speaker operation, assistive-technology
acceptance, reference-machine compliance or hosted availability. The original
desktop benchmark was measured on approximately 31.8 GiB RAM, not 8 GB.

## Release-owner checklist

- Hosting/domain/HTTPS, durable private storage, trusted proxy, monitoring,
  service account and protected off-host recovery.
- SMTP sender credentials and real delivery; Google OAuth client, consent and
  authorized redirect; provider budget and authorized non-sensitive trials.
- Reviewed business terminology/French meanings and redistribution permission
  for supplied references.
- Physical devices, real mobile browsers, browser voice and assistive technology.
- Privacy, retention/deletion, terms/support and approved capacity/recovery goals.
- Authorization to publish changes, a passing remote CI workflow and launch
  approval. Local success is not remote CI or a public deployment.
