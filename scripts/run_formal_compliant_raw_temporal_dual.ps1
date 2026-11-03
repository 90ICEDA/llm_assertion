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
    Set-Location -LiteralPath $RepoRoot
    & $PythonExe src/run_trace_representation_ablation.py `
        --root rtl_cases_real_scale120 `
        --output-dir outputs/formal_compliant_raw_temporal_dual `
        --temporal-summary-json outputs/formal_temporal_abstractions/temporal_abstractions.json `
        --all-cases --model GPT --model Claude `
        --method spec_rtl_raw_trace `
        --method spec_rtl_temporal_relation_abstraction `
        --candidates-per-cell 2 --resume
    if ($LASTEXITCODE -ne 0) { throw "Formal-compliant raw/temporal run failed with exit code $LASTEXITCODE" }
}
finally {
    if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    $key = $null
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $old[$name], "Process") }
}
