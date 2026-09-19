# Francanglais Compiler Documentation

Version 1.2 describes the current desktop collector, editable React frontend,
FastAPI API, local lexer/parser, imports, reviewed retrieval and coursework
workspace. It replaces the obsolete desktop-only architecture.

## Documents

- [SRS PDF](srs.pdf) and [LaTeX source](srs.tex): 36 numbered functional
  requirements (including one deferred predictor), 16 non-functional
  requirements, 23 user stories, 23 backlog items and four proposed two-week
  sprint backlogs with 30 individually evidence-labelled tasks.
- [SDD PDF](sdd.pdf) and [LaTeX source](sdd.tex): architecture, data/transaction
  boundaries, the twenty application API method/path combinations, failure
  contracts, every diagram's explanation and requirement/source trace.
- [Full-size UML atlas](uml-atlas.pdf) and [atlas source](uml-atlas.tex): the same
  28 diagram sheets included at the end of the SDD, without the prose.
- [Editable PlantUML and PNGs](diagrams): nine class views, thirteen sequences,
  two state models, one activity, one use case, one component view and one
  deployment view.
- [Class-coverage inventory](diagrams/class-coverage.json): all **47** authored
  production classes: 45 Python `ClassDef` declarations, the runtime `Token`
  namedtuple and frontend `ApiError`. Test helpers, maintenance tools, external
  libraries and erased TypeScript interfaces are excluded.
- [Measured desktop performance](evidence/collector-benchmark.json): raw
  timings, machine/runtime and collector source hashes.
- [Final verification record](evidence/verification.json): recorded checks,
  stage outcomes, integration boundaries and remaining manual gates.

The SDD uses A4 explanatory pages followed by large-format diagram sheets.
Diagram labels remain approximately nine points at actual size; complex
views are not squeezed into unreadable A4 figures. Use PDF zoom, actual-size
printing or tiled printing for the large sheets. The separate coursework
report still has its own 25-30-page requirement; the SRS/SDD are not that report.

## Verified software versus human acceptance

| Check | Current recorded result | Boundary |
|---|---|---|
| Python | **252 tests passed** | Includes 56 desktop and 33 maintenance/checker tests; isolated fixtures and mocked provider/device failures. |
| Frontend components | **77 tests passed** | Eight component/helper test files. |
| Browser workflows | **18 tests passed** | Desktop and mobile Chromium; controlled API fixtures, no real corpus/provider/device access. |
| Types and production assets | **Passed** | Application and test TypeScript configurations; production bundle rebuilt. |
| WAV I/O | **Passed** | Silent mono 44,100 Hz, 4,410 frames; codec/file round-trip, not microphone or speaker certification. |
| Recovery and measurement methodology | **21 tests passed** | Sixteen snapshot/restore and five benchmark-method tests, also included in the Python total. |
| Real GUI timing | **Passed on measured machine** | Search p95 53.31 ms; Stats p95 606.01 ms; 1,000 ms limit, 1,000 synthetic 500-character rows, one warm-up and 20 runs each. |
| Documentation | Local render/build/check | 47 classes, 28 diagrams, 13 balanced synchronous sequence views; source/atlas mapping, PDF pixels, layout and references checked by the command below. |
| CI | Configured and locally linted | No remote GitHub Actions result is asserted. |

The measured machine has approximately **31.8 GiB RAM**. This does **not**
certify the original SRS reference machine with 8 GB RAM/local SSD, nor was
that requirement silently relaxed.

An earlier intermittent Windows storage-test failure did not recur in 25
targeted retries or subsequent clean complete runs. Its underlying cause was
not proven, and no speculative production retry was introduced.

The first author name/matricule already entered in the old SDD is preserved
in both documents. The other two member rows remain blank. All contributions,
genuine transcriptions, permission, reviewed meanings, corpus-grounded grammar
rationale/evaluation, genuine screenshots, final report/slides and rehearsal
remain human inputs. Physical audio, real mobile/assistive-technology use,
authorized live-provider trials and reference-machine acceptance remain manual
gates. A trained unseen-word predictor remains deferred.

The four sprint allocations retain the original **67 selected story points /
106 estimated task hours**, plus the deferred 8-point predictor. They are a
proposal, not historical velocity or retrospectively completed sprints.
Every task distinguishes current software evidence from open human gates.

## UML conventions

- Classes show selected real fields/methods. Generalization points toward the
  superclass. Associations carry cardinalities; dependencies and inheritance
  do not.
- Nested/shared DTO values use associations, not unjustified composition.
  Module/function/hook abstractions and external types are clearly marked.
- Every shown synchronous call, including self-calls, opens an activation and
  has a matching reply ending it. Actors/callback senders also have execution
  spans. The checker enforces this document's convention.
- Exclusive decisions, optional fragments, retry states and extension-arrow
  directions are explained in the SDD. Saved/approved, preview/save,
  analysis/persistence and software/research completion remain separate.
- Sources are rendered locally; project code is not sent to an online UML
  rendering service.

## Rebuild and verify

With Java and the local portable tools already available, run from the
repository root:

```powershell
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
if ($LASTEXITCODE -ne 0) { throw "Documentation build failed." }
.\.venv\Scripts\python.exe -m tools.check_documentation
if ($LASTEXITCODE -ne 0) { throw "Documentation verification failed." }
```

The script renders **every** PlantUML source, builds the atlas first, then
compiles/publishes the SRS and SDD. It prefers `pdflatex`, otherwise Tectonic,
and detects a portable [Tectonic](https://tectonic-typesetting.github.io/)
installation at `docs\.tools\tectonic.exe`. The first compilation can download
standard TeX packages; rendering and compilation remain local. Intermediate
files/logs are in ignored [`.build`](.build); tools are in ignored
[`.tools`](.tools).

For a source-unchanged PDF-only rebuild:

```powershell
.\docs\build.ps1 -SkipDiagrams
```

Do not use `-SkipDiagrams` after changing PlantUML or the shared theme.
The checker inventories source classes, validates balanced synchronous
communications, checks every SDD source/sheet mapping, verifies the embedded
image pixels, and rejects unresolved references or layout warnings.

The [root README](../README.md) documents application setup, automated tests,
benchmarking, recovery and the full fieldwork checklist. The
[CI workflow](../.github/workflows/ci.yml) performs fresh builds rather than
assuming that checked-in PDFs are current.
