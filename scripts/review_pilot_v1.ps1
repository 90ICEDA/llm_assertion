$ErrorActionPreference="Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$Python=(Get-Command python -ErrorAction SilentlyContinue).Source
if(-not $Python){$Python=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"}
if(-not(Test-Path -LiteralPath $Python)){throw "Windows Python not found"}
& $Python src/audit_pilot_v1_evidence.py
if($LASTEXITCODE-ne 0){exit $LASTEXITCODE}
Get-Content -Encoding UTF8 outputs/behavioral_preference_pilot_v1/final_report_v1/pilot_v1_final_report.md
