# Francanglais Compiler Documentation

This folder contains the Software Requirements Specification (SRS), Software
Design Description (SDD), and PlantUML sources for the Francanglais project.

## Contents

- `srs.tex` — requirements specification.
- `sdd.tex` — architecture and detailed design description.
- `diagrams/*.puml` — editable UML sources.
- `diagrams/*.png` — rendered diagram images included by the SDD.
- `diagrams/theme.iuml` — shared local PlantUML styling.
- `build.ps1` — Windows build script for PlantUML and LaTeX.

## Requirements and delivery planning

The SRS contains 20 functional requirements, 12 non-functional requirements,
16 acceptance-oriented user stories, and a prioritized 16-item product backlog.
It distinguishes source-supported behavior (B), proposed targets (T), and
deferred scope (D).

The four proposed two-week sprint backlogs contain concrete tasks, dependency
links, suggested member leads, review gates and estimates. The selected scope
is 67 story points / 106 task hours; the 8-point predictor is deferred. These
are planning estimates, not historical sprint completion or measured velocity.
Member names and matricules remain placeholders.

## Class and sequence diagram conventions

- The class diagram includes every application-defined class in the available
  source (`App` and `Recorder`), selected methods, inheritance, ownership, and
  association multiplicities (`1`, `0..1`, and `0..*`).
- Helper modules and logical CSV/audio records are explicitly labelled; they
  are not presented as implemented Python model classes. Dashed dependencies
  and inheritance arrows have no multiplicities.
- Seven sequence diagrams cover save/attachment, search/selection, editing,
  confirmed deletion, recording, playback/fallback and statistics. Each shown
  synchronous call has an activation and matching return, including self-calls.
- Every one of the 13 UML diagrams has an SDD explanation of purpose, reading
  order, branches/relationships, side effects, limitations and requirement
  traceability. Compiler components/deployment options remain labelled proposed.
- Existing use-case extension directions, save-time activity validation and
  the selected-entry state transitions reflect the available collector source.
- The PNGs are rendered locally from the adjacent PlantUML sources. Project
  sources do not need to be sent to an online diagram-rendering service.

## Build

Install Java, PlantUML, and a LaTeX distribution (MiKTeX or TeX Live), then
run from the repository root:

```powershell
.\docs\build.ps1
```

The script renders every `.puml` file to PNG and compiles both documents.
It uses `pdflatex` when available, otherwise Tectonic. It accepts an optional
PlantUML jar path:

```powershell
.\docs\build.ps1 -PlantUmlJar C:\tools\plantuml.jar
```

If PlantUML is not installed, download the current jar from
<https://plantuml.com/download> and pass its path to the script.
The local renderer in this workspace can be used for a full rebuild with:

```powershell
.\docs\build.ps1 -PlantUmlJar .\docs\.tools\plantuml.jar
```

### Build PDFs using the existing diagrams

The checked-in PNGs can be used without installing Java or PlantUML:

```powershell
.\docs\build.ps1 -SkipDiagrams
```

Install a LaTeX distribution or [Tectonic](https://tectonic-typesetting.github.io/).
For a portable Windows installation, extract the official Windows Tectonic
release into `docs\.tools` so that `docs\.tools\tectonic.exe` exists. The build
script detects it without changing the system `PATH`. Tectonic downloads
required TeX packages on its first run; document compilation happens locally.

The generated documents are `docs\srs.pdf` and `docs\sdd.pdf`. Intermediate
files and compiler logs are kept in `docs\.build`; this directory and the
local tool directory are ignored by Git. Tectonic automatically reruns LaTeX
to resolve the table of contents. The `pdflatex` path runs two passes.

Use the VS Code **Build documentation PDFs** task for the PDF-only build in
this workspace. After editing a PlantUML source, regenerate its PNG using the
full build command rather than `-SkipDiagrams`.

## Project snapshot and author fields

The source-controlled snapshot contains the CustomTkinter data collector and a
compiled frontend bundle. Local backend/compiler files are ignored or absent
from the Git index, so the documents distinguish verified implementation from
planned integration. Replace the placeholders on the title pages with the
group's names and matricules.
