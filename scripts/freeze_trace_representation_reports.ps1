param(
    [string]$PythonExe = "",
    [string]$RepoRoot = "D:\AssertionForge-main1"
)
$ErrorActionPreference = "Stop"
if (-not $PythonExe) {
    $bundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundledPython) { $PythonExe = $bundledPython }
    else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) { $PythonExe = $pythonCommand.Source }
    }
}
if (-not $PythonExe -or -not (Test-Path -LiteralPath $PythonExe)) { throw "Python not found" }
Set-Location -LiteralPath $RepoRoot
& $PythonExe src/freeze_trace_representation_reports.py `
    --data-dir outputs/scale120_trace_representation_ablation_data `
    --k 2 --repetitions 10000 --seed 20260721
if ($LASTEXITCODE -ne 0) { throw "Trace-representation report freeze failed with exit code $LASTEXITCODE" }
