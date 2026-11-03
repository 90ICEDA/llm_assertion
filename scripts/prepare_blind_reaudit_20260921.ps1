$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$out = 'deliverables/blind_reaudit_20260921'
$raw = Join-Path $out 'pre_feedback_raw'
New-Item -ItemType Directory -Force -Path $raw | Out-Null
$selection = 'outputs/behavioral_preference_pilot_v1/selected_train_parents.csv'
$exclude = @('case115_prim_edge_both_edges_collapsed','case505_axis_stat_counter_frame_pulse_early','case463_axis_frame_join_port_skip','case506_axis_crosspoint_simultaneous_source_priority','case457_cc_delta_counter_load_enable_priority','case478_axis_srl_register_ready_recovery')
$parents = @(Import-Csv $selection | Where-Object {$_.parent_bug_id -notin $exclude})
$rng = [System.Random]::new(20260921)
for ($i=$parents.Count-1; $i -gt 0; $i--) { $j=$rng.Next($i+1); $tmp=$parents[$i]; $parents[$i]=$parents[$j]; $parents[$j]=$tmp }
$picked = @($parents | Select-Object -First 4)
$picked | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'selected_parents.csv')
$fileRecords = [System.Collections.Generic.List[object]]::new()
$candidates = [System.Collections.Generic.List[object]]::new()
function Save-Evidence([string]$source,[string]$destination,[string]$class) {
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "MISSING pre-feedback source: $source" }
  $dir=Split-Path $destination -Parent
  New-Item -ItemType Directory -Force -Path $dir | Out-Null
  Copy-Item -LiteralPath $source -Destination $destination -Force
  $sourceHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $source).Hash.ToLowerInvariant()
  $copyHash=(Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash.ToLowerInvariant()
  if ($sourceHash -ne $copyHash) { throw "copy mismatch: $source" }
  $fileRecords.Add([pscustomobject]@{source=$source.Replace('\','/');copy=$destination.Replace('\','/');sha256=$sourceHash;class=$class;bytes=(Get-Item -LiteralPath $source).Length})
}
Save-Evidence $selection (Join-Path $raw 'selected_train_parents.csv') 'sampling_frame'
Save-Evidence 'src/behavioral_preference_v3_gate.py' (Join-Path $raw 'behavioral_preference_v3_gate.py') 'provenance_code'
foreach ($p in $picked) {
  $parentId=$p.parent_bug_id
  $case=Join-Path $p.dataset_root $p.case_id
  $target=Join-Path $raw $parentId
  foreach ($name in @('buggy.v','correct.v','mutation.diff','spec.md','golden.sva','STIMULUS_NOTES.md','case_metadata.json','tb.v','tb_holdout.v')) {
    $src=Join-Path $case $name
    if (Test-Path -LiteralPath $src -PathType Leaf) { Save-Evidence $src (Join-Path $target $name) 'repair_context' }
  }
  for($slot=1;$slot -le 8;$slot++) {
    $prefix="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$parentId/slot_$($slot.ToString('00'))/attempt_01"
    $class=if($slot -eq 8){'synthetic_control'}else{'natural_model_response'}
    foreach($name in @('request.json','raw_response.json','prompt.txt','candidate.sva','evidence.json')) {
      Save-Evidence "$prefix/$name" (Join-Path $target "slot_$($slot.ToString('00'))/$name") $class
    }
    $req=Get-Content "$prefix/request.json" -Raw|ConvertFrom-Json
    $response=Get-Content "$prefix/raw_response.json" -Raw|ConvertFrom-Json
    $ast=$response.message.content|ConvertFrom-Json
    $assertion=(Get-Content "$prefix/candidate.sva" -Raw).Trim()
    $isSynthetic=($assertion -match '\(\((\w+) && !\1\)\)')
    $expectedClass=if($slot -eq 8){'synthetic_control'}else{'natural_model_response'}
    if($slot -eq 8 -and -not $isSynthetic){throw "slot 8 synthetic invariant absent: $parentId"}
    if($slot -le 7 -and $isSynthetic){throw "natural slot contains synthetic antecedent: $parentId/$slot"}
    $schema=$req.format.properties
    if($ast.antecedent_signal -notin $schema.antecedent_signal.enum -or $ast.consequent_signal -notin $schema.consequent_signal.enum -or $ast.implication -notin $schema.implication.enum -or $ast.relation -notin $schema.relation.enum){throw "AST outside frozen request schema: $parentId/$slot"}
    if($assertion -notmatch '^assert property \('){throw "no rendered assertion: $parentId/$slot"}
    $candidates.Add([pscustomobject]@{parent_bug_id=$parentId;candidate_id="$parentId`__v3_slot_$($slot.ToString('00'))";slot=$slot;class=$expectedClass;source_model=$req.model;synthetic_render_invariant=$isSynthetic;clean_source_and_schema=$true;runtime_compile_status='SEALED_UNTIL_FEEDBACK';request_path="$prefix/request.json";raw_response_path="$prefix/raw_response.json";assertion_path="$prefix/candidate.sva";evidence_path="$prefix/evidence.json";assertion=$assertion})
  }
}
$fileRecords | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'pre_feedback_file_inventory.csv')
$candidates | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'candidate_provenance.csv')
[ordered]@{seed=20260921;random_method='PowerShell System.Random Fisher-Yates shuffle';sampling_frame=$selection;sampling_frame_sha256=(Get-FileHash -Algorithm SHA256 $selection).Hash.ToLowerInvariant();excluded_previously_inspected_parents=$exclude;eligible_after_exclusion=$parents.Count;selected=@($picked.parent_bug_id);natural_candidates=28;synthetic_controls=4;feedback_access='forbidden_until_judgment_freeze';pre_feedback_clean_definition='source model response parses under frozen request schema; rendered assertion is present and no synthetic antecedent; runtime compile validated only after freeze';provenance_note='All AST responses originate from model; slot 8 rendered assertion is synthetic because renderer injects contradictory antecedent.'}|ConvertTo-Json -Depth 6|Set-Content -Encoding utf8 (Join-Path $out 'sampling_and_provenance_manifest.json')
