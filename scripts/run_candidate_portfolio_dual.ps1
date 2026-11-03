param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$RelayUrl = "https://api.highwayapi.ai/openai/chat/completions"
)
$ErrorActionPreference = "Stop"
if (-not $PythonExe) {
    $candidate = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $candidate) { $PythonExe = $candidate } else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
Set-Location -LiteralPath $RepoRoot
$names=@("OPENAI_API_KEY","ANTHROPIC_API_KEY","MULTIMODEL_OPENAI_BASE_URL","MULTIMODEL_OPENAI_MODEL","MULTIMODEL_CLAUDE_PROVIDER","MULTIMODEL_CLAUDE_BASE_URL","MULTIMODEL_CLAUDE_MODEL")
$old=@{}; foreach($name in $names){$old[$name]=[Environment]::GetEnvironmentVariable($name,"Process")}
$secure=Read-Host "Highway API key" -AsSecureString; $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $key=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
  $env:OPENAI_API_KEY=$key; $env:ANTHROPIC_API_KEY=$key
  $env:MULTIMODEL_OPENAI_BASE_URL=$RelayUrl; $env:MULTIMODEL_OPENAI_MODEL="gpt-5.4"
  $env:MULTIMODEL_CLAUDE_PROVIDER="openai_compatible"; $env:MULTIMODEL_CLAUDE_BASE_URL=$RelayUrl; $env:MULTIMODEL_CLAUDE_MODEL="claude-opus-4-8"
  & $PythonExe src/run_trace_representation_ablation.py `
    --root rtl_cases_real_scale120 `
    --output-dir outputs/candidate_portfolio_k4_extension `
    --temporal-summary-json outputs/formal_temporal_abstractions/temporal_abstractions.json `
    --all-cases --model GPT --model Claude `
    --method spec_rtl_raw_trace --method spec_rtl_temporal_relation_abstraction `
    --candidates-per-cell 2 --candidate-index-offset 2 `
    --exclude-candidates-results outputs/formal_compliant_raw_temporal_dual/multi_model_results_raw.csv `
    --resume
  if($LASTEXITCODE -ne 0){throw "Candidate 3-4 generation failed with exit code $LASTEXITCODE"}
  & $PythonExe src/build_candidate_portfolio_report.py
  if($LASTEXITCODE -ne 0){throw "Candidate portfolio report failed with exit code $LASTEXITCODE"}
}
finally {
  if($ptr -ne [IntPtr]::Zero){[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)}; $key=$null
  foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$old[$name],"Process")}
}
