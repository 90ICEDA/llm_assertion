$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$Out = "deliverables/lineage_and_blind_review_20260918/blind_review/raw_evidence"
New-Item -ItemType Directory -Force -Path $Out | Out-Null
$parents = @(
  "case115_prim_edge_both_edges_collapsed",
  "case505_axis_stat_counter_frame_pulse_early",
  "case463_axis_frame_join_port_skip",
  "case506_axis_crosspoint_simultaneous_source_priority",
  "case457_cc_delta_counter_load_enable_priority",
  "case478_axis_srl_register_ready_recovery"
)
$inventory=@()
foreach($parent in $parents) {
  $dest=Join-Path $Out $parent; New-Item -ItemType Directory -Force -Path $dest | Out-Null
  $evidence="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$parent/slot_01/attempt_01/evidence.json"
  $doc=Get-Content -LiteralPath $evidence -Raw|ConvertFrom-Json
  $wsl=Split-Path $doc.runs.correct.command[-3] -Parent
  $rel=$wsl -replace '^\\mnt\\d\\AssertionForge-main1\\',''
  $case=Join-Path (Get-Location) $rel
  foreach($name in @("buggy.v","correct.v","mutation.diff","spec.md","golden.sva","STIMULUS_NOTES.md","case_metadata.json")) {
    $src=Join-Path $case $name
    if(Test-Path -LiteralPath $src) { Copy-Item -LiteralPath $src -Destination (Join-Path $dest $name) -Force }
  }
  for($slot=1;$slot -le 8;$slot++) {
    $src="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$parent/slot_$($slot.ToString('00'))/attempt_01/evidence.json"
    $name="slot_$($slot.ToString('00'))_evidence.json"
    Copy-Item -LiteralPath $src -Destination (Join-Path $dest $name) -Force
  }
}
Get-ChildItem -LiteralPath $Out -Recurse -File | ForEach-Object {
  [pscustomobject]@{
    path=$_.FullName.Substring((Get-Location).Path.Length+1).Replace('\','/')
    bytes=$_.Length
    sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
    provenance_class=if($_.Name -eq 'slot_08_evidence.json'){'synthetic_control'}elseif($_.Name -match '^slot_0[1-7]_'){'natural'}else{'repair_context'}
  }
} | Export-Csv -NoTypeInformation -Encoding utf8 "deliverables/lineage_and_blind_review_20260918/blind_review/raw_evidence_inventory.csv"
