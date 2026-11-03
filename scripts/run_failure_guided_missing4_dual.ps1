param(
  [string]$PythonExe = "",
  [string]$RepoRoot = "D:\AssertionForge-main1",
  [string]$RelayUrl = "https://api.highwayapi.ai/openai/chat/completions"
)
$ErrorActionPreference = "Stop"
if (-not $PythonExe) {
  $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if (Test-Path $bundled) { $PythonExe = $bundled } else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
Set-Location -LiteralPath $RepoRoot
& $PythonExe scripts/materialize_missing_repair_categories.py
if ($LASTEXITCODE -ne 0) { throw "Could not materialize missing-category repair candidates" }

$names = @("OPENAI_API_KEY","ANTHROPIC_API_KEY","MULTIMODEL_OPENAI_BASE_URL","MULTIMODEL_OPENAI_MODEL","MULTIMODEL_CLAUDE_PROVIDER","MULTIMODEL_CLAUDE_BASE_URL","MULTIMODEL_CLAUDE_MODEL")
$old = @{}; foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name,"Process") }
$secure = Read-Host "Highway API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  $env:OPENAI_API_KEY = $key; $env:ANTHROPIC_API_KEY = $key
  $env:MULTIMODEL_OPENAI_BASE_URL = $RelayUrl; $env:MULTIMODEL_OPENAI_MODEL = "gpt-5.4"
  $env:MULTIMODEL_CLAUDE_PROVIDER = "openai_compatible"; $env:MULTIMODEL_CLAUDE_BASE_URL = $RelayUrl; $env:MULTIMODEL_CLAUDE_MODEL = "claude-opus-4-8"
  & $PythonExe src/run_failure_guided_single_repair.py `
    --selected outputs/failure_guided_missing4/selected_candidates_missing4.csv `
    --out-dir outputs/failure_guided_missing4
  if ($LASTEXITCODE -ne 0) { throw "Missing-category one-step repair failed with exit code $LASTEXITCODE" }
}
finally {
  if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
  $key = $null
  foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name,$old[$name],"Process") }
}
