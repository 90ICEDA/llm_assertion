param([string]$PythonExe="", [string]$RepoRoot="D:\AssertionForge-main1")
$ErrorActionPreference="Stop"
if(-not $PythonExe){$p=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"; if(Test-Path $p){$PythonExe=$p}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}}
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/compare_seen_only_reranker_policies.py
if($LASTEXITCODE -ne 0){throw "Reranker policy comparison failed with exit code $LASTEXITCODE"}
