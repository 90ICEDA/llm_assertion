$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$base='deliverables/blind_reaudit_20260921'
$out=Join-Path $base 'postfreeze_status_correction_20260922'
New-Item -ItemType Directory -Force $out|Out-Null
$parents=@(Import-Csv "$base/selected_parents.csv"|ForEach-Object parent_bug_id)
$rows=[System.Collections.Generic.List[object]]::new();$parentRows=[System.Collections.Generic.List[object]]::new()
foreach($parent in $parents){
  $dir="outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent"
  $summary=Get-Content "$dir/parent_result.json" -Raw|ConvertFrom-Json
  $files=@(Get-ChildItem "$dir/runs" -Recurse -File -Filter result.json)
  $parentTimeout=0;$parentUnknown=0
  foreach($f in $files){
    $r=Get-Content $f.FullName -Raw|ConvertFrom-Json
    $path=$f.FullName.Substring($root.Length+1).Replace('\','/')
    $hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $f.FullName).Hash.ToLowerInvariant()
    foreach($variant in @('correct','buggy')){foreach($stage in @('compile','simulation')){
      $o=$r.rtl.$variant.$stage
      $status=if($null -eq $o -or $null -eq $o.timeout){'UNKNOWN_MISSING_TIMEOUT_FIELD'}elseif($o.timeout -eq $true){'TIMEOUT'}else{'NO_TIMEOUT_RECORDED'}
      if($status -eq 'TIMEOUT'){$parentTimeout++};if($status -like 'UNKNOWN*'){$parentUnknown++}
      $rows.Add([pscustomobject]@{parent_bug_id=$parent;candidate_id=$r.candidate_id;probe_id=$r.probe_id;rtl_variant=$variant;stage=$stage;result_path=$path;result_sha256=$hash;timeout_status=$status;recorded_returncode=if($o){$o.returncode}else{$null}})
    }}
  }
  $parentRows.Add([pscustomobject]@{parent_bug_id=$parent;result_files=$files.Count;stage_objects=$files.Count*4;stage_timeouts=$parentTimeout;stage_unknown_timeout_fields=$parentUnknown;preflight_timeout_probe_ids=($summary.preflight_timeout_probe_ids -join '|');parent_result_path="$dir/parent_result.json";parent_result_sha256=(Get-FileHash -Algorithm SHA256 "$dir/parent_result.json").Hash.ToLowerInvariant()})
}
$rows|Export-Csv -NoTypeInformation -Encoding utf8 "$out/historical_probe_timeout_by_stage.csv"
$parentRows|Export-Csv -NoTypeInformation -Encoding utf8 "$out/historical_probe_timeout_by_parent.csv"
$capture="$base/witnesses/case510_held_flush/command_capture_20260922/command_runs.json"
$commands=@(Get-Content $capture -Raw|ConvertFrom-Json)
$commandStatus=if($commands.Count -eq 6 -and @($commands|Where-Object exit_code -ne 0).Count -eq 0){'SIX_COMMANDS_COMPLETED_EXIT_0'}else{'REVIEW_COMMAND_FAILURE'}
$ledger=[System.Collections.Generic.List[object]]::new()
$ledger.Add([pscustomobject]@{object='case459_slot02_slot06_quality_difference_and_selection_impact';status='UNKNOWN';search_attempted='partial';evidence='Old feedback tie and semantic relevance distinction; no replayable distinguishing quality witness or actual selection-impact proof'})
$ledger.Add([pscustomobject]@{object='case510_slot06_slot07_quality_witness';status='FOUND';search_attempted='yes';evidence="$base/witnesses/case510_held_flush/command_capture_20260922/command_runs.json; six commands completed with exit 0"})
$ledger.Add([pscustomobject]@{object='other_pair_new_witness';status='NOT_ATTEMPTED';search_attempted='no';evidence='No targeted replay for other pairs; do not use NOT FOUND'})
$ledger.Add([pscustomobject]@{object='case459_replayable_distinguishing_witness';status='NOT_ATTEMPTED';search_attempted='no';evidence='No targeted witness construction/replay after the frozen judgment; case-level conclusion remains UNKNOWN'})
$ledger.Add([pscustomobject]@{object='historical_probe_stage_timeouts_four_parents';status=if(@($rows|Where-Object timeout_status -eq TIMEOUT).Count){'TIMEOUT_OBSERVED'}elseif(@($rows|Where-Object timeout_status -like 'UNKNOWN*').Count){'PARTIALLY_UNKNOWN'}else{'NO_TIMEOUT_RECORDED_IN_CHECKED_OBJECTS'};search_attempted='yes';evidence="$out/historical_probe_timeout_by_stage.csv; no extrapolation outside listed run objects"})
$ledger.Add([pscustomobject]@{object='new_case510_witness_processes';status=$commandStatus;search_attempted='yes';evidence=$capture})
$ledger.Add([pscustomobject]@{object='phase_b_adapter_and_training_records';status='MISSING_AFTER_CHECK';search_attempted='yes';evidence='deliverables/phase_b_original_artifact_search_20260922/MISSING.csv; checked local archives and accessible directories'})
$ledger.Add([pscustomobject]@{object='unsearched_external_original_runtime';status='NOT_ATTEMPTED';search_attempted='no';evidence='Remote original machine/storage inaccessible; not classified NOT FOUND'})
$ledger|Export-Csv -NoTypeInformation -Encoding utf8 "$out/status_ledger_corrected.csv"
$comparisonPath="$base/postfreeze_feedback_comparison.csv"
$comparisonSha=(Get-FileHash -Algorithm SHA256 -LiteralPath $comparisonPath).Hash.ToLowerInvariant()
$pairs=[System.Collections.Generic.List[object]]::new()
$comparisonLine=0
foreach($r in (Import-Csv $comparisonPath)){
  $comparisonLine++
  $is510=$r.parent_bug_id -like 'case510_*' -and $r.candidate_a -like '*slot_06' -and $r.candidate_b -like '*slot_07'
  $is459=$r.parent_bug_id -like 'case459_*' -and $r.candidate_a -like '*slot_02' -and $r.candidate_b -like '*slot_06'
  $pairs.Add([pscustomobject]@{source_path=$comparisonPath;source_sha256=$comparisonSha;source_data_line=$comparisonLine+1;parent_bug_id=$r.parent_bug_id;policy=$r.policy;candidate_a=$r.candidate_a;candidate_b=$r.candidate_b;old_case_status=$r.case_status;new_witness_search_status=if($is510){'FOUND'}else{'NOT_ATTEMPTED'};quality_difference_status=if($is510){'FOUND_FIXED_RTL_FALSE_POSITIVE_SLOT07'}elseif($is459){'UNKNOWN'}else{'NOT_ESTABLISHED'};selection_impact_status=if($is510){'FOUND_SFT_ANCHOR_ADMISSION_ONLY'}elseif($is459){'UNKNOWN'}else{'NOT_ESTABLISHED'}})
}
$pairs|Export-Csv -NoTypeInformation -Encoding utf8 "$out/pairwise_case_status_corrected.csv"
[ordered]@{historical_result_files=($parentRows|Measure-Object result_files -Sum).Sum;historical_stage_objects=$rows.Count;timeouts=@($rows|Where-Object timeout_status -eq TIMEOUT).Count;unknown_timeout_fields=@($rows|Where-Object timeout_status -like 'UNKNOWN*').Count;case459_quality_selection_status='UNKNOWN';case510_command_capture=$commandStatus}|ConvertTo-Json|Set-Content -Encoding utf8 "$out/summary.json"
Get-Content "$out/summary.json" -Raw
