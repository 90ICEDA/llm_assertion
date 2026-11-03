param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$DataRoot = "D:\AssertionForge-main1\rtl_cases_real_scale120",
    [string]$TemporalSummaryJson = "D:\AssertionForge-main1\outputs\scale120_abstracted_summary_inputs\scale120_abstracted_summaries_combined.json",
    [string]$OutputDir = "D:\AssertionForge-main1\outputs\scale120_trace_representation_ablation_data",
    [string[]]$Models = @("GPT", "Claude"),
    [string[]]$Methods = @("spec_rtl_raw_trace", "spec_rtl_naive_summary", "spec_rtl_event_abstraction", "spec_rtl_temporal_relation_abstraction"),
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
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Resolve-PythonExe {
    param(
        [string]$Preferred
    )

    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates = @()
    if ($Preferred) {
        $candidates += $Preferred
    }
    $candidates += @(
        "python",
        "py",
        $bundledPython
    )

    foreach ($candidate in $candidates) {
        if (-not $candidate) {
            continue
        }
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    throw "Unable to locate a usable Python interpreter. Pass -PythonExe explicitly."
}

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
$ResolvedPythonExe = Resolve-PythonExe -Preferred $PythonExe

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

    $cmd = @(
        "src\run_trace_representation_ablation.py",
        "--root", $DataRoot,
        "--output-dir", $OutputDir,
        "--temporal-summary-json", $TemporalSummaryJson,
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
    if ($DryRun) {
        $cmd += "--dry-run"
    }

    Write-Host "=== SCALE120 TRACE REPRESENTATION ABLATION ==="
    Write-Host "python:    $ResolvedPythonExe"
    Write-Host "repo:      $RepoRoot"
    Write-Host "data root: $DataRoot"
    Write-Host "temporal:  $TemporalSummaryJson"
    Write-Host "output:    $OutputDir"
    Write-Host "models:    $($Models -join ', ')"
    Write-Host "methods:   $($Methods -join ', ')"
    Write-Host "shard:     $ShardIndex / $ShardCount"
    if ($HasGPT -and $OpenAIBaseUrl) {
        Write-Host "gpt relay: $OpenAIBaseUrl"
    }
    if ($HasGPT -and $OpenAIModel) {
        Write-Host "gpt model: $OpenAIModel"
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
    if ($DryRun) {
        Write-Host "mode:      dry-run"
    }

    & $ResolvedPythonExe @cmd
}
finally {
    Pop-Location
}
