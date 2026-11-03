$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$base='deliverables/blind_reaudit_20260921'
$out=Join-Path $base 'postfreeze_bug_evidence_supplement_20260922'
$raw=Join-Path $out 'raw_originals'
New-Item -ItemType Directory -Force $raw|Out-Null
$parents=@(Import-Csv (Join-Path $base 'selected_parents.csv')|ForEach-Object parent_bug_id)
if($parents.Count -ne 4){throw "expected four parents, got $($parents.Count)"}
$sourcePaths=[System.Collections.Generic.List[string]]::new()
foreach($p in $parents){
  $dir=Join-Path 'rtl_cases_real_scale210_independent_next' $p
  foreach($f in (Get-ChildItem -LiteralPath $dir -Recurse -File)){$sourcePaths.Add($f.FullName.Substring($root.Length+1).Replace('\','/'))}
}
$sourcePaths.Add('rtl_cases_real_scale210_independent_next/hardness_admission_report.csv')
$sourcePaths.Add('rtl_cases_real_scale210_independent_next/hardness_admission_summary.json')
$rows=[System.Collections.Generic.List[object]]::new()
foreach($path in ($sourcePaths|Sort-Object -Unique)){
  $src=Join-Path $root $path;$dst=Join-Path $raw $path
  New-Item -ItemType Directory -Force (Split-Path $dst -Parent)|Out-Null
  Copy-Item -LiteralPath $src -Destination $dst -Force
  $sha=(Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToLowerInvariant()
  if((Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash.ToLowerInvariant() -ne $sha){throw "copy hash mismatch: $path"}
  $rows.Add([pscustomobject]@{source_path=$path;source_absolute=$src;bytes=(Get-Item -LiteralPath $src).Length;sha256=$sha;copy_path=$dst.Replace('\','/');status='FOUND_BYTE_IDENTICAL'})
}
$rows|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'evidence_inventory.csv')
$old=@{};foreach($r in (Import-Csv (Join-Path $base 'pre_feedback_file_inventory.csv'))){$old[$r.source]=$r}
$cross=[System.Collections.Generic.List[object]]::new()
foreach($p in $parents){foreach($f in @('buggy.v','correct.v','mutation.diff','spec.md')){
  $path="rtl_cases_real_scale210_independent_next/$p/$f";$now=$rows|Where-Object source_path -eq $path
  $before=$old[$path]
  $cross.Add([pscustomobject]@{parent_bug_id=$p;source_path=$path;new_sha256=$now.sha256;pre_feedback_sha256=if($before){$before.sha256}else{$null};status=if(-not $before){'NOT_IN_PRE_FEEDBACK_INVENTORY'}elseif($now.sha256 -eq $before.sha256){'UNCHANGED_FROM_PRE_FEEDBACK_SEAL'}else{'HASH_MISMATCH'}})
}}
$cross|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'repair_context_crosscheck.csv')
$admission=Import-Csv 'rtl_cases_real_scale210_independent_next/hardness_admission_report.csv'|Where-Object { $parents -contains $_.parent_bug_id }
if($admission.Count -ne 4){throw "expected four admission rows, got $($admission.Count)"}
$admission|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'selected_hardness_admission_rows.csv')
[ordered]@{selected_parents=$parents;raw_files=$rows.Count;repair_context_crosschecks=$cross.Count;repair_context_hash_mismatches=@($cross|Where-Object status -eq HASH_MISMATCH).Count;hardness_admission_rows=$admission.Count;archive_time_utc=[DateTime]::UtcNow.ToString('o');status='POSTFREEZE_SUPPLEMENT_NOT_PART_OF_ORIGINAL_SEAL'}|ConvertTo-Json -Depth 4|Set-Content -Encoding utf8 (Join-Path $out 'summary.json')
Get-Content (Join-Path $out 'summary.json') -Raw
