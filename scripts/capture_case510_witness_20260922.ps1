$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$out='deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/command_capture_20260922'
New-Item -ItemType Directory -Force $out|Out-Null
$linux='/mnt/d/AssertionForge-main1'
$case="$linux/rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority"
$tb="$linux/deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/tb_held_flush.v"
$output="$linux/$out"
function Sha($p){(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant()}
function Capture([string]$name,[string[]]$arguments){
  $psi=[System.Diagnostics.ProcessStartInfo]::new('wsl.exe')
  $psi.UseShellExecute=$false;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true;$psi.CreateNoWindow=$true;$psi.WorkingDirectory=$root
  foreach($a in @('--exec')+$arguments){[void]$psi.ArgumentList.Add($a)}
  $p=[System.Diagnostics.Process]::Start($psi)
  $stdoutMemory=[System.IO.MemoryStream]::new();$stderrMemory=[System.IO.MemoryStream]::new()
  $stdoutTask=$p.StandardOutput.BaseStream.CopyToAsync($stdoutMemory);$stderrTask=$p.StandardError.BaseStream.CopyToAsync($stderrMemory)
  $p.WaitForExit();[void]$stdoutTask.GetAwaiter().GetResult();[void]$stderrTask.GetAwaiter().GetResult()
  $stdoutBytes=$stdoutMemory.ToArray();$stderrBytes=$stderrMemory.ToArray()
  $stdoutPath=Join-Path $out "$name.stdout.raw";$stderrPath=Join-Path $out "$name.stderr.raw"
  [System.IO.File]::WriteAllBytes((Join-Path $root $stdoutPath),$stdoutBytes)
  [System.IO.File]::WriteAllBytes((Join-Path $root $stderrPath),$stderrBytes)
  [System.IO.File]::WriteAllText((Join-Path $root (Join-Path $out "$name.stdout.txt")),[System.Text.Encoding]::UTF8.GetString($stdoutBytes),[System.Text.UTF8Encoding]::new($false))
  [System.IO.File]::WriteAllText((Join-Path $root (Join-Path $out "$name.stderr.txt")),[System.Text.Encoding]::UTF8.GetString($stderrBytes),[System.Text.UTF8Encoding]::new($false))
  [pscustomobject]@{name=$name;argv=@('wsl.exe','--exec')+$arguments;exit_code=$p.ExitCode;stdout_raw_path=$stdoutPath;stdout_raw_bytes=$stdoutBytes.Length;stdout_raw_sha256=Sha $stdoutPath;stderr_raw_path=$stderrPath;stderr_raw_bytes=$stderrBytes.Length;stderr_raw_sha256=Sha $stderrPath;stdout_text_view_path=(Join-Path $out "$name.stdout.txt");stderr_text_view_path=(Join-Path $out "$name.stderr.txt")}
}
$inputs=@('rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/correct.v','rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/buggy.v','deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/tb_held_flush.v')
$inputs|ForEach-Object {[pscustomobject]@{path=$_;bytes=(Get-Item $_).Length;sha256=Sha $_}}|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'input_hashes.csv')
$runs=[System.Collections.Generic.List[object]]::new()
$runs.Add((Capture 'iverilog_version' @('iverilog','-V')))
$runs.Add((Capture 'vvp_version' @('vvp','-V')))
foreach($variant in @('correct','buggy')){
  $runs.Add((Capture "${variant}_compile" @('iverilog','-g2012','-s','tb','-o',"$output/$variant.out","$case/$variant.v",$tb)))
  if($runs[-1].exit_code -eq 0){$runs.Add((Capture "${variant}_simulate" @('vvp',"$output/$variant.out")))}
}
$runs|ConvertTo-Json -Depth 8|Set-Content -Encoding utf8 (Join-Path $out 'command_runs.json')
$runs|Select-Object name,exit_code,stdout_raw_path,stdout_raw_bytes,stdout_raw_sha256,stderr_raw_path,stderr_raw_bytes,stderr_raw_sha256,stdout_text_view_path,stderr_text_view_path|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'command_runs.csv')
$binaries=@(foreach($variant in @('correct','buggy')){
  $binary=Join-Path $out "$variant.out"
  if(Test-Path -LiteralPath $binary -PathType Leaf){[pscustomobject]@{path=$binary;bytes=(Get-Item -LiteralPath $binary).Length;sha256=Sha $binary}}
})
$binaries|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'compiled_output_hashes.csv')
$runs|Select-Object name,exit_code|Format-Table -AutoSize
