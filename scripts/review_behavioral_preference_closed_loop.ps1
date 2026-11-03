$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" }
if (-not (Test-Path -LiteralPath $Python)) { throw "Windows Python not found" }
& $Python src/review_behavioral_preference_closed_loop.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Get-Content -Encoding UTF8 outputs/behavioral_preference_closed_loop_final_v1/behavioral_preference_closed_loop_final_report.md
