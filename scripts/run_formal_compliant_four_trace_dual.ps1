param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$RelayUrl = "https://api.highwayapi.ai/openai/chat/completions",
    [string]$GptModel = "gpt-5.4",
    [string]$ClaudeModel = "claude-opus-4-8"
)
$ErrorActionPreference = "Stop"
if (-not $PythonExe) {
    $candidate = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $candidate) { $PythonExe = $candidate }
    else { $PythonExe = (Get-Command python -ErrorAction Stop).Source }
}
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/build_scale120_four_trace_representations.py
if ($LASTEXITCODE -ne 0) { throw "Four-representation contract build failed" }
& $PythonExe src/assemble_reusable_formal_four_trace_results.py
if ($LASTEXITCODE -ne 0) { throw "Safe arm-reuse assembly failed" }
$names = @("OPENAI_API_KEY","ANTHROPIC_API_KEY","MULTIMODEL_OPENAI_BASE_URL","MULTIMODEL_OPENAI_MODEL","MULTIMODEL_CLAUDE_PROVIDER","MULTIMODEL_CLAUDE_BASE_URL","MULTIMODEL_CLAUDE_MODEL")
$old = @{}; foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
$secure = Read-Host "Highway API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:OPENAI_API_KEY = $key; $env:ANTHROPIC_API_KEY = $key
    $env:MULTIMODEL_OPENAI_BASE_URL = $RelayUrl; $env:MULTIMODEL_OPENAI_MODEL = $GptModel
    $env:MULTIMODEL_CLAUDE_PROVIDER = "openai_compatible"
    $env:MULTIMODEL_CLAUDE_BASE_URL = $RelayUrl; $env:MULTIMODEL_CLAUDE_MODEL = $ClaudeModel
    & $PythonExe src/run_trace_representation_ablation.py `
        --root rtl_cases_real_scale120 `
        --output-dir outputs/formal_compliant_four_trace_dual `
        --temporal-summary-json outputs/formal_temporal_abstractions/temporal_abstractions.json `
        --all-cases --model GPT --model Claude `
        --method spec_rtl_raw_trace --method spec_rtl_naive_summary `
        --method spec_rtl_event_abstraction --method spec_rtl_temporal_relation_abstraction `
        --candidates-per-cell 2 --resume
    if ($LASTEXITCODE -ne 0) { throw "Formal compliant four-trace run failed with exit code $LASTEXITCODE" }
    & $PythonExe src/freeze_trace_representation_reports.py `
        --data-dir outputs/formal_compliant_four_trace_dual `
        --contract-audit outputs/formal_four_trace_representations/contract_audit_summary.json `
        --representation-artifact outputs/formal_four_trace_representations/trace_representations.json `
        --k 2 --repetitions 10000 --seed 20260721
    if ($LASTEXITCODE -ne 0) { throw "Formal report regeneration/freeze failed with exit code $LASTEXITCODE" }
}
finally {
    if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    $key = $null
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $old[$name], "Process") }
}
