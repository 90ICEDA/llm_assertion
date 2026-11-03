param(
    [Parameter(Mandatory = $true)][ValidateSet('GPT','Claude','Qwen')][string]$Model
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$userProfilePath = [Environment]::GetFolderPath('UserProfile')
$python = Join-Path $userProfilePath '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw "Bundled Python runtime not found: $python"
}
$root = Join-Path $repo 'rtl_cases_real_scale210_independent_next'
$baseOut = Join-Path $repo "outputs\final46_main_experiment\run\$Model"
$temporal = Join-Path $repo 'outputs\final46_main_experiment\temporal_abstractions.json'
$status = Join-Path $baseOut 'run_status.json'
New-Item -ItemType Directory -Force -Path $baseOut | Out-Null

$env:MULTIMODEL_OPENAI_MODEL = 'gpt-5.4'
$env:MULTIMODEL_OPENAI_BASE_URL = 'https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_CLAUDE_PROVIDER = 'openai_compatible'
$env:MULTIMODEL_CLAUDE_MODEL = 'claude-opus-4-8'
$env:MULTIMODEL_CLAUDE_BASE_URL = 'https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_QWEN_PROVIDER = 'openai_compatible'
$env:MULTIMODEL_QWEN_MODEL = 'qwen/qwen-2.5-72b-instruct'
$env:MULTIMODEL_QWEN_BASE_URL = 'https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_OPENAI_MAX_RETRIES = '8'
$env:MULTIMODEL_CLAUDE_MAX_RETRIES = '8'
$env:MULTIMODEL_QWEN_MAX_RETRIES = '8'
$env:MULTIMODEL_OPENAI_RETRY_BACKOFF_SEC = '10'
$env:MULTIMODEL_CLAUDE_RETRY_BACKOFF_SEC = '10'
$env:MULTIMODEL_QWEN_RETRY_BACKOFF_SEC = '10'
$env:MULTIMODEL_SEED = '20260806'

$started = (Get-Date).ToString('o')
try {
    & $python (Join-Path $repo 'src\run_rtl_context_ablation.py') `
        --root $root --output-dir (Join-Path $baseOut 'context') --all-cases `
        --model $Model `
        --method spec_only --method spec_rtl_full --method spec_rtl_signal_list --method spec_rtl_sliced `
        --candidates-per-cell 4 --resume
    if ($LASTEXITCODE -ne 0) { throw "context runner exited $LASTEXITCODE" }

    & $python (Join-Path $repo 'src\run_trace_representation_ablation.py') `
        --root $root --output-dir (Join-Path $baseOut 'trace') --all-cases `
        --model $Model `
        --method spec_rtl_raw_trace --method spec_rtl_naive_summary `
        --method spec_rtl_event_abstraction --method spec_rtl_temporal_relation_abstraction `
        --temporal-summary-json $temporal --candidates-per-cell 4 --resume
    if ($LASTEXITCODE -ne 0) { throw "trace runner exited $LASTEXITCODE" }

    @{ model = $Model; status = 'complete'; started_at = $started; completed_at = (Get-Date).ToString('o') } |
        ConvertTo-Json | Set-Content -Encoding utf8 $status
} catch {
    @{ model = $Model; status = 'failed'; started_at = $started; failed_at = (Get-Date).ToString('o'); error = $_.Exception.Message } |
        ConvertTo-Json | Set-Content -Encoding utf8 $status
    throw
}
