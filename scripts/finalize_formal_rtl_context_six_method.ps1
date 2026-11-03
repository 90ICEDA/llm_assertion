param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1"
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
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/finalize_rtl_context_six_method_experiment.py `
    --baseline outputs/scale120_rtl_context_ablation_data_gpt_sharded4/multi_model_results_raw.csv `
    --small-slice outputs/scale120_rtl_context_small_slice_v2/formal/multi_model_results_raw.csv `
    --output-dir outputs/scale120_rtl_context_six_method_formal `
    --k 2 --repetitions 10000 --seed 20260721
if ($LASTEXITCODE -ne 0) { throw "Six-method finalization failed with exit code $LASTEXITCODE" }
