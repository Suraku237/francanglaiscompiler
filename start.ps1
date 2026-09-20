param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Build,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Create .venv with Python 3.11+ and install requirements.txt before starting Mboa."
}

$arguments = @("-m", "tools.run_app", "--host", $HostAddress, "--port", "$Port")
if ($Build) { $arguments += "--build" }
if ($Reload) { $arguments += "--reload" }

Push-Location $PSScriptRoot
try {
    & $python @arguments
    $result = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $result
