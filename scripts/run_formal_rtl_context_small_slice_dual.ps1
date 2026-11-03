param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$OutputDir = "D:\AssertionForge-main1\outputs\scale120_rtl_context_small_slice_v2\formal",
    [string]$RelayUrl = "https://api.highwayapi.ai/openai/chat/completions",
    [string]$GptModel = "gpt-5.4",
    [string]$ClaudeModel = "claude-opus-4-8",
    [int]$CandidatesPerCell = 2,
    [int]$ShardIndex = 0,
    [int]$ShardCount = 1
)

$ErrorActionPreference = "Stop"

if (-not $PythonExe) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython) {
        $PythonExe = $bundledPython
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $PythonExe = $pythonCommand.Source }
    }
}
if (-not $PythonExe -or -not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python not found. Pass -PythonExe with a Windows Python path."
}

$old = @{}
$names = @(
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "MULTIMODEL_OPENAI_BASE_URL",
    "MULTIMODEL_OPENAI_MODEL", "MULTIMODEL_CLAUDE_PROVIDER",
    "MULTIMODEL_CLAUDE_BASE_URL", "MULTIMODEL_CLAUDE_MODEL"
)
foreach ($name in $names) { $old[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }

$secure = Read-Host "Highway API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    $env:OPENAI_API_KEY = $key
    $env:ANTHROPIC_API_KEY = $key
    $env:MULTIMODEL_OPENAI_BASE_URL = $RelayUrl
    $env:MULTIMODEL_OPENAI_MODEL = $GptModel
    $env:MULTIMODEL_CLAUDE_PROVIDER = "openai_compatible"
    $env:MULTIMODEL_CLAUDE_BASE_URL = $RelayUrl
    $env:MULTIMODEL_CLAUDE_MODEL = $ClaudeModel

    Set-Location -LiteralPath $RepoRoot
    & $PythonExe src/run_rtl_context_ablation.py `
        --root rtl_cases_real_scale120 `
        --output-dir $OutputDir `
        --all-cases `
        --model GPT --model Claude `
        --method spec_rtl_signal_list_small_slice `
        --candidates-per-cell $CandidatesPerCell `
        --shard-index $ShardIndex --shard-count $ShardCount `
        --resume
    if ($LASTEXITCODE -ne 0) { throw "Formal RTL-context run failed with exit code $LASTEXITCODE" }
}
finally {
    if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    $key = $null
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $old[$name], "Process") }
}
