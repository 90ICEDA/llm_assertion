param([string]$PythonExe="",[string]$RepoRoot="D:\AssertionForge-main1")
$ErrorActionPreference="Stop";if(-not $PythonExe){$p=Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe";if(Test-Path $p){$PythonExe=$p}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}};Set-Location -LiteralPath $RepoRoot
& $PythonExe src/benchmark_candidate_validation_time.py --resume
if($LASTEXITCODE-ne 0){throw "Validation timing replay failed"}
& $PythonExe src/build_candidate_count_cost_experiment.py
if($LASTEXITCODE-ne 0){throw "Candidate-count report rebuild failed"}
