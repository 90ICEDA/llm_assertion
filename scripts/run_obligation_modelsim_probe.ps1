$ErrorActionPreference = 'Stop'
$root = 'D:/AssertionForge-main1/deliverables/obligation_continuation_20261013_r01/native_modelsim'
Set-Location -LiteralPath $root
$results = @()
foreach ($step in @(
    @{ Name = 'vlib'; Args = @('work') },
    @{ Name = 'vlog'; Args = @('-sv', 'qa.sv') },
    @{ Name = 'vsim'; Args = @('-c', '-novopt', 'work.tb', '-do', 'run -all; quit -f') }
)) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    $argsForTool = $step.Args
    $output = & "D:/modeltech64_10.4/win64/$($step.Name).exe" @argsForTool 2>&1
    $exit = $LASTEXITCODE
    $timer.Stop()
    $output | Set-Content -LiteralPath "$root/$($step.Name).log" -Encoding UTF8
    $results += @{ tool=$step.Name; args=$argsForTool; exit_code=$exit; wall_seconds=$timer.Elapsed.TotalSeconds }
    ConvertTo-Json -InputObject $results -Depth 6 | Set-Content -LiteralPath "$root/commands.json" -Encoding UTF8
    if ($exit -ne 0) { break }
}
$results | ConvertTo-Json -Depth 6
