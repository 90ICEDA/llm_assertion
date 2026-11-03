param([string]$PythonExe="",[string]$RepoRoot="D:\AssertionForge-main1")
$ErrorActionPreference="Stop"; if(-not $PythonExe){$p=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe";if(Test-Path $p){$PythonExe=$p}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}}
Set-Location -LiteralPath $RepoRoot; & $PythonExe src/build_dev_locked_score_reranker.py; if($LASTEXITCODE -ne 0){throw "Dev-locked score reranker failed with exit code $LASTEXITCODE"}
