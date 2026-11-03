param(
  [ValidateSet('Init','Generate','BuildPairs')][string]$Stage='Init',
  [string]$EvidenceJsonl='',
  [int]$Limit=0,
  [string]$BaseUrl='https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
  [string]$Model='qwen3-8b',
  [string]$PythonExe=''
)
$ErrorActionPreference='Stop'
$RepoRoot=Split-Path -Parent $PSScriptRoot
if(-not $PythonExe){
  $Bundled=Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
  if(Test-Path -LiteralPath $Bundled){$PythonExe=$Bundled}else{$PythonExe=(Get-Command python -ErrorAction Stop).Source}
}
if($Stage -eq 'Init'){
  & $PythonExe (Join-Path $RepoRoot 'src\behavioral_preference_pilot.py') init
}elseif($Stage -eq 'Generate'){
  & $PythonExe (Join-Path $RepoRoot 'src\behavioral_preference_pilot.py') generate --limit $Limit --base-url $BaseUrl --model $Model
}else{
  if(-not $EvidenceJsonl){throw 'BuildPairs requires -EvidenceJsonl'}
  & $PythonExe (Join-Path $RepoRoot 'src\behavioral_preference_pilot.py') build-pairs --evidence $EvidenceJsonl
}
if($LASTEXITCODE -ne 0){throw "Pilot stage failed with exit code $LASTEXITCODE"}
