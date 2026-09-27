# Camfranglais documentation

**Version 4.0 · 27 September 2026 · CS4110 SET A**

This edition documents the actual **public, non-AI, five-screen application**:
anyone may analyze and retain immutable tests, while Collection, saved grammar
and recordings are read-only. It replaces the old account/private-project,
editable-grammar and in-app report-generation guidance without rewriting
historical archives.

## Deliverables and reading order

| Document | Purpose |
| --- | --- |
| [Final coursework report](final-report.pdf) · [LaTeX](final-report.tex) | Fixed twelve-statement study; all raw text and token tables; real regex/CFG calculations, complete LL(1) table and representative complete traces; browser evidence and linguistic limitations |
| [SRS](srs.pdf) · [LaTeX](srs.tex) | Public permissions, functional/quality requirements, failure contracts, limits and acceptance criteria |
| [SDD](sdd.pdf) · [LaTeX](sdd.tex) | Source-grounded design and UML; active public boundary distinguished from retained legacy/desktop code |
| [UML atlas](uml-atlas.pdf) · [LaTeX](uml-atlas.tex) | One full-size zoomable sheet per current diagram, also embedded in the SDD |
| [PlantUML and PNGs](diagrams) | Editable sources, rendered images and the exact [class-coverage inventory](diagrams/class-coverage.json) |
| [Operating guide](../README.md) | Local launch, public behavior, storage, deployment and test commands |

The coursework report is the **25–30-page submission document**; the SRS, SDD
and atlas are separate supplements and are not subject to that limit. The
checker counts actual PDF pages, including the cover and contents, not sections.

The published edition has **29 report pages, 11 SRS pages, 52 SDD pages and
35 atlas sheets**. The SDD includes all 35 full-size UML sheets after its
narrative; the separate atlas contains only those sheets.

The known author group is filled on the covers:

| Name | Matricule |
| --- | --- |
| Kwete Ngouba Junior Rayan | ICTU20241377 |
| Djemtchimo Noukui Bruno Jonatan | ICTU20241585 |
| Amina Boubakary | ICTU20241870 |

Signatures and individually confirmed contributions remain blank for the
authors. No account or privileged application role is created from these names.

## Evidence boundaries

The [corpus snapshot](evidence/final-corpus-20260927.json) was extracted
read-only from the existing shared Collection. Its twelve raw strings match
the [exact regression cases](../compiler/tests/yaounde_cases.py), and its saved
grammar matches the [corpus grammar source](../compiler/parser/yaounde.py).
Only public coursework text and relevant metadata are included, not accounts,
credentials, sessions or private configuration.

The [computed analysis](evidence/final-analysis-20260927.json) and
[generated LaTeX tables](report-data) contain:

- Twelve supplied statements, 81 tokens, 55 case-folded forms.
- Full token/category tables, frequencies, observed spelling variation and
  26 language-transition clues.
- The original grammar, two actual transformations, complete FIRST/FOLLOW
  sets, 39 transformed productions and all 47 populated LL(1) table cells.
- Ten accepted originals and two rejections at token six (`n'ais`, `alli`).
- Complete traces for all twelve cases in JSON; full S02/S09/S10 traces in the
  report; seven additional constructed boundary controls.
- Source SHA-256 fingerprints for reproducibility. Text is hashed as UTF-8
  without BOM with line endings normalized to LF, so Git's Windows/Unix
  checkout conversion does not produce false evidence changes.

**Fieldwork remains unconfirmed.** The saved manual-transcription flag is false
and collection method is blank. Some locations and audio references exist, but
they do not establish the original utterance's date, collector or consent.
Supplied meanings have not been independently validated. Numerical corpus size,
available recordings and successful parsing cannot certify authenticity.

The 938 dictionary entries and 26 synthetic examples are reference/practice
material, not additional field statements. Vocabulary recognition, CFG fit
and linguistic correctness are deliberately distinguished.

### Genuine screenshots, not mockups

The [capture register](evidence/screenshots/captures-20260927.json) records
six images: four real browser captures and two cropped derivatives. They were
captured locally with Playwright Chromium from the deployed application, using
its real API and no mocked responses. The report embeds four images:

- [Public analyzer input panel](evidence/screenshots/public-analyzer-20260927.png);
  its [full-page view](evidence/screenshots/public-analyzer-full-20260927.png)
  is retained.
- [Loaded read-only Collection](evidence/screenshots/public-collection-20260927.png).
- [Saved-test statistics](evidence/screenshots/public-analysis-20260927.png).
- [Selected S02 token panel](evidence/screenshots/public-test-20260927.png);
  its [uncropped original](evidence/screenshots/public-test-full-20260927.png)
  is retained.

No new test was submitted for these captures. The history screenshot shows 34
tests and 179 token occurrences, including repeats and older snapshots. These
are not the fixed twelve-statement/81-token evaluation. The register records
the crop coordinates, capture context and image hashes. Screenshots establish
working software, not authentic original field recordings.

## UML modeling rules

Every authored production Python/TypeScript runtime class is covered, including
protocols and the lexer `Token` namedtuple. Tests, tools, framework/vendor classes
and erased TypeScript interfaces are outside that inventory. Selected methods
use actual source names. Modules, React functions/hooks and record-shaped data
must not be turned into invented runtime classes.

The inventory contains **98 production classes** across **18 class views**.
The other sheets are **nine sequence, three activity, two state, one use-case,
one component and one deployment diagram**.

Real associations have meaningful multiplicities. Inheritance, protocol
realization and dependencies do not receive artificial cardinalities.
Optional/collection-valued fields and retained legacy relationships are
distinguished. Overview and detailed views are provided instead of making a
single unreadable all-to-all graph. String lengths and numeric bounds are
written as constraints in braces, not misleading object multiplicities.

Each sequence call activates its receiver; callers/return receivers are active,
replies match their calls, and activations close explicitly. Active public
workflows are distinguished from retained private or desktop compatibility
paths. Diagram sources render locally; no code or private data is uploaded to
an online renderer. Large atlas sheets preserve their aspect ratio for zooming.

## Rebuild and verify

Use the existing VS Code **Build documentation PDFs** task. From the repository
root, the equivalent commands are:

```powershell
.\.venv\Scripts\python.exe -m tools.build_report_evidence --check
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
.\.venv\Scripts\python.exe -m tools.check_documentation
.\.venv\Scripts\python.exe -m unittest tools.tests.test_documentation_checks tools.tests.test_report_evidence
```

When intentionally regenerating evidence after a reviewed compiler/snapshot
change, omit `--check` from the report-evidence command. Review the resulting
data and narrative together before publishing. Generation never reads or writes
the live SQLite database; it uses the committed public snapshot.

The build order is **UML atlas → SRS → SDD → final report**. It uses Java and
PlantUML for PNGs, then the installed `pdflatex` or Tectonic; portable tools may
reside in the ignored `.tools` directory. `-SkipDiagrams` is appropriate only
when current PNGs already match unchanged diagram sources. Intermediate files
and logs go to the ignored `.build` directory; PDFs are copied into this folder.

The strict [checker](../tools/check_documentation.py) rejects:

- Missing/obsolete production-class coverage and missing declarations.
- Unused/missing diagrams, duplicate sheets and wrong SDD/atlas page mappings.
- Unbalanced sequence activations or mismatched calls/replies.
- Missing/stale embedded UML pixels.
- Missing/stale screenshot capture hashes or screenshots absent from the report.
- Stale computed evidence or generated table fragments.
- LaTeX layout/reference/missing-character errors and unresolved PDF references.
- A report shorter than 25 or longer than 30 actual PDF pages.

The compiler's non-fatal Fontconfig configuration diagnostic is separate from
LaTeX layout errors. Font embedding and representative rendered pages are
inspected as part of publication. No warning threshold or UML rule is weakened
to make the documents pass.

## Validation and remaining gates

The final [verification record](evidence/final-documentation-verification-20260927.json)
records the published page counts, class/diagram coverage, image checks,
report evidence and tooling regressions. The **strict documentation checker
passed** against all four published PDFs, with no LaTeX layout/reference
errors or clipped image placements. All **28 focused documentation,
report-evidence and corpus grammar/persistence tests** passed on 27 September,
including the seven corpus tests. Workflow syntax and the edited Python files'
editor diagnostics were also checked successfully.

Earlier application-release evidence is dated **26 September**: 186
backend/launcher/legacy-storage passes, 148 frontend unit passes, 68 mocked
browser passes, passing app/test type checks and production build. Fourteen
distinct live workflows passed across a full run and a focused rerun. Two
full-run fixture startup/teardown interruptions passed in a three-test mobile
rerun; this was not an uninterrupted 14/14 run.

One known old category-expectation regression remains in
[the parser test suite](../compiler/tests/test_parser.py). It omits nine
currently supported categories; this documentation-only task does not repair
it or claim fully green CI.

The public HTTPS bootstrap and five-screen no-login interface were verified
read-only on 27 September. The documentation session did not perform remote
updates or certify long-term uptime, full backup recovery or all deployment
settings.

Before academic submission, the group must confirm or explicitly qualify
fieldwork provenance, review linguistic annotations and individual contributions,
and prepare/rehearse the ten-minute presentation. This edition supplies the
report and engineering documentation, not a claim that the oral assessment
or instructor approval is already complete.

## Historical archives

[The legacy guide](README.legacy.md), [legacy SRS](srs-legacy.tex),
[legacy SDD](sdd-legacy.tex), [root legacy guide](../README.legacy.md) and older
[evidence files](evidence) remain historical records. Old AI/authenticated
workflows, zero-corpus statements, starter-grammar claims, benchmark ratios and
test totals must not be reused as facts about this edition.
