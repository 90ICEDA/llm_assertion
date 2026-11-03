$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$out='deliverables/blind_reaudit_20260921'
$rows=@(Import-Csv (Join-Path $out 'independent_judgments_frozen.csv'))
$prov=@(Import-Csv (Join-Path $out 'candidate_provenance.csv') | Where-Object {$_.class -eq 'natural_model_response'})
if($rows.Count -ne 28 -or $prov.Count -ne 28){throw 'expected exactly 28 natural judgments and provenance rows'}
foreach($r in $rows){if(@($prov|Where-Object candidate_id -eq $r.candidate_id).Count -ne 1){throw "unverified natural candidate: $($r.candidate_id)"}}
$pairs=[System.Collections.Generic.List[object]]::new()
foreach($g in ($rows|Group-Object parent_bug_id)){
  $rr=@($g.Group|Sort-Object {[int]$_.slot})
  for($i=0;$i-lt$rr.Count;$i++){for($j=$i+1;$j-lt$rr.Count;$j++){
    $a=$rr[$i];$b=$rr[$j]
    $relation=if($a.judgment -eq 'UNKNOWN' -or $b.judgment -eq 'UNKNOWN'){'UNKNOWN'}elseif($a.judgment -eq 'PARTIAL' -and $b.judgment -eq 'MISMATCH'){'A_BETTER'}elseif($b.judgment -eq 'PARTIAL' -and $a.judgment -eq 'MISMATCH'){'B_BETTER'}else{'INCOMPARABLE'}
    $pairs.Add([pscustomobject]@{parent_bug_id=$g.Name;candidate_a=$a.candidate_id;candidate_b=$b.candidate_id;relation=$relation;basis='repair-relevance only; no feedback or probe outcome used'})
  }}
}
$pairs|Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'pairwise_judgments_frozen.csv')
$paths=@('selected_parents.csv','sampling_and_provenance_manifest.json','pre_feedback_file_inventory.csv','candidate_provenance.csv','repair_requirements_frozen.md','independent_judgments_frozen.csv','pairwise_judgments_frozen.csv')
$seal=@(foreach($p in $paths){$f=Join-Path $out $p;[pscustomobject]@{path=$f.Replace('\','/');sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $f).Hash.ToLowerInvariant();bytes=(Get-Item $f).Length}})
$seal|ConvertTo-Json -Depth 4|Set-Content -Encoding utf8 (Join-Path $out 'PRE_FEEDBACK_FREEZE.json')
[ordered]@{frozen_at=(Get-Date).ToUniversalTime().ToString('o');policy='No legacy feedback opened for this new selected batch before this seal; old six-parent batch excluded. Reviewer previously exposed to old feedback for other parents, so human-memory blinding is not claimed.';natural=28;synthetic_controls_excluded=4;pairwise_rows=$pairs.Count;seal_sha256=(Get-FileHash -Algorithm SHA256 (Join-Path $out 'PRE_FEEDBACK_FREEZE.json')).Hash.ToLowerInvariant()}|ConvertTo-Json -Depth 5|Set-Content -Encoding utf8 (Join-Path $out 'PRE_FEEDBACK_FREEZE_META.json')
