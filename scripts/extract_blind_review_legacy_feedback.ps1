$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$Out="deliverables/lineage_and_blind_review_20260918/blind_review"
$manifest=Get-Content "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json" -Raw|ConvertFrom-Json
$ids=@(
 "case505_axis_stat_counter_frame_pulse_early__v3_slot_06",
 "case505_axis_stat_counter_frame_pulse_early__v3_slot_07"
)
$feedback=@($manifest.candidate_policy_records|Where-Object candidate_id -in $ids)
$feedback|ConvertTo-Json -Depth 12|Set-Content -Encoding utf8 "$Out/legacy_feedback_snapshot.json"
$schedule="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/anchor_20_all30.jsonl"
$hits=Get-Content $schedule|ForEach-Object {$_|ConvertFrom-Json}|Where-Object { $_.example_id -in $ids -or $_.chosen_id -in $ids -or $_.rejected_id -in $ids }
$hits|ConvertTo-Json -Depth 8|Set-Content -Encoding utf8 "$Out/training_batch_case505_snapshot.json"
[ordered]@{
  legacy_feedback_source="outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json"
  feedback_records=$feedback.Count
  slot_06_anchor_rows=@($hits|Where-Object {$_.record_type -eq 'sft_anchor' -and $_.example_id -eq $ids[0]}).Count
  slot_07_anchor_rows=@($hits|Where-Object {$_.record_type -eq 'sft_anchor' -and $_.example_id -eq $ids[1]}).Count
  slot_06_all_schedule_rows=@($hits|Where-Object {$_.example_id -eq $ids[0] -or $_.chosen_id -eq $ids[0] -or $_.rejected_id -eq $ids[0]}).Count
  slot_07_all_schedule_rows=@($hits|Where-Object {$_.example_id -eq $ids[1] -or $_.chosen_id -eq $ids[1] -or $_.rejected_id -eq $ids[1]}).Count
  note="Snapshots extracted only after prefeedback_freeze.json was written."
}|ConvertTo-Json|Set-Content -Encoding utf8 "$Out/postfeedback_summary.json"
