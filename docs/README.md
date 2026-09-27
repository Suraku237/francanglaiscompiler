# Camfranglais documentation

**Version 4.1 · 27 September 2026 · CS4110 SET A**

This edition documents the actual **public, non-AI, five-screen application**:
anyone may analyze and retain immutable tests, while Collection, saved grammar
and recordings are read-only. It replaces the old account/private-project,
editable-grammar and in-app report-generation guidance without rewriting
historical archives.

## Deliverables and reading order

| Document | Purpose |
| --- | --- |
| [12-slide PowerPoint](camfranglais-presentation-12-slides.pptx) · [PDF preview](camfranglais-presentation-12-slides.pdf) | Essential oral presentation: app workflow, real screenshots, key source files, compiler automata and results; exactly 12 editable slides with speaker notes |
| [Final coursework report](final-report.pdf) · [LaTeX](final-report.tex) | Fixed twelve-statement study; all raw text and token tables; regex/CFG calculations, lexer DFA and parser pushdown models, complete LL(1) table and representative complete traces; browser evidence and linguistic limitations |
| [SRS](srs.pdf) · [LaTeX](srs.tex) | Public permissions, functional/quality requirements, failure contracts, limits and acceptance criteria |
| [SDD](sdd.pdf) · [LaTeX](sdd.tex) | Source-grounded design and UML; active public boundary distinguished from retained legacy/desktop code |
| [UML and automata atlas](uml-atlas.pdf) · [LaTeX](uml-atlas.tex) | One full-size zoomable sheet per current diagram, also embedded in the SDD |
| [PlantUML and PNGs](diagrams) | Editable sources, rendered images and the exact [class-coverage inventory](diagrams/class-coverage.json) |
| [Operating guide](../README.md) | Local launch, public behavior, storage, deployment and test commands |

The coursework report is the **25–30-page submission document**; the SRS, SDD
and atlas are separate supplements and are not subject to that limit. The
checker counts actual PDF pages, including the cover and contents, not sections.

The published edition has **30 report pages, 11 SRS pages, 56 SDD pages and
37 atlas sheets**.
The SDD includes all 37 full-size sheets after its narrative: **35 UML views
and two formal automata**. The separate atlas contains only those sheets.
The [verification record](evidence/final-documentation-verification-20260927.json)
lists the physical page counts and hashes of all four PDFs.

The shared design uses navy headings, teal accents, pale-mint table headers
and restrained gold rules. Covers retain the known identities below; signing
columns and handwritten approval/contribution blanks have been removed.

The known author group is filled on the covers:

| Name | Matricule |
| --- | --- |
| Kwete Ngouba Junior Rayan | ICTU20241377 |
| Djemtchimo Noukui Bruno Jonatan | ICTU20241585 |
| Amina Boubakary | ICTU20241870 |

Individual contributions still require the group's own review; they are not
invented by the documentation. No account or privileged application role is
created from these names.

## Evidence boundaries

The [corpus snapshot](evidence/final-corpus-20260927.json) was extracted
read-only from the existing shared Collection. Its twelve raw strings match
the [exact regression cases](../compiler/tests/yaounde_cases.py), and its saved
grammar matches the [corpus grammar source](../compiler/parser/yaounde.py).
Only public coursework text and relevant metadata are included, not accounts,
credentials, sessions or private configuration.

The [computed analysis](evidence/final-analysis-20260927.json) and
[generated LaTeX tables](report-data) contain twenty LaTeX fragments and one
computed JSON analysis:

- Twelve supplied statements, 81 tokens, 55 case-folded forms.
- Full token/category tables, frequencies, observed spelling variation and
  26 language-transition clues.
- The original grammar, two actual transformations, complete FIRST/FOLLOW
  sets, 39 transformed productions and all 47 populated LL(1) table cells.
- Ten accepted originals and two rejections at token six (`n'ais`, `alli`).
- Complete traces for all twelve cases in JSON; full S02/S09/S10 traces in the
  report; seven additional constructed boundary controls.
- Eight executed lexer controls covering internal/dangling joiners, decimals,
  leading separators/signs and underscore fallback.
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

## 12-slide essentials PowerPoint

The [editable PowerPoint](camfranglais-presentation-12-slides.pptx) and
[PDF preview](camfranglais-presentation-12-slides.pdf) contain **exactly 12
slides**, suitable for a roughly ten-minute oral presentation:

1. Project title and group members.
2. Purpose: preserve, explain and review.
3. The five public pages.
4. The input-to-result workflow.
5. Franc Analyzer and its real input screen.
6. Separate vocabulary and grammar verdicts.
7. Collection, Dictionary and synthetic examples.
8. The three application layers and their key files.
9. The lexer and its equivalent DFA.
10. The LL(1) parser and its pushdown control.
11. Controlled results and their limitations.
12. Conclusion, website and questions.

The deck includes the known names/matricules without signing fields, a
matching navy/teal/gold design, ten layout variants and speaker notes on every
slide. Text, cards, flow graphics and the outcome chart are editable;
screenshots, the original architecture illustration and imported formal
automata are images. Slide 3 has clickable navigation cards that lead only
to slides within this twelve-slide deck.

The [concise slide content](presentation/slides-brief.json) contains the exact
titles, explanations, notes and responsible source filenames. Source rails use
repository-relative links: keep the deck in this folder with the checkout
if you want those links to resolve. Standalone copies still display every
filename and retain their speaker notes.

The earlier [100-slide technical reference](camfranglais-presentation-100-slides.pptx),
its [PDF](camfranglais-presentation-100-slides.pdf) and
[full content](presentation/slides.json) are preserved separately; they are
not the concise presentation.

The shared asset collection contains eight real screenshots covering all five
pages, a `kass` dictionary lookup, and mobile Analyzer/Collection views. The
[capture register](presentation/screenshots/captures.json) records their
hashes and dimensions. Capture uses the live app without response mocking or
DOM changes; all non-read API requests are blocked and **no new tests are
submitted**. The concise deck uses selected Analyzer and Dictionary images,
plus a genuine earlier selected-test image reused from the report.
The [visual register](presentation/visuals/provenance.json) distinguishes
crop-only derivatives from original programmatically drawn illustrations.
Illustrations are explanatory artwork, not fieldwork photographs.

Rebuild using the configured Python environment:

```powershell
.\.venv\Scripts\python.exe -m tools.build_presentation --brief
.\.venv\Scripts\python.exe -m tools.build_presentation --brief --check
.\.venv\Scripts\python.exe -m unittest tools.tests.test_presentation
```

The [generator](../tools/build_presentation.py) uses `python-pptx`, Pillow
and the installed Arial/Georgia/Consolas Windows fonts for layout metrics.
It rejects a count other than 12 for the concise edition, missing referenced
files, text that cannot fit above its minimum font size, absent speaker notes
and off-slide objects. Omit `--brief` only to rebuild the 100-slide reference.
The optional `--render` command additionally uses PyMuPDF and local LibreOffice
to render and validate the **actual PPTX**, then publishes the PDF:

```powershell
.\.venv\Scripts\python.exe -m tools.build_presentation --brief --render
```

The verified local renderer is LibreOffice 26.2.6.3, extracted under
`.tools\LibreOffice-26.2.6` without a system-wide installation. Its official
26.2.6 Windows MSI SHA-256 is
`f9877032fd908beb9c0ddf06df4af5c2e85f419c42e14876c4cce5aae5fb2660`.
Rendering never uploads the presentation to a third party. A non-blocking
LibreOffice Python-prefix message may appear; the converter exit, PDF
existence, freshness and all 12 rendered pages are checked independently.
Use `--brief --verify-render` to recheck a current local PDF without regenerating.

The [concise verification record](presentation/verification-brief.json)
records both artifact hashes, editability counts, source-file inventory,
page count, per-text-box fit, image bounds and PDF font embedding. The
[reference verification record](presentation/verification.json) is separate.
The published concise deck has 221 editable text shapes, seven image
placements, one editable chart and 12 speaker-note pages. All 221 rendered
text boxes fit, every image stays within the page and all five PDF font
resources are embedded.
Review images and intermediate files stay under the ignored
`.build\presentation\brief` directory. To intentionally refresh public screenshots,
run the [read-only capture script](../tools/capture_presentation.cjs) after
installing the frontend's declared development dependencies; then review the
new counts and explanatory text before rebuilding.

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

### Compiler automata

The two additional sheets use formal automata notation rather than claiming
to be UML state machines:

- [Lexer DFA](diagrams/automaton-lexer.puml) · [PNG](diagrams/automaton-lexer.png):
  an equivalent finite-state model of the actual regex, with double-circle
  accepting states, non-accepting pending joiner/decimal states and an implicit
  dead state. The implementation uses Python's regex matcher, not a hand-coded
  DFA class. U+02BC follows the Unicode word-character edges; it is not a
  competing pending-joiner transition.
- [Parser pushdown control](diagrams/automaton-parser.puml) ·
  [PNG](diagrams/automaton-parser.png): the saved LL(1) table drives expansion,
  terminal matching and acceptance using a right-top stack. Finite buffered
  lookahead explains the control states; the code advances its input position
  only on a match. Runtime token, trace and stack bounds remain explicit.

The report explains both figures and tests their boundaries against actual
tokenizer outputs and recorded parser transitions. Recognizing a token shape,
approving its vocabulary category and accepting the full grammar are different
decisions. No LR parser or unbounded production implementation is claimed.

## Rebuild and verify

Use the existing VS Code **Build documentation PDFs** task. From the repository
root, the equivalent commands are:

```powershell
.\.venv\Scripts\python.exe -m tools.build_report_evidence --check
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
.\.venv\Scripts\python.exe -m tools.check_documentation
.\.venv\Scripts\python.exe -m unittest tools.tests.test_documentation_checks tools.tests.test_report_evidence compiler.tests.test_yaounde_grammar backend.tests.test_yaounde_corpus
```

When intentionally regenerating evidence after a reviewed compiler/snapshot
change, omit `--check` from the report-evidence command. Review the resulting
data and narrative together before publishing. Generation never reads or writes
the live SQLite database; it uses the committed public snapshot.

The build order is **UML atlas → SRS → SDD → final report**. It uses Java and
PlantUML for PNGs, then the installed `pdflatex` or Tectonic; portable tools may
reside in the ignored `.tools` directory. DOT automata additionally require a
**full Graphviz build with PNG support**; PlantUML's minimal bundled Graphviz
can return text errors despite a successful process exit.

The build automatically selects portable Graphviz 16.1.0 when installed at
`.tools\Graphviz-16.1.0-win64\bin\dot.exe`. The
[CI setup](../.github/workflows/ci.yml) downloads the
[official Windows archive](https://gitlab.com/api/v4/projects/4207231/packages/generic/graphviz-releases/16.1.0/windows_10_cmake_Release_Graphviz-16.1.0-win64.zip),
verifies SHA-256
`733e49626c492242eb8dca30ea627b6ead20710e207998c7933b4909d92d6abc`,
then extracts it under `.tools`. Use the same verified archive for a portable
local setup, or configure an installed PNG-capable Graphviz for PlantUML.
No system-wide install is required by the portable setup.

The build checks the PNG header of every diagram and fails on error text
masquerading as an image. `-SkipDiagrams` is appropriate only when current
PNGs already match unchanged sources and the shared theme. Intermediate files
and logs go to the ignored `.build` directory; PDFs are copied into this folder.

The strict [checker](../tools/check_documentation.py) rejects:

- Missing/obsolete production-class coverage and missing declarations.
- Unused/missing diagrams, duplicate sheets and wrong SDD/atlas page mappings.
- Unbalanced sequence activations or mismatched calls/replies.
- Missing/stale embedded diagram pixels, including both current automata in
  the final report.
- Signature text remaining in the current report, SRS or SDD.
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
errors or clipped image placements. All **33 focused documentation,
report-evidence and corpus grammar/persistence tests** passed on 27 September,
including the seven corpus tests, Unicode/joiner controls and recorded
pushdown-transition checks. Workflow syntax, the PNG guard's positive/negative
controls and the edited Python files' editor diagnostics were also checked
successfully.

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
