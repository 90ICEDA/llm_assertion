$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$out='deliverables/behavioral_provenance_correction_20260922'
New-Item -ItemType Directory -Force $out|Out-Null
function Sha($p){(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant()}
function Origin($id){if(-not $id){throw 'missing candidate id'};if($id -match '(?:__v3_)?slot_0?8$'){return 'synthetic control'};if($id -match '(?:__v3_)?slot_0?[1-7]$'){return 'natural'};throw "unrecognized candidate id: $id"}
function Label($row){
  if($row.example_id){return Origin $row.example_id}
  if($row.chosen_id -and $row.rejected_id){$a=Origin $row.chosen_id;$b=Origin $row.rejected_id;if($a -eq $b){return $a};return 'mixed'}
  throw 'record has no candidate IDs'
}
$v1='outputs/behavioral_preference_pilot_v1'
$v2='outputs/behavioral_preference_pilot_v2'
$files=@()
$files+=Get-ChildItem "$v1/dominance_pairs_v3" -Filter '*.jsonl' -File
foreach($dir in @("$v1/training_corpora_v2","$v2/training_corpora_v1","$v2/training_corpora_v2","$v2/balanced_behavioral_objective_v1")){$files+=Get-ChildItem $dir -Filter '*.jsonl' -File -Recurse}
$records=[System.Collections.Generic.List[object]]::new()
$summaries=[System.Collections.Generic.List[object]]::new()
foreach($file in ($files|Sort-Object FullName -Unique)){
  $rel=$file.FullName.Substring($root.Length+1).Replace('\','/')
  $n=0;$fileSha=Sha $file.FullName;$counts=@{'natural'=0;'synthetic control'=0;'mixed'=0};$mixedWithControl=0
  foreach($line in [System.IO.File]::ReadLines($file.FullName,[System.Text.Encoding]::UTF8)){
    $n++;if([string]::IsNullOrWhiteSpace($line)){continue};$row=$line|ConvertFrom-Json
    if(-not $row.example_id -and -not $row.chosen_id){continue}
    $label=Label $row;$counts[$label]++
    $hasControl=($label -ne 'natural');if($hasControl){$mixedWithControl++}
    $records.Add([pscustomobject]@{source_path=$rel;source_sha256=$fileSha;line=$n;record_id=if($row.pair_id){$row.pair_id}else{$row.example_id};parent_bug_id=$row.parent_bug_id;chosen_id=$row.chosen_id;chosen_origin=if($row.chosen_id){Origin $row.chosen_id}else{$null};rejected_id=$row.rejected_id;rejected_origin=if($row.rejected_id){Origin $row.rejected_id}else{$null};example_id=$row.example_id;provenance=$label;contains_synthetic_control=$hasControl;record_sha256=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData([System.Text.Encoding]::UTF8.GetBytes($line))).ToLowerInvariant()})
  }
  $summaries.Add([pscustomobject]@{source_path=$rel;source_sha256=$fileSha;rows=$counts['natural']+$counts['synthetic control']+$counts['mixed'];natural=$counts['natural'];synthetic_control=$counts['synthetic control'];mixed=$counts['mixed'];contains_synthetic_control=$mixedWithControl;aggregate_provenance=if($mixedWithControl -eq 0){'natural'}elseif($counts['natural'] -eq 0 -and $counts['mixed'] -eq 0){'synthetic control'}else{'mixed'}})
}
$records|Export-Csv -NoTypeInformation -Encoding utf8 "$out/row_provenance.csv"
$summaries|Export-Csv -NoTypeInformation -Encoding utf8 "$out/source_file_summary.csv"
$phase='outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/anchor_20_all30.jsonl'
$phaseSummary=$summaries|Where-Object source_path -eq $phase
if($phaseSummary.rows -ne 4058 -or $phaseSummary.contains_synthetic_control -ne 729){throw "Phase-B count mismatch: $($phaseSummary|ConvertTo-Json -Compress)"}
$phaseRows=$records|Where-Object { $_.source_path -eq $phase -and $_.contains_synthetic_control }
$phaseRows|Select-Object source_path,line,record_id,parent_bug_id,chosen_id,chosen_origin,rejected_id,rejected_origin,example_id,provenance,record_sha256|Export-Csv -NoTypeInformation -Encoding utf8 "$out/phase_b_729_affected_rows.csv"
$reportRows=[System.Collections.Generic.List[object]]::new()
foreach($version in @('v1','v2')){
  $rp=if($version -eq 'v1'){"$v1/final_report_v1/pilot_v1_final_report.json"}else{"$v2/final_report_v2/pilot_v2_final_report.json"}
  $report=Get-Content $rp -Raw|ConvertFrom-Json
  if($version -eq 'v2'){
    foreach($split in $report.summaries.PSObject.Properties){foreach($method in $split.Value.methods.PSObject.Properties){
      $corpus="$v2/training_corpora_v2/$($method.Name).jsonl";$s=$summaries|Where-Object source_path -eq $corpus
      $reportRows.Add([pscustomobject]@{report_path=$rp;report_sha256=Sha $rp;report_row="summaries.$($split.Name).methods.$($method.Name)";method=$method.Name;source_path=$corpus;source_rows=$s.rows;source_natural=$s.natural;source_synthetic_control=$s.synthetic_control;source_mixed=$s.mixed;training_source_provenance=$s.aggregate_provenance;execution_evidence='historical report retained'})
    }}
  }else{
    foreach($row in $report.probe_ablation.rows){
      $sourcePath="$v1/dominance_pairs_v3/$($row.policy)_dominance_pairs.jsonl";$s=$summaries|Where-Object source_path -eq $sourcePath
      $reportRows.Add([pscustomobject]@{report_path=$rp;report_sha256=Sha $rp;report_row="probe_ablation.rows.$($row.policy)";method=$row.policy;source_path=$sourcePath;source_rows=$s.rows;source_natural=$s.natural;source_synthetic_control=$s.synthetic_control;source_mixed=$s.mixed;training_source_provenance='mixed';execution_evidence='label describes preference/probe source, not trained model; historical report retained'})
    }
    foreach($split in $report.frozen_top1.metrics.summaries.PSObject.Properties){foreach($method in $split.Value.methods.PSObject.Properties){
      $corpus="$v1/training_corpora_v2/$($method.Name).jsonl";$s=$summaries|Where-Object source_path -eq $corpus
      $reportRows.Add([pscustomobject]@{report_path=$rp;report_sha256=Sha $rp;report_row="frozen_top1.metrics.summaries.$($split.Name).methods.$($method.Name)";method=$method.Name;source_path=$corpus;source_rows=$s.rows;source_natural=$s.natural;source_synthetic_control=$s.synthetic_control;source_mixed=$s.mixed;training_source_provenance=$s.aggregate_provenance;execution_evidence='historical report retained'})
    }}
  }
}
$metrics='outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json'
foreach($split in @('unseen_parent','unseen_bug_family','union_overview')){$reportRows.Add([pscustomobject]@{report_path=$metrics;report_sha256=Sha $metrics;report_row="summaries.$split";method='anchor_20_all30';source_path=$phase;source_rows=$phaseSummary.rows;source_natural=$phaseSummary.natural;source_synthetic_control=$phaseSummary.synthetic_control;source_mixed=$phaseSummary.mixed;training_source_provenance='mixed';execution_evidence='schedule verified; original training log/checkpoint MISSING; completion UNKNOWN'})}
$devReport="$v2/balanced_behavioral_objective_v1/dev_top1_v1/execution_evaluation_v1/dev_metrics_and_selection.json"
$dev=Get-Content $devReport -Raw|ConvertFrom-Json
foreach($variant in $dev.summaries.PSObject.Properties){
  $sourcePath=if($variant.Name -like 'anchor_*'){"$v2/balanced_behavioral_objective_v1/token_schedules_v1/$($variant.Name).jsonl"}else{"$v2/training_corpora_v2/$($variant.Name).jsonl"}
  $s=$summaries|Where-Object source_path -eq $sourcePath
  $reportRows.Add([pscustomobject]@{report_path=$devReport;report_sha256=Sha $devReport;report_row="summaries.$($variant.Name)";method=$variant.Name;source_path=$sourcePath;source_rows=$s.rows;source_natural=$s.natural;source_synthetic_control=$s.synthetic_control;source_mixed=$s.mixed;training_source_provenance=$s.aggregate_provenance;execution_evidence='historical report retained'})
}
$reportRows|Export-Csv -NoTypeInformation -Encoding utf8 "$out/report_row_corrections.csv"
$summaries|Where-Object {$_.source_path -like '*anchor_20_all30.jsonl' -or $_.source_path -like '*full_disagreement_dominance_dpo.jsonl'}|Format-Table source_path,rows,natural,synthetic_control,mixed,contains_synthetic_control -AutoSize
