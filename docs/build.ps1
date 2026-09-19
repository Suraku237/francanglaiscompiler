param(
    [string]$PlantUmlJar = ""
)

$ErrorActionPreference = "Stop"
$docs = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $docs
$diagramDir = Join-Path $docs "diagrams"

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    throw "Java is required to render PlantUML diagrams."
}
if (-not (Get-Command pdflatex -ErrorAction SilentlyContinue)) {
    throw "pdflatex is required to compile the documents."
}

if ([string]::IsNullOrWhiteSpace($PlantUmlJar)) {
    $PlantUmlJar = Join-Path $docs "plantuml.jar"
}
if (-not (Test-Path $PlantUmlJar)) {
    throw "PlantUML jar not found at '$PlantUmlJar'. Pass -PlantUmlJar with a valid path."
}

Get-ChildItem $diagramDir -Filter *.puml | ForEach-Object {
    & java -jar $PlantUmlJar -tpng -charset UTF-8 $_.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "PlantUML failed for $($_.Name)."
    }
}

Push-Location $docs
try {
    foreach ($document in @("srs.tex", "sdd.tex")) {
        & pdflatex -interaction=nonstopmode -halt-on-error $document
        if ($LASTEXITCODE -ne 0) {
            throw "LaTeX failed for $document."
        }
        & pdflatex -interaction=nonstopmode -halt-on-error $document
        if ($LASTEXITCODE -ne 0) {
            throw "Second LaTeX pass failed for $document."
        }
    }
}
finally {
    Pop-Location
}

Write-Host "Built docs\srs.pdf and docs\sdd.pdf"
