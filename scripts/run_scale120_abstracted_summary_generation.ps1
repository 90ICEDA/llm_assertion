param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$DataRoot = "D:\AssertionForge-main1\rtl_cases_real_scale120",
    [string]$OutputDir = "D:\AssertionForge-main1\outputs\scale120_abstracted_summary_inputs",
    [string]$SummaryModel = "GPT",
    [double]$Temperature = 0.2,
    [int]$ShardIndex = 0,
    [int]$ShardCount = 1,
    [string]$OpenAIBaseUrl = "",
    [string]$OpenAIModel = "",
    [string]$OpenAIAuthScheme = "",
    [string]$OpenAIExtraHeadersJson = "",
    [int]$OpenAIMaxRetries = 4,
    [double]$OpenAIRetryBackoffSec = 5.0,
    [string]$ClaudeProvider = "",
    [string]$ClaudeBaseUrl = "",
    [string]$ClaudeModel = "",
    [string]$ClaudeAuthMode = "",
    [string]$ClaudeAuthScheme = "",
    [string]$ClaudeApiVersion = "",
    [string]$ClaudeExtraHeadersJson = "",
    [int]$ClaudeMaxRetries = 4,
    [double]$ClaudeRetryBackoffSec = 5.0,
    [string]$QwenProvider = "",
    [string]$QwenBaseUrl = "",
    [string]$QwenModel = "",
    [string]$QwenAuthScheme = "",
    [string]$QwenExtraHeadersJson = "",
    [int]$QwenMaxRetries = 4,
    [double]$QwenRetryBackoffSec = 5.0,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Push-Location $RepoRoot
try {
    if ($OpenAIBaseUrl) {
        $env:MULTIMODEL_OPENAI_BASE_URL = $OpenAIBaseUrl
    }
    if ($OpenAIModel) {
        $env:MULTIMODEL_OPENAI_MODEL = $OpenAIModel
    }
    if ($OpenAIAuthScheme) {
        $env:MULTIMODEL_OPENAI_AUTH_SCHEME = $OpenAIAuthScheme
    }
    if ($OpenAIExtraHeadersJson) {
        $env:MULTIMODEL_OPENAI_EXTRA_HEADERS_JSON = $OpenAIExtraHeadersJson
    }
    $env:MULTIMODEL_OPENAI_MAX_RETRIES = [string]$OpenAIMaxRetries
    $env:MULTIMODEL_OPENAI_RETRY_BACKOFF_SEC = [string]$OpenAIRetryBackoffSec

    if ($ClaudeProvider) {
        $env:MULTIMODEL_CLAUDE_PROVIDER = $ClaudeProvider
    }
    if ($ClaudeBaseUrl) {
        $env:MULTIMODEL_CLAUDE_BASE_URL = $ClaudeBaseUrl
    }
    if ($ClaudeModel) {
        $env:MULTIMODEL_CLAUDE_MODEL = $ClaudeModel
    }
    if ($ClaudeAuthMode) {
        $env:MULTIMODEL_CLAUDE_AUTH_MODE = $ClaudeAuthMode
    }
    if ($ClaudeAuthScheme) {
        $env:MULTIMODEL_CLAUDE_AUTH_SCHEME = $ClaudeAuthScheme
    }
    if ($ClaudeApiVersion) {
        $env:MULTIMODEL_CLAUDE_API_VERSION = $ClaudeApiVersion
    }
    if ($ClaudeExtraHeadersJson) {
        $env:MULTIMODEL_CLAUDE_EXTRA_HEADERS_JSON = $ClaudeExtraHeadersJson
    }
    $env:MULTIMODEL_CLAUDE_MAX_RETRIES = [string]$ClaudeMaxRetries
    $env:MULTIMODEL_CLAUDE_RETRY_BACKOFF_SEC = [string]$ClaudeRetryBackoffSec

    if ($QwenProvider) {
        $env:MULTIMODEL_QWEN_PROVIDER = $QwenProvider
    }
    if ($QwenBaseUrl) {
        $env:MULTIMODEL_QWEN_BASE_URL = $QwenBaseUrl
    }
    if ($QwenModel) {
        $env:MULTIMODEL_QWEN_MODEL = $QwenModel
    }
    if ($QwenAuthScheme) {
        $env:MULTIMODEL_QWEN_AUTH_SCHEME = $QwenAuthScheme
    }
    if ($QwenExtraHeadersJson) {
        $env:MULTIMODEL_QWEN_EXTRA_HEADERS_JSON = $QwenExtraHeadersJson
    }
    $env:MULTIMODEL_QWEN_MAX_RETRIES = [string]$QwenMaxRetries
    $env:MULTIMODEL_QWEN_RETRY_BACKOFF_SEC = [string]$QwenRetryBackoffSec

    $cmd = @(
        "src\generate_scale120_abstracted_summaries.py",
        "--root", $DataRoot,
        "--output-dir", $OutputDir,
        "--all-cases",
        "--summary-model", $SummaryModel,
        "--temperature", $Temperature,
        "--shard-index", $ShardIndex,
        "--shard-count", $ShardCount
    )
    if ($DryRun) {
        $cmd += "--dry-run"
    }

    Write-Host "=== SCALE120 ABSTRACTED SUMMARY GENERATION ==="
    Write-Host "python:    $PythonExe"
    Write-Host "repo:      $RepoRoot"
    Write-Host "data root: $DataRoot"
    Write-Host "output:    $OutputDir"
    Write-Host "model:     $SummaryModel"
    Write-Host "temp:      $Temperature"
    Write-Host "shard:     $ShardIndex / $ShardCount"
    if ($DryRun) {
        Write-Host "mode:      dry-run"
    }

    & $PythonExe @cmd
}
finally {
    Pop-Location
}
