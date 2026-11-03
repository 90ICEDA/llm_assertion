$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$workspace='deliverables/independent_blind_workspace_20260922'
$review='deliverables/independent_blind_review_20260922'
$scope='deliverables/preunblind_selection_scope_20260922'
$out='deliverables/independent_unblind_20260922'
$raw=Join-Path $out 'raw_originals'
New-Item -ItemType Directory -Force $raw|Out-Null
function Sha([string]$p){(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant()}
function RequireHash([string]$p,[string]$expected){if((Sha $p) -ne $expected){throw "seal hash mismatch: $p"}}
function Signature($items){(@($items|Sort-Object -Unique) -join '|')}
RequireHash "$workspace/SEAL_SHA256.csv" '860537ac86c9b0d22039e955fe2e287e3e7bd6221a19d1a1b8a9bf5051ce9ddd'
RequireHash "$review/SEAL_MANIFEST.csv" '9fa3f1e6bf05c4caf4d6214bc8b640f70cf240bb59f435e60f090965db0b284f'
RequireHash "$scope/PRE_UNBLIND_FREEZE.json" '38d43c12d8600fffac779de34d76750b115972b059c1e0b0816091532af0404e'
foreach($r in (Import-Csv "$review/SEAL_MANIFEST.csv")){ $p=Join-Path $review $r.file;if((Get-Item -LiteralPath $p).Length -ne [long]$r.bytes -or (Sha $p) -ne $r.sha256){throw "review file changed: $p"} }
foreach($r in (Import-Csv "$scope/HISTORICAL_DECISION_FILES.csv")){if((Sha $r.path) -ne $r.sha256){throw "decision input changed: $($r.path)"}}
$pairs=@(Import-Csv "$review/pair_judgments.csv")
if($pairs.Count -ne 42){throw 'expected 42 sealed pair judgments'}
$parents=@($pairs.parent_bug_id|Sort-Object -Unique)
if($parents.Count -ne 2){throw 'expected two selected parents'}
$assets=[System.Collections.Generic.List[object]]::new()
$sources=@('outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/dev_top1_v1/execution_evaluation_v1/dev_metrics_and_selection.json',
  'src/evaluate_balanced_behavioral_dev_top1.py')
foreach($parent in $parents){$sources+="outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent/parent_result.json"}
foreach($src in $sources){
  $dst=Join-Path $raw $src;New-Item -ItemType Directory -Force (Split-Path $dst -Parent)|Out-Null
  Copy-Item -LiteralPath $src -Destination $dst -Force
  $hash=Sha $src;if((Sha $dst) -ne $hash){throw "copy mismatch: $src"}
  $assets.Add([pscustomobject]@{source_path=$src;bytes=(Get-Item -LiteralPath $src).Length;sha256=$hash;copy_path=$dst.Replace('\','/')})
}
$assets|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'source_inventory.csv')
$old=@{};foreach($parent in $parents){$old[$parent]=Get-Content "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent/parent_result.json" -Raw|ConvertFrom-Json}
$rows=[System.Collections.Generic.List[object]]::new()
foreach($pair in $pairs){
  $parent=$pair.parent_bug_id;$result=$old[$parent]
  foreach($policy in @('random_legal','disagreement_guided')){
    $leftId="${parent}__v3_$($pair.left_slot)";$rightId="${parent}__v3_$($pair.right_slot)"
    $a=@($result.candidate_sets|Where-Object {$_.candidate_id -eq $leftId -and $_.probe_policy -eq $policy})
    $b=@($result.candidate_sets|Where-Object {$_.candidate_id -eq $rightId -and $_.probe_policy -eq $policy})
    if($a.Count -ne 1 -or $b.Count -ne 1){throw "missing old feedback: $parent $policy $leftId $rightId"}
    $af=Signature $a[0].fp_probe_ids;$bf=Signature $b[0].fp_probe_ids;$at=Signature $a[0].tp_mutant_ids;$bt=Signature $b[0].tp_mutant_ids
    $fullEqual=($af -ceq $bf -and $at -ceq $bt)
    $countEqual=($a[0].fp_probe_ids.Count -eq $b[0].fp_probe_ids.Count -and $a[0].tp_mutant_ids.Count -eq $b[0].tp_mutant_ids.Count)
    $directional=$pair.judgment -in @('LEFT_BETTER','RIGHT_BETTER')
    $rows.Add([pscustomobject]@{parent_bug_id=$parent;policy=$policy;left_slot=$pair.left_slot;right_slot=$pair.right_slot;sealed_judgment=$pair.judgment;left_candidate_id=$leftId;right_candidate_id=$rightId;left_fp_count=$a[0].fp_probe_ids.Count;right_fp_count=$b[0].fp_probe_ids.Count;left_tp_count=$a[0].tp_mutant_ids.Count;right_tp_count=$b[0].tp_mutant_ids.Count;fp_set_identical=($af -ceq $bf);tp_set_identical=($at -ceq $bt);old_full_feedback_identical=$fullEqual;old_counts_identical=$countEqual;independently_ranked_quality_difference=$directional;actionable_feedback_tie=($directional -and $fullEqual);old_parent_result_path="outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent/parent_result.json";old_parent_result_sha256=Sha "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent/parent_result.json"})
  }
}
$rows|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'pairwise_feedback_comparison.csv')
$timeoutRows=[System.Collections.Generic.List[object]]::new()
foreach($parent in $parents){
  $dir="outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/$parent/runs"
  foreach($file in (Get-ChildItem -LiteralPath $dir -Recurse -File -Filter result.json)){
    $item=Get-Content $file.FullName -Raw|ConvertFrom-Json
    $rel=$file.FullName.Substring($root.Length+1).Replace('\','/')
    $h=Sha $file.FullName
    foreach($variant in @('correct','buggy')){foreach($stage in @('compile','simulation')){
      $run=$item.rtl.$variant.$stage
      $status=if($null -eq $run -or $null -eq $run.timeout){'UNKNOWN_MISSING_FIELD'}elseif($run.timeout){'TIMEOUT'}else{'NO_TIMEOUT_RECORDED'}
      $timeoutRows.Add([pscustomobject]@{parent_bug_id=$parent;candidate_id=$item.candidate_id;probe_id=$item.probe_id;rtl_variant=$variant;stage=$stage;result_path=$rel;result_sha256=$h;timeout_status=$status;returncode=if($run){$run.returncode}else{$null}})
    }}
  }
}
$timeoutRows|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'historical_timeout_by_object.csv')
$decisionPath='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/dev_top1_v1/execution_evaluation_v1/dev_metrics_and_selection.json'
$decision=Get-Content $decisionPath -Raw|ConvertFrom-Json
$rank=[System.Collections.Generic.List[object]]::new()
foreach($name in @('anchor_10','anchor_20','anchor_25','scalar_score_dpo','full_disagreement_dominance_dpo')){
  $s=$decision.summaries.$name
  $rank.Add([pscustomobject]@{method=$name;query_count=$s.query_count;scs_at_1=$s.'SCS@1';fixed_safe=$s.'Fixed-Safe';target_detect=$s.'Target Detect';eligible_under_frozen_rule=($name -like 'anchor_*' -and $s.'Fixed-Safe' -ge $decision.selection.constraints.fixed_safe_floor -and $s.'Target Detect' -ge $decision.selection.constraints.target_detect_floor);historical_selected=($name -eq $decision.selection.selected_variant)})
}
$rank|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'historical_variant_selection_check.csv')
$actionable=@($rows|Where-Object actionable_feedback_tie -eq $true)
$statusRows=@(
  [pscustomobject]@{object='qualifying_quality_difference_plus_old_feedback_tie';status='NOT_FOUND_AFTER_CHECK';scope='42 sealed pairs x 2 old policies; exact full FP/TP ID-set equality checked';evidence='pairwise_feedback_comparison.csv'},
  [pscustomobject]@{object='new_targeted_witness_for_this_two_parent_batch';status='NOT_ATTEMPTED';scope='No qualifying pair emerged from the checked feedback comparison';evidence='pairwise_feedback_comparison.csv'},
  [pscustomobject]@{object='historical_anchor_20_variant_selection_effect_from_these_pair_judgments';status='NOT_ESTABLISHED';scope='Frozen six dev-parent variant selection; no causal intervention or changed historical decision log';evidence='historical_variant_selection_check.csv'},
  [pscustomobject]@{object='historical_probe_timeouts_selected_two_parents';status=if(@($timeoutRows|Where-Object timeout_status -eq TIMEOUT).Count){'TIMEOUT_OBSERVED'}elseif(@($timeoutRows|Where-Object timeout_status -like 'UNKNOWN*').Count){'PARTIALLY_UNKNOWN'}else{'NO_TIMEOUT_RECORDED_IN_CHECKED_OBJECTS'};scope="$($timeoutRows.Count) correct/buggy compile/simulation stage objects";evidence='historical_timeout_by_object.csv'}
)
$statusRows|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'status_ledger.csv')
[ordered]@{seal_status='VERIFIED_BEFORE_UNBLIND';selected_parents=$parents;sealed_pairs=$pairs.Count;policy_pair_rows=$rows.Count;directional_quality_pair_rows=@($rows|Where-Object independently_ranked_quality_difference -eq $true).Count;old_full_feedback_ties=@($rows|Where-Object old_full_feedback_identical -eq $true).Count;directional_quality_pairs_with_identical_old_full_feedback=$actionable.Count;historical_timeout_stage_objects=$timeoutRows.Count;historical_timeouts=@($timeoutRows|Where-Object timeout_status -eq TIMEOUT).Count;unknown_timeout_fields=@($timeoutRows|Where-Object timeout_status -like 'UNKNOWN*').Count;historical_selected_variant=$decision.selection.selected_variant;historical_variant_selection_effect='NOT_ESTABLISHED: sealed parent-pair judgments are not the six dev-parent model outputs or selection inputs';new_training='NONE'}|ConvertTo-Json -Depth 5|Set-Content -Encoding utf8 (Join-Path $out 'unblind_summary.json')
Get-Content (Join-Path $out 'unblind_summary.json') -Raw
