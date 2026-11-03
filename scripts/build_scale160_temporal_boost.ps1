param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1",
    [string]$SourceRoot = "D:\AssertionForge-main1\rtl_cases_real_scale120",
    [string]$OutputRoot = "D:\AssertionForge-main1\rtl_cases_real_scale160_temporal_boosted",
    [string]$FormalGoldenCsv = "D:\AssertionForge-main1\outputs\golden_recheck_scale120_formal.csv",
    [string]$HardnessCsv = "D:\AssertionForge-main1\outputs\hardness_scale120_wsl.csv",
    [string]$DivergenceCsv = "D:\AssertionForge-main1\outputs\trace_divergence_scale120_wsl.csv",
    [switch]$SkipCopyBase,
    [switch]$SkipPreparePrompts
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
    $candidates += @("python", "py", $bundledPython)

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

$ResolvedPythonExe = Resolve-PythonExe -Preferred $PythonExe

Push-Location $RepoRoot
try {
    $cmd = @(
        "rtl_cases\expand_scale160_temporal_boost.py",
        "--source-root", $SourceRoot,
        "--output-root", $OutputRoot,
        "--formal-golden-csv", $FormalGoldenCsv,
        "--hardness-csv", $HardnessCsv,
        "--divergence-csv", $DivergenceCsv
    )
    if ($SkipCopyBase) {
        $cmd += "--skip-copy-base"
    }
    if ($SkipPreparePrompts) {
        $cmd += "--skip-prepare-prompts"
    }

    Write-Host "=== BUILD SCALE160 TEMPORAL BOOST ==="
    Write-Host "python:   $ResolvedPythonExe"
    Write-Host "repo:     $RepoRoot"
    Write-Host "source:   $SourceRoot"
    Write-Host "output:   $OutputRoot"
    Write-Host "formal:   $FormalGoldenCsv"
    Write-Host "hardness: $HardnessCsv"
    Write-Host "trace:    $DivergenceCsv"

    & $ResolvedPythonExe @cmd
}
finally {
    Pop-Location
}
