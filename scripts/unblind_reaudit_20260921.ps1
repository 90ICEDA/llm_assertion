$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$out='deliverables/blind_reaudit_20260921'
$seal=Get-Content (Join-Path $out 'PRE_FEEDBACK_FREEZE.json') -Raw|ConvertFrom-Json
foreach($row in $seal){$now=(Get-FileHash -Algorithm SHA256 -LiteralPath $row.path).Hash.ToLowerInvariant();if($now -ne $row.sha256){throw "Pre-feedback freeze broken: $($row.path)"}}
$pairs=@(Import-Csv (Join-Path $out 'pairwise_judgments_frozen.csv'))
$parents=@(Import-Csv (Join-Path $out 'selected_parents.csv')|ForEach-Object parent_bug_id)
$manifestPath='outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json'
$manifest=Get-Content $manifestPath -Raw|ConvertFrom-Json
$feedback=@($manifest.candidate_policy_records|Where-Object {$_.parent_bug_id -in $parents -and [int](($_.candidate_id -split '_slot_')[-1]) -le 7})
$feedback|ConvertTo-Json -Depth 20|Set-Content -Encoding utf8 (Join-Path $out 'legacy_feedback_snapshot.json')
$byId=@{};foreach($r in $feedback){$byId[($r.probe_policy+'|'+$r.candidate_id)]=$r}
$joined=[System.Collections.Generic.List[object]]::new()
foreach($policy in @('random_legal','disagreement_guided')){foreach($p in $pairs){
  $a=$byId[($policy+'|'+$p.candidate_a)];$b=$byId[($policy+'|'+$p.candidate_b)]
  if($null -eq $a -or $null -eq $b){throw "Missing legacy feedback: $($p.parent_bug_id) $policy"}
  $fpA=(@($a.fp_probe_ids)|Sort-Object)-join '|';$fpB=(@($b.fp_probe_ids)|Sort-Object)-join '|'
  $tpA=(@($a.tp_mutant_ids)|Sort-Object)-join '|';$tpB=(@($b.tp_mutant_ids)|Sort-Object)-join '|'
  $same=($fpA -ceq $fpB -and $tpA -ceq $tpB)
  $joined.Add([pscustomobject]@{parent_bug_id=$p.parent_bug_id;policy=$policy;candidate_a=$p.candidate_a;candidate_b=$p.candidate_b;independent_relation=$p.relation;legacy_full_signature_identical=$same;fp_a=@($a.fp_probe_ids).Count;fp_b=@($b.fp_probe_ids).Count;tp_a=@($a.tp_mutant_ids).Count;tp_b=@($b.tp_mutant_ids).Count;case_status=if($same -and $p.relation -in @('A_BETTER','B_BETTER')){'SEMANTIC_DIFFERENCE_FEEDBACK_TIE'}else{'NOT_FOUND_FOR_THIS_PAIR'}})
}}
$joined|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'postfreeze_feedback_comparison.csv')
$case='case510_cc_spill_register_flush_push_priority';$ids=@("$case`__v3_slot_06","$case`__v3_slot_07")
$schedule='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/anchor_20_all30.jsonl'
$scheduleHits=@(Get-Content $schedule|ForEach-Object {$_|ConvertFrom-Json}|Where-Object {$_.example_id -in $ids -or $_.chosen_id -in $ids -or $_.rejected_id -in $ids})
$scheduleHits|ConvertTo-Json -Depth 12|Set-Content -Encoding utf8 (Join-Path $out 'case510_training_batch_rows.json')
$verify=@();foreach($slot in 6,7){$f="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$case/slot_$($slot.ToString('00'))/attempt_01/evidence.json";$verify+=Get-Content $f -Raw|ConvertFrom-Json}
$verify|ConvertTo-Json -Depth 20|Set-Content -Encoding utf8 (Join-Path $out 'case510_original_candidate_verification.json')
[ordered]@{pre_feedback_seal_sha256=(Get-FileHash -Algorithm SHA256 (Join-Path $out 'PRE_FEEDBACK_FREEZE.json')).Hash.ToLowerInvariant();feedback_source=$manifestPath;feedback_source_sha256=(Get-FileHash -Algorithm SHA256 $manifestPath).Hash.ToLowerInvariant();full_feedback_rows=$feedback.Count;pairwise_comparisons=$joined.Count;case510_slot06_slot07_equal_full_signature_both_policies=@($joined|Where-Object {$_.candidate_a -eq $ids[0] -and $_.candidate_b -eq $ids[1] -and $_.legacy_full_signature_identical}).Count -eq 2;slot06_sft_anchor_rows=@($scheduleHits|Where-Object {$_.example_id -eq $ids[0] -and $_.record_type -eq 'sft_anchor'}).Count;slot07_sft_anchor_rows=@($scheduleHits|Where-Object {$_.example_id -eq $ids[1] -and $_.record_type -eq 'sft_anchor'}).Count;new_witness='witnesses/case510_held_flush';witness_fixed_result='slot06 pass; slot07 false positive';witness_buggy_result='both fail';timeout_status='NOT_OBSERVED_IN_CASE510_CACHED_EVIDENCE_OR_NEW_WITNESS';new_training='NONE'}|ConvertTo-Json -Depth 6|Set-Content -Encoding utf8 (Join-Path $out 'postfreeze_summary.json')
