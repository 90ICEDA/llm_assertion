$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$out='deliverables/phase_b_original_artifact_search_20260922'
New-Item -ItemType Directory -Force $out|Out-Null
$pattern='checkpoint-004058|adapter_model\.safetensors|training_result\.json|train_log\.jsonl|latest_checkpoint\.txt'
$names=@('adapter_model.safetensors','training_result.json','train_log.jsonl','latest_checkpoint.txt')
$archives=[System.Collections.Generic.List[object]]::new()
$archives.AddRange([object[]]@(Get-ChildItem -LiteralPath $root -File|Where-Object Name -Match '\.(tar\.gz|zip)$'))
$archives.AddRange([object[]]@(Get-ChildItem -LiteralPath deliverables -Recurse -File|Where-Object Name -Match '\.(tar\.gz|zip)$'))
$archiveRows=[System.Collections.Generic.List[object]]::new()
$memberHits=[System.Collections.Generic.List[object]]::new()
foreach($a in ($archives|Sort-Object FullName -Unique)){
  $members=@(tar -tf $a.FullName)
  if($LASTEXITCODE -ne 0){throw "archive listing failed: $($a.FullName)"}
  $hits=@($members|Where-Object { $_ -match $pattern })
  $rel=$a.FullName.Substring($root.Length+1).Replace('\','/')
  $archiveRows.Add([pscustomobject]@{archive_path=$rel;bytes=$a.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $a.FullName).Hash.ToLowerInvariant();member_count=$members.Count;target_member_count=$hits.Count;status=if($hits.Count){'HIT'}else{'NO_TARGET_MEMBER'}})
  foreach($h in $hits){$memberHits.Add([pscustomobject]@{archive_path=$rel;member_path=$h})}
}
$archiveRows|Export-Csv -NoTypeInformation -Encoding utf8 "$out/archive_inventory.csv"
$memberHits|Export-Csv -NoTypeInformation -Encoding utf8 "$out/archive_target_members.csv"
$dirs=@('outputs/behavioral_preference_pilot_v1','outputs/behavioral_preference_pilot_v2','outputs/behavioral_preference_closed_loop_final_v1','outputs/behavioral_posthoc_analysis_v1','outputs/phase_b_ood_eval_v1','outputs/checkpoints','deliverables','analysis','scripts','src')
$dirRows=[System.Collections.Generic.List[object]]::new();$fileHits=[System.Collections.Generic.List[object]]::new()
foreach($d in $dirs){
  $files=@(Get-ChildItem -LiteralPath $d -Recurse -File)
  $hits=@($files|Where-Object { $names -contains $_.Name -or $_.FullName -match 'checkpoint-004058' })
  $dirRows.Add([pscustomobject]@{directory=$d;file_count=$files.Count;target_file_count=$hits.Count;status=if($hits.Count){'HIT'}else{'NO_TARGET_FILE'}})
  foreach($f in $hits){$fileHits.Add([pscustomobject]@{path=$f.FullName.Substring($root.Length+1).Replace('\','/');bytes=$f.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLowerInvariant()})}
}
$dirRows|Export-Csv -NoTypeInformation -Encoding utf8 "$out/directory_inventory.csv"
$fileHits|Export-Csv -NoTypeInformation -Encoding utf8 "$out/directory_target_files.csv"
$missing=@('checkpoint-004058/adapter_model.safetensors','train_log.jsonl','training_result.json','latest_checkpoint.txt')
$missing|ForEach-Object {[pscustomobject]@{expected_relative_to='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30';artifact=$_;status='MISSING';execution_inference='UNKNOWN'}}|Export-Csv -NoTypeInformation -Encoding utf8 "$out/MISSING.csv"
[ordered]@{status=if($memberHits.Count -eq 0 -and $fileHits.Count -eq 0){'NO_ORIGINAL_TRAINING_ARTIFACT_FOUND'}else{'TARGET_FOUND_REVIEW_REQUIRED'};archives_checked=$archiveRows.Count;archive_members=($archiveRows|Measure-Object member_count -Sum).Sum;directories_checked=$dirRows.Count;files_checked=($dirRows|Measure-Object file_count -Sum).Sum;archive_target_hits=$memberHits.Count;directory_target_hits=$fileHits.Count;original_training_execution='UNKNOWN';physical_adapter_verification='MISSING';local_reproducible_load='NOT_DEMONSTRATED'}|ConvertTo-Json -Depth 4|Set-Content -Encoding utf8 "$out/summary.json"
Get-Content "$out/summary.json" -Raw
