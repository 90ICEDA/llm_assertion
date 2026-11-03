param([string]$PythonExe="",[string]$RepoRoot="D:\AssertionForge-main1")
$ErrorActionPreference="Stop"
if(-not $PythonExe){$p=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe";if(Test-Path $p){$PythonExe=$p}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}}
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/build_group_heldout_splits.py
if($LASTEXITCODE -ne 0){throw "Split construction failed"}
& $PythonExe src/check_group_split_leakage.py --split-dir outputs/formal_group_heldout_splits_v1
if($LASTEXITCODE -ne 0){throw "Leakage detected; split rejected"}
