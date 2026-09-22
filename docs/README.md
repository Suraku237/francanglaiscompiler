# Mboa compiler documentation

**Version 3.0 · 22 September 2026 · CS4110 SET A**

The current documents describe the **authenticated, non-AI assignment product**.
Local testing and hosting exercise the same private account/project workflow.
They supersede the business/AI product guidance without rewriting its history.

## Reading order

| Document | Purpose |
| --- | --- |
| [SRS](srs.pdf) · [LaTeX](srs.tex) | Assignment traceability, functional/quality requirements, limits, evidence and human completion gates |
| [SDD](sdd.pdf) · [LaTeX](sdd.tex) | Deterministic compiler, isolated coursework storage, local imports, retained accounts/recovery and source-grounded UML |
| [UML atlas](uml-atlas.pdf) · [LaTeX](uml-atlas.tex) | Full-size readable diagram sheets, also embedded in the SDD |
| [PlantUML sources and PNGs](diagrams) | Editable current diagrams and the exact [production class inventory](diagrams/class-coverage.json) |
| [Operating guide](../README.md) | Startup, truthful assignment workflow, limits, configuration and verification commands |

The author group is Kwete Ngouba Junior Rayan (**ICTU20241377**),
Djemtchimo Noukui Bruno Jonatan (**ICTU20241585**) and Amina Boubakary
(**ICTU20241870**). These document identities do not prepopulate private accounts.

## Evidence and coursework status

The supplied brief requires 10–15 **real manually transcribed Yaoundé
statements**, a group of three, lexical specification/frequency/variation,
a corpus-derived CFG and transformations, FIRST/FOLLOW and an LL(1) table
(or the LR alternative), an implemented parser tested on the group's own data,
a 25–30-page final report capped at 30 pages, and a ten-minute presentation.
Each member presents for three minutes. The due date is **29 September 2026**.

At the 22 September scope review, the legacy CSV and three inspected hosted
workspaces had **zero entries**. The 179 dictionary rows, 26 constructed practice
examples and illustrative default grammar are not empirical fieldwork.
The user's genuine manually transcribed text file is still needed. The app can
export a **DRAFT HTML report, editable presentation and artifacts**, not certify
authenticity or final pagination. SRS/SDD PDFs are separate engineering documents,
not that 25–30-page submission. Screenshots must be actual analyzer captures.

## UML conventions

Every authored production Python/TypeScript class, including protocols and the
generated lexer `Token`, belongs in `class-coverage.json`. Tests, maintenance
tools, external framework types and erased TypeScript interfaces are excluded.
Selected operations use real method names. Function modules/hooks are shown as
such, not invented service classes.

Real nested/reference associations have cardinalities. Inheritance, protocol
realization and module dependencies do not acquire artificial multiplicities.
Each sequence call/reply has explicit, balanced caller/callee activations.
Historical desktop classes remain covered as preserved production code, with
their non-default legacy storage boundary made explicit.

All sources render locally; repository code or field data is not uploaded to
online diagram services. Large sheets retain their native aspect ratio instead
of being shrunk to unreadable A4 figures.

## Rebuild and verify

Use the existing VS Code **Build documentation PDFs** task, or from the root:

```powershell
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
if ($LASTEXITCODE -ne 0) { throw "Documentation build failed." }
.\.venv\Scripts\python.exe -m tools.check_documentation
if ($LASTEXITCODE -ne 0) { throw "Documentation verification failed." }
.\.venv\Scripts\python.exe -m unittest tools.tests.test_documentation_checks -q
```

The script renders PlantUML and compiles atlas → SRS → SDD with existing local
tools. `-SkipDiagrams` is only valid when diagram sources have not changed.
PlantUML's 8,192-pixel canvas ceiling is a guard, not proof against clipping;
inspect image bounds after layout changes.

The strict checker rejects incomplete/obsolete class inventories, mapped
classes absent from diagrams, missing or duplicate sheets, wrong atlas page
mapping, invalid sequence activations, stale embedded image pixels and LaTeX
layout/reference warnings. New classes or changed architecture are not reasons
to weaken these checks.

### Current verification

The final source inventory, diagram/page counts and exact successful validation
commands will be recorded here after the parallel implementation stabilizes and
the current documents are rebuilt. Until then, existing generated PDFs must not
be treated as verification of the new scope.

## Historical material is not current acceptance

All `docs/evidence/*.json` records remain unmodified. They describe their original
source versions, dates, fixtures and limits. Earlier Gemini, translation,
assistant, browser dictation and cloud-media successes do not exercise the current
non-AI product; earlier suite totals do not establish a current passing build.
Historical email/Google/device records also do not replace fresh deployment
acceptance.

`README.legacy.md`, `srs-legacy.tex`, `sdd-legacy.tex` and the root
`README.legacy.md` are explicitly archived. Previous business/AI implementation
history also remains in version control. Obsolete AI diagrams are removed from
the **current** atlas/inventory rather than presented as active architecture.
Legacy saved AI history remains private readable/exportable data, not generation.

## Remaining human gates

- Supply and review the real manual statements, provenance, consent and exact
  transcription; references and synthetic tests cannot substitute.
- Justify the CFG against those statements; inspect labels, unknowns, table
  conflicts, accepted/rejected cases and limitations.
- Capture real screenshots, author the linguistic discussion, check final
  25–30-page pagination and rehearse the ten-minute presentation.
- For public hosting, validate HTTPS, SMTP, Google configuration if enabled,
  browser recording/read-aloud, persistent storage and off-host recovery.
- Do not call the report finished or claim remote CI/provider tests without
  fresh evidence. No provider calls are required for the compiler workflow.
