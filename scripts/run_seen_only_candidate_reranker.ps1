param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1"
)
$ErrorActionPreference = "Stop"
if (-not $PythonExe) {
    $candidate = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $candidate) { $PythonExe = $candidate } else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/build_seen_only_candidate_reranker.py
if ($LASTEXITCODE -ne 0) { throw "Seen-only reranker failed with exit code $LASTEXITCODE" }
