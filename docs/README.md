# Francanglais Compiler Documentation

This folder contains the Software Requirements Specification (SRS), Software
Design Description (SDD), and PlantUML sources for the Francanglais project.

## Contents

- `srs.tex` — requirements specification.
- `sdd.tex` — architecture and detailed design description.
- `diagrams/*.puml` — editable UML sources.
- `diagrams/*.png` — rendered diagram images included by the SDD.
- `build.ps1` — Windows build script for PlantUML and LaTeX.

## Build

Install Java, PlantUML, and a LaTeX distribution (MiKTeX or TeX Live), then
run from the repository root:

```powershell
.\docs\build.ps1
```

The script renders every `.puml` file to PNG and compiles both documents with
`pdflatex`. It accepts an optional PlantUML jar path:

```powershell
.\docs\build.ps1 -PlantUmlJar C:\tools\plantuml.jar
```

If PlantUML is not installed, download the current jar from
<https://plantuml.com/download> and pass its path to the script.

## Project snapshot and author fields

The source-controlled snapshot contains the CustomTkinter data collector and a
compiled frontend bundle. Local backend/compiler files are ignored or absent
from the Git index, so the documents distinguish verified implementation from
planned integration. Replace the placeholders on the title pages with the
group's names and matricules.

