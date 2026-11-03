param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$DataRoot = "D:\AssertionForge-main1\rtl_cases_real_scale120",
    [string]$OutputDir = "D:\AssertionForge-main1\outputs\scale120_full_model_eval_data",
    [string]$SelectedCasesJson = "",
    [string[]]$Models = @("GPT"),
    [string[]]$Methods = @("spec_plus_rtl", "spec_rtl_raw_trace", "spec_rtl_trace_summary"),
    [int]$CandidatesPerCell = 2,
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

function Expand-CommaSeparatedList {
    param(
        [string[]]$Items
    )

    $expanded = @()
    foreach ($item in $Items) {
        if ($null -eq $item) {
            continue
        }
        foreach ($piece in ($item -split ",")) {
            $trimmed = $piece.Trim()
            if ($trimmed) {
                $expanded += $trimmed
            }
        }
    }
    return $expanded
}

$Models = Expand-CommaSeparatedList -Items $Models
$Methods = Expand-CommaSeparatedList -Items $Methods
$HasGPT = $Models -contains "GPT"
$HasClaude = $Models -contains "Claude"
$HasQwen = $Models -contains "Qwen"

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
        "src\run_multi_model_small_eval.py",
        "--root", $DataRoot,
        "--output-dir", $OutputDir,
        "--all-cases",
        "--candidates-per-cell", $CandidatesPerCell,
        "--shard-index", $ShardIndex,
        "--shard-count", $ShardCount
    )

    foreach ($model in $Models) {
        $cmd += @("--model", $model)
    }
    foreach ($method in $Methods) {
        $cmd += @("--method", $method)
    }
    if ($SelectedCasesJson) {
        $cmd += @("--selected-cases-json", $SelectedCasesJson)
    }
    if ($DryRun) {
        $cmd += "--dry-run"
    }

    Write-Host "=== SCALE120 FULL MODEL EVAL ==="
    Write-Host "python:    $PythonExe"
    Write-Host "repo:      $RepoRoot"
    Write-Host "data root: $DataRoot"
    Write-Host "output:    $OutputDir"
    if ($SelectedCasesJson) {
        Write-Host "abs json:  $SelectedCasesJson"
    }
    Write-Host "models:    $($Models -join ', ')"
    Write-Host "methods:   $($Methods -join ', ')"
    Write-Host "shard:     $ShardIndex / $ShardCount"
    if ($HasGPT -and $OpenAIBaseUrl) {
        Write-Host "relay:     $OpenAIBaseUrl"
    }
    if ($HasGPT -and $OpenAIModel) {
        Write-Host "model id:  $OpenAIModel"
    }
    if ($HasGPT) {
        Write-Host "gpt retries: $OpenAIMaxRetries"
        Write-Host "gpt backoff: $OpenAIRetryBackoffSec s"
    }
    if ($HasClaude -and $ClaudeProvider) {
        Write-Host "claude provider: $ClaudeProvider"
    }
    if ($HasClaude -and $ClaudeBaseUrl) {
        Write-Host "claude relay:    $ClaudeBaseUrl"
    }
    if ($HasClaude -and $ClaudeModel) {
        Write-Host "claude model:    $ClaudeModel"
    }
    if ($HasClaude -and $ClaudeAuthMode) {
        Write-Host "claude auth:     $ClaudeAuthMode"
    }
    if ($HasClaude) {
        Write-Host "claude retries: $ClaudeMaxRetries"
        Write-Host "claude backoff: $ClaudeRetryBackoffSec s"
    }
    if ($HasQwen -and $QwenProvider) {
        Write-Host "qwen provider:   $QwenProvider"
    }
    if ($HasQwen -and $QwenBaseUrl) {
        Write-Host "qwen relay:      $QwenBaseUrl"
    }
    if ($HasQwen -and $QwenModel) {
        Write-Host "qwen model:      $QwenModel"
    }
    if ($HasQwen) {
        Write-Host "qwen retries:    $QwenMaxRetries"
        Write-Host "qwen backoff:    $QwenRetryBackoffSec s"
    }
    if ($DryRun) {
        Write-Host "mode:      dry-run"
    }

    & $PythonExe @cmd
}
finally {
    Pop-Location
}
