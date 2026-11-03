$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$repo=(Get-Location).Path
$out='deliverables/phase_b_edge_lineage_20260922'
$raw=Join-Path $out 'raw_originals'
New-Item -ItemType Directory -Force -Path $raw | Out-Null
function Sha([string]$path) { (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() }
function Jsonl([string]$path) {
  $n=0
  foreach($line in [System.IO.File]::ReadLines((Join-Path $repo $path),[System.Text.Encoding]::UTF8)) {
    $n++
    if([string]::IsNullOrWhiteSpace($line)){continue}
    [pscustomobject]@{line_no=$n;raw=$line;record=($line|ConvertFrom-Json)}
  }
}
function CopyOriginal([string]$path) {
  $src=Join-Path $repo $path
  if(-not(Test-Path -LiteralPath $src -PathType Leaf)){return $null}
  $dst=Join-Path $raw $path
  New-Item -ItemType Directory -Force -Path (Split-Path $dst -Parent)|Out-Null
  Copy-Item -LiteralPath $src -Destination $dst -Force
  if((Sha $src) -ne (Sha $dst)){throw "copied bytes differ: $path"}
  $dst.Replace('\','/')
}
$schedulePath='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/anchor_20_all30.jsonl'
$prefPath='outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl'
$canonicalPath='outputs/behavioral_preference_pilot_v2/training_corpora_v2/full_disagreement_dominance_dpo.jsonl'
$edgesPath='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/dpo_edges_all30.jsonl'
$anchorsPath='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/safe_detect_anchors_all30.jsonl'
$shaManifestPath='outputs/behavioral_preference_pilot_v2/training_corpora_v2/SHA256SUMS.json'
$schedule=@(Jsonl $schedulePath)
$pref=@{};foreach($x in (Jsonl $prefPath)){if($pref.ContainsKey($x.record.pair_id)){throw "duplicate preference pair: $($x.record.pair_id)"};$pref[$x.record.pair_id]=$x}
$canonical=@{};foreach($x in (Jsonl $canonicalPath)){if($canonical.ContainsKey($x.record.pair_id)){throw "duplicate canonical pair: $($x.record.pair_id)"};$canonical[$x.record.pair_id]=$x}
$edges=@{};foreach($x in (Jsonl $edgesPath)){if($edges.ContainsKey($x.record.pair_id)){throw "duplicate edge: $($x.record.pair_id)"};$edges[$x.record.pair_id]=$x}
$anchors=@{};foreach($x in (Jsonl $anchorsPath)){if($anchors.ContainsKey($x.record.example_id)){throw "duplicate anchor: $($x.record.example_id)"};$anchors[$x.record.example_id]=$x}
$declared=Get-Content $shaManifestPath -Raw|ConvertFrom-Json
$paths=[System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
foreach($x in $schedule){foreach($field in @('prompt_path','response_path','chosen_path','rejected_path')){$v=$x.record.$field;if($v){[void]$paths.Add([string]$v)}}}
$files=[System.Collections.Generic.List[object]]::new()
$fileMap=@{}
foreach($path in ($paths|Sort-Object)){
  $src=Join-Path $repo $path
  $exists=Test-Path -LiteralPath $src -PathType Leaf
  $hash=if($exists){Sha $src}else{$null}
  $expected=$declared.$path
  $status=if(-not $exists){'MISSING'}elseif(-not $expected){'NO_DECLARED_HASH'}elseif($hash -ne $expected){'HASH_MISMATCH'}else{'VERIFIED'}
  $copy=if($exists){CopyOriginal $path}else{$null}
  $record=[pscustomobject]@{path=$path;absolute_path=$src;status=$status;bytes=if($exists){(Get-Item -LiteralPath $src).Length}else{$null};sha256=$hash;declared_sha256=$expected;raw_copy=$copy}
  $files.Add($record);$fileMap[$path]=$record
}
$files|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'training_text_164_inventory.csv')
$mappings=[System.Collections.Generic.List[object]]::new()
$issues=[System.Collections.Generic.List[object]]::new()
$sourceAssets=[System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
foreach($x in $schedule){
  $r=$x.record;$kind=$r.record_type
  $source=$null;$prefLine=$null;$prefHash=$null;$canonicalLine=$null;$edgeLine=$null;$anchorLine=$null;$originEvidence=$null;$chosenEvidence=$null;$rejectedEvidence=$null;$sourceStatus='VERIFIED'
  if($kind -eq 'dpo_edge'){
    $source=$edges[$r.pair_id];$pr=$pref[$r.pair_id];$cr=$canonical[$r.pair_id]
    if(-not $source -or -not $pr -or -not $cr){$sourceStatus='MISSING_UPSTREAM'}
    else{
      $edgeLine=$source.line_no;$prefLine=$pr.line_no;$canonicalLine=$cr.line_no
      $prefHash=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($pr.raw))).ToLowerInvariant()
      if($source.record.source_pair_sha256 -ne $prefHash -or $r.source_pair_sha256 -ne $prefHash){$sourceStatus='SOURCE_PAIR_HASH_MISMATCH'}
      foreach($field in @('chosen_id','rejected_id','parent_bug_id')){if($r.$field -ne $source.record.$field -or $r.$field -ne $pr.record.$field -or $r.$field -ne $cr.record.$field){$sourceStatus='FIELD_MISMATCH'}}
      foreach($field in @('prompt_path','chosen_path','rejected_path')){if($r.$field -ne $source.record.$field -or $r.$field -ne $cr.record.$field){$sourceStatus='TEXT_PATH_MISMATCH'}}
      [void]$sourceAssets.Add($pr.record.chosen_generation_evidence_path)
      [void]$sourceAssets.Add($pr.record.rejected_generation_evidence_path)
      $chosenEvidence=$pr.record.chosen_generation_evidence_path
      $rejectedEvidence=$pr.record.rejected_generation_evidence_path
      foreach($side in @('chosen','rejected')){
        $ep=$pr.record."${side}_generation_evidence_path";$eh=$pr.record."${side}_generation_evidence_sha256"
        if(-not(Test-Path -LiteralPath $ep -PathType Leaf)){$sourceStatus='MISSING_GENERATION_EVIDENCE'}
        elseif((Sha $ep) -ne $eh){$sourceStatus='GENERATION_EVIDENCE_HASH_MISMATCH'}
        foreach($suffix in @('prompt','sva')){
          $op=$pr.record."${side}_${suffix}_path";$oh=$pr.record."${side}_${suffix}_sha256"
          if($op){[void]$sourceAssets.Add($op);if(-not(Test-Path -LiteralPath $op -PathType Leaf)){$sourceStatus='MISSING_ORIGIN_ASSET'}elseif((Sha $op) -ne $oh){$sourceStatus='ORIGIN_ASSET_HASH_MISMATCH'}}
        }
      }
    }
  }elseif($kind -eq 'sft_anchor'){
    $source=$anchors[$r.example_id]
    if(-not $source){$sourceStatus='MISSING_UPSTREAM'}
    else{
      $anchorLine=$source.line_no
      foreach($field in @('example_id','parent_bug_id','prompt_path','response_path')){if($r.$field -ne $source.record.$field){$sourceStatus='FIELD_MISMATCH'}}
      $originEvidence="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$($r.parent_bug_id)/slot_$($r.example_id.Split('_')[-1])/attempt_01/evidence.json"
      if(-not(Test-Path -LiteralPath $originEvidence -PathType Leaf)){$sourceStatus='MISSING_GENERATION_EVIDENCE'}else{[void]$sourceAssets.Add($originEvidence)}
    }
  }else{$sourceStatus='UNKNOWN_RECORD_TYPE'}
  $textPaths=if($kind -eq 'sft_anchor'){@($r.prompt_path,$r.response_path)}else{@($r.prompt_path,$r.chosen_path,$r.rejected_path)}
  foreach($p in $textPaths){if(-not $fileMap[$p] -or $fileMap[$p].status -ne 'VERIFIED'){$sourceStatus='TEXT_NOT_VERIFIED'}}
  if($sourceStatus -ne 'VERIFIED'){$issues.Add([pscustomobject]@{schedule_line=$x.line_no;record_id=if($kind -eq 'sft_anchor'){$r.example_id}else{$r.pair_id};status=$sourceStatus})}
  $mappings.Add([pscustomobject]@{
    schedule_line=$x.line_no;record_type=$kind;record_id=if($kind -eq 'sft_anchor'){$r.example_id}else{$r.pair_id};parent_bug_id=$r.parent_bug_id
    provenance_class=if($r.example_id -match '_slot_08$' -or $r.chosen_id -match '_slot_08$' -or $r.rejected_id -match '_slot_08$'){'MIXED_SYNTHETIC_CONTROL'}else{'NATURAL_ONLY'}
    objective_bucket=$r.objective_bucket;loss_tokens=$r.loss_tokens;prompt_path=$r.prompt_path;prompt_sha256=$fileMap[$r.prompt_path].sha256
    response_path=$r.response_path;response_sha256=if($r.response_path){$fileMap[$r.response_path].sha256}else{$null}
    chosen_id=$r.chosen_id;chosen_path=$r.chosen_path;chosen_sha256=if($r.chosen_path){$fileMap[$r.chosen_path].sha256}else{$null}
    rejected_id=$r.rejected_id;rejected_path=$r.rejected_path;rejected_sha256=if($r.rejected_path){$fileMap[$r.rejected_path].sha256}else{$null}
    preference_path=if($prefLine){$prefPath}else{$null};preference_line=$prefLine;preference_record_sha256=$prefHash
    canonical_pair_path=if($canonicalLine){$canonicalPath}else{$null};canonical_pair_line=$canonicalLine
    edge_pool_path=if($edgeLine){$edgesPath}else{$null};edge_pool_line=$edgeLine
    anchor_pool_path=if($anchorLine){$anchorsPath}else{$null};anchor_pool_line=$anchorLine
    generation_evidence_path=$originEvidence;chosen_generation_evidence_path=$chosenEvidence;rejected_generation_evidence_path=$rejectedEvidence;trainer_branch=if($kind -eq 'sft_anchor'){'sft_anchor: response_path'}else{'dpo_edge: chosen_path+rejected_path'};source_status=$sourceStatus
  })
}
$mappings|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'schedule_4058_lineage.csv')
$issues|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'lineage_issues.csv')
$responseOrigins=@{}
foreach($m in $mappings){
  foreach($side in @('response','chosen','rejected')){
    $rp=$m."${side}_path";if(-not $rp){continue}
    $id=if($side -eq 'response'){$m.record_id}else{$m."${side}_id"}
    $ep=if($side -eq 'response'){$m.generation_evidence_path}else{$m."${side}_generation_evidence_path"}
    $key="$rp|$id|$ep"
    if(-not $responseOrigins.ContainsKey($key)){$responseOrigins[$key]=[pscustomobject]@{response_path=$rp;candidate_id=$id;evidence_path=$ep;uses=0}}
    $responseOrigins[$key].uses++
  }
}
$responseChecks=[System.Collections.Generic.List[object]]::new()
foreach($item in ($responseOrigins.Values|Sort-Object response_path,candidate_id)){
  $rp=$item.response_path;$ep=$item.evidence_path;$body=[System.IO.File]::ReadAllText((Join-Path $repo $rp),[System.Text.Encoding]::UTF8)
  $status='VERIFIED';$eh=$null
  if(-not $ep -or -not(Test-Path -LiteralPath $ep -PathType Leaf)){$status='MISSING_EVIDENCE'}
  else{
    $eh=Sha $ep;$ast=(Get-Content -LiteralPath $ep -Raw|ConvertFrom-Json).ast
    $keys=@('antecedent_signal','antecedent_polarity','consequent_signal','implication','relation')
    $obj=[ordered]@{};foreach($k in $keys){$obj[$k]=$ast.$k}
    $expected=ConvertTo-Json -InputObject $obj -Compress -Depth 4
    if($body -cne $expected){$status='RESPONSE_AST_OR_SERIALIZATION_MISMATCH'}
  }
  $responseChecks.Add([pscustomobject]@{candidate_id=$item.candidate_id;response_path=$rp;response_bytes=(Get-Item -LiteralPath $rp).Length;response_sha256=Sha $rp;generation_evidence_path=$ep;generation_evidence_sha256=$eh;schedule_uses=$item.uses;canonical_status=$status})
}
$responseChecks|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'canonical_response_origin_validation.csv')
$assets=@($schedulePath,$prefPath,$canonicalPath,$edgesPath,$anchorsPath,$shaManifestPath,
  'scripts/audit_phase_b_edge_lineage_20260922.ps1',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/phase_b_refit_all30_v1_frozen.json',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/balanced_behavioral_objective_v1_frozen.json',
  'src/freeze_and_materialize_balanced_behavioral_objective.py','src/materialize_balanced_behavioral_phase_b.py',
  'src/materialize_pilot_v2_ast_training.py','src/materialize_pilot_v2_corrected_protocol.py',
  'src/materialize_balanced_behavioral_token_schedules.py','src/train_balanced_behavioral_phase_b_qwen3.py',
  'src/train_balanced_behavioral_dev_qwen3.py','scripts/run_balanced_behavioral_phase_b_training_v1.sh',
  'src/generate_balanced_behavioral_phase_b_ood.py',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/query_manifest.json',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/generation_run_manifest.json',
  'outputs/phase_b_ood_eval_v1/pre_execution_audit.json')
$assets+=@($sourceAssets|Where-Object {$_})
$assets+=@(Get-ChildItem -LiteralPath $repo -File -Filter '*phase_b*.log'|ForEach-Object Name)
$assets+=@('outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/train_log.jsonl',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/training_result.json',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/latest_checkpoint.txt',
  'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/checkpoint-004058/adapter_model.safetensors')
$assetRows=[System.Collections.Generic.List[object]]::new()
foreach($p in ($assets|Where-Object {$_}|Sort-Object -Unique)){
  $src=Join-Path $repo $p;$ok=Test-Path -LiteralPath $src -PathType Leaf
  $assetRows.Add([pscustomobject]@{path=$p;status=if($ok){'FOUND'}else{'MISSING'};bytes=if($ok){(Get-Item -LiteralPath $src).Length}else{$null};sha256=if($ok){Sha $src}else{$null};raw_copy=if($ok){CopyOriginal $p}else{$null}})
}
$assetRows|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'source_scripts_logs_and_missing.csv')
[ordered]@{status=if($issues.Count -eq 0 -and @($files|Where-Object status -ne VERIFIED).Count -eq 0 -and @($responseChecks|Where-Object canonical_status -ne VERIFIED).Count -eq 0){'LINEAGE_PATHS_VERIFIED_EXECUTION_UNPROVEN'}else{'LINEAGE_ISSUES'};schedule_rows=$schedule.Count;unique_training_text_files=$files.Count;verified_training_text_files=@($files|Where-Object status -eq VERIFIED).Count;canonical_response_origin_links=$responseChecks.Count;canonical_response_origin_issues=@($responseChecks|Where-Object canonical_status -ne VERIFIED).Count;lineage_issues=$issues.Count;synthetic_control_schedule_rows=@($mappings|Where-Object provenance_class -eq MIXED_SYNTHETIC_CONTROL).Count;loss_tokens=($schedule|ForEach-Object record|Measure-Object loss_tokens -Sum).Sum;training_execution_status='UNKNOWN: original train_log, training_result, and checkpoint bytes absent';adapter_load_status='DECLARED_BY_MANIFEST_AND_GENERATOR; PHYSICAL_ADAPTER_MISSING';missing_assets=@($assetRows|Where-Object status -eq MISSING|ForEach-Object path)}|ConvertTo-Json -Depth 5|Set-Content -Encoding utf8 (Join-Path $out 'audit_summary.json')
Get-Content (Join-Path $out 'audit_summary.json') -Raw
