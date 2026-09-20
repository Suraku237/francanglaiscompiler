param(
    [string]$PlantUmlJar = "",
    [switch]$SkipDiagrams
)

$ErrorActionPreference = "Stop"
$docs = Split-Path -Parent $MyInvocation.MyCommand.Path
$diagramDir = Join-Path $docs "diagrams"
$buildDir = Join-Path $docs ".build"
$pdflatex = Get-Command pdflatex -ErrorAction SilentlyContinue
$tectonic = Get-Command tectonic -ErrorAction SilentlyContinue
$localTectonic = Join-Path $docs ".tools\tectonic.exe"

if ($pdflatex) {
    $compiler = $pdflatex.Source
    $engine = "pdflatex"
}
elseif ($tectonic) {
    $compiler = $tectonic.Source
    $engine = "tectonic"
}
elseif (Test-Path -LiteralPath $localTectonic -PathType Leaf) {
    $compiler = $localTectonic
    $engine = "tectonic"
}
else {
    throw "Install pdflatex or Tectonic, or place portable tectonic.exe in docs\.tools."
}

$diagrams = @(Get-ChildItem -LiteralPath $diagramDir -Filter *.puml -File)
if ($SkipDiagrams) {
    Write-Host "Using existing diagram PNGs. Omit -SkipDiagrams after changing PlantUML sources."
    foreach ($diagram in $diagrams) {
        $image = [System.IO.Path]::ChangeExtension($diagram.FullName, ".png")
        if (-not (Test-Path -LiteralPath $image -PathType Leaf)) {
            throw "Missing diagram image '$image'. Render the PlantUML sources first."
        }
    }
}
else {
    if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
        throw "Java is required to render PlantUML diagrams, or use -SkipDiagrams with existing PNGs."
    }
    if ([string]::IsNullOrWhiteSpace($PlantUmlJar)) {
        $PlantUmlJar = Join-Path $docs "plantuml.jar"
    }
    if (-not (Test-Path -LiteralPath $PlantUmlJar -PathType Leaf)) {
        throw "PlantUML jar not found at '$PlantUmlJar'. Pass -PlantUmlJar, or use -SkipDiagrams with existing PNGs."
    }
    foreach ($diagram in $diagrams) {
        # Hosted architecture views exceed PlantUML's default 4096-pixel canvas.
        & java -DPLANTUML_LIMIT_SIZE=8192 -jar $PlantUmlJar -tpng -charset UTF-8 $diagram.FullName
        if ($LASTEXITCODE -ne 0) {
            throw "PlantUML failed for $($diagram.Name)."
        }
    }
}

New-Item -ItemType Directory -Path $buildDir -Force | Out-Null
Write-Host "Compiling documentation with $engine ($compiler)"
Push-Location $docs
try {
    foreach ($document in @("uml-atlas.tex", "srs.tex", "sdd.tex")) {
        if ($engine -eq "pdflatex") {
            foreach ($pass in 1..2) {
                & $compiler -interaction=nonstopmode -halt-on-error -file-line-error -no-shell-escape -output-directory $buildDir $document
                if ($LASTEXITCODE -ne 0) {
                    throw "LaTeX pass $pass failed for $document. See docs\.build for logs."
                }
            }
        }
        else {
            & $compiler --keep-logs --outdir $buildDir $document
            if ($LASTEXITCODE -ne 0) {
                throw "Tectonic failed for $document. See docs\.build for logs."
            }
        }
        $pdfName = [System.IO.Path]::ChangeExtension($document, ".pdf")
        $pdf = Get-Item -LiteralPath (Join-Path $buildDir $pdfName)
        if ($pdf.Length -eq 0) {
            throw "The compiler produced an empty PDF for $document."
        }
        Copy-Item -LiteralPath $pdf.FullName -Destination (Join-Path $docs $pdfName) -Force
    }
}
finally {
    Pop-Location
}

Write-Host "Built docs\srs.pdf, docs\sdd.pdf and the full-size docs\uml-atlas.pdf"
