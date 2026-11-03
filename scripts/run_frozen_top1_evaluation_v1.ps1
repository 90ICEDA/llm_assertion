$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Python = $null
$SystemPython = Get-Command python -ErrorAction SilentlyContinue
if ($SystemPython) {
    $Python = $SystemPython.Source
} else {
    $BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $BundledPython) {
        $Python = $BundledPython
    }
}
if (-not $Python) {
    throw "No Windows Python interpreter found. Install Python or run through a Codex workspace runtime."
}

& $Python src/evaluate_frozen_top1_v1.py --preflight-only
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $Python src/evaluate_frozen_top1_v1.py --resume
exit $LASTEXITCODE
