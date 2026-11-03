param([string]$PythonExe="",[string]$RepoRoot="D:\AssertionForge-main1")
$ErrorActionPreference="Stop";if(-not $PythonExe){$p=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe";if(Test-Path $p){$PythonExe=$p}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}}
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/evaluate_overfit20_multiholdout.py --candidates outputs/overfit_bait20_selected_candidates.csv
if($LASTEXITCODE -ne 0){throw "Overfit20 multi-heldout candidate evaluation failed with exit code $LASTEXITCODE"}
