param(
    [string]$PythonExe = "python",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$DataRoot = "D:\AssertionForge-main1\rtl_cases_real_scale120",
    [string]$OutputDir = "D:\AssertionForge-main1\outputs\scale120_full_model_eval_data",
    [string]$SummaryInputDir = "D:\AssertionForge-main1\outputs\scale120_abstracted_summary_inputs",
    [string]$SummaryJson = "",
    [string[]]$Models = @("GPT"),
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
    [switch]$SkipMerge,
    [switch]$SkipRebuild,
    [switch]$SkipMainResults,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $SummaryJson) {
    $SummaryJson = Join-Path $SummaryInputDir "scale120_abstracted_summaries_combined.json"
}

Push-Location $RepoRoot
try {
    if (-not $SkipMerge) {
        & $PythonExe "src\merge_scale120_abstracted_summaries.py" `
            --input-dir $SummaryInputDir `
            --output-json $SummaryJson `
            --cases-root $DataRoot
    }

    $fullEvalArgs = @(
        "-ExecutionPolicy", "Bypass",
        "-File", (Join-Path $RepoRoot "scripts\run_scale120_full_model_eval.ps1"),
        "-PythonExe", $PythonExe,
        "-RepoRoot", $RepoRoot,
        "-DataRoot", $DataRoot,
        "-OutputDir", $OutputDir,
        "-SelectedCasesJson", $SummaryJson,
        "-CandidatesPerCell", $CandidatesPerCell,
        "-ShardIndex", $ShardIndex,
        "-ShardCount", $ShardCount,
        "-Methods", "spec_rtl_abstracted_trace_summary"
    )
    if ($Models -and $Models.Count -gt 0) {
        $fullEvalArgs += @("-Models", ($Models -join ","))
    }
    if ($OpenAIBaseUrl) { $fullEvalArgs += @("-OpenAIBaseUrl", $OpenAIBaseUrl) }
    if ($OpenAIModel) { $fullEvalArgs += @("-OpenAIModel", $OpenAIModel) }
    if ($OpenAIAuthScheme) { $fullEvalArgs += @("-OpenAIAuthScheme", $OpenAIAuthScheme) }
    if ($OpenAIExtraHeadersJson) { $fullEvalArgs += @("-OpenAIExtraHeadersJson", $OpenAIExtraHeadersJson) }
    $fullEvalArgs += @("-OpenAIMaxRetries", $OpenAIMaxRetries, "-OpenAIRetryBackoffSec", $OpenAIRetryBackoffSec)
    if ($ClaudeProvider) { $fullEvalArgs += @("-ClaudeProvider", $ClaudeProvider) }
    if ($ClaudeBaseUrl) { $fullEvalArgs += @("-ClaudeBaseUrl", $ClaudeBaseUrl) }
    if ($ClaudeModel) { $fullEvalArgs += @("-ClaudeModel", $ClaudeModel) }
    if ($ClaudeAuthMode) { $fullEvalArgs += @("-ClaudeAuthMode", $ClaudeAuthMode) }
    if ($ClaudeAuthScheme) { $fullEvalArgs += @("-ClaudeAuthScheme", $ClaudeAuthScheme) }
    if ($ClaudeApiVersion) { $fullEvalArgs += @("-ClaudeApiVersion", $ClaudeApiVersion) }
    if ($ClaudeExtraHeadersJson) { $fullEvalArgs += @("-ClaudeExtraHeadersJson", $ClaudeExtraHeadersJson) }
    $fullEvalArgs += @("-ClaudeMaxRetries", $ClaudeMaxRetries, "-ClaudeRetryBackoffSec", $ClaudeRetryBackoffSec)
    if ($QwenProvider) { $fullEvalArgs += @("-QwenProvider", $QwenProvider) }
    if ($QwenBaseUrl) { $fullEvalArgs += @("-QwenBaseUrl", $QwenBaseUrl) }
    if ($QwenModel) { $fullEvalArgs += @("-QwenModel", $QwenModel) }
    if ($QwenAuthScheme) { $fullEvalArgs += @("-QwenAuthScheme", $QwenAuthScheme) }
    if ($QwenExtraHeadersJson) { $fullEvalArgs += @("-QwenExtraHeadersJson", $QwenExtraHeadersJson) }
    $fullEvalArgs += @("-QwenMaxRetries", $QwenMaxRetries, "-QwenRetryBackoffSec", $QwenRetryBackoffSec)
    if ($DryRun) { $fullEvalArgs += "-DryRun" }

    & powershell @fullEvalArgs

    if (-not $SkipRebuild) {
        & $PythonExe "src\build_case_level_delta_matrix.py"
        if (-not $SkipMainResults) {
            & $PythonExe "src\build_main_results_strict_success.py"
        }
    }
}
finally {
    Pop-Location
}
