$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))

$Out = "deliverables/lineage_and_blind_review_20260918/lineage"
$Raw = Join-Path $Out "raw_evidence"
New-Item -ItemType Directory -Force -Path $Raw | Out-Null

$items = @(
    @{stage="preference"; path="outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/dominance_audit.json"},
    @{stage="preference"; path="outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/disagreement_guided_dominance_pairs.jsonl"},
    @{stage="training_text"; path="outputs/behavioral_preference_pilot_v2/training_corpora_v2/full_disagreement_dominance_dpo.jsonl"},
    @{stage="training_text"; path="outputs/behavioral_preference_pilot_v2/training_corpora_v2/formal_training_v2_frozen.json"},
    @{stage="training_text"; path="outputs/behavioral_preference_pilot_v2/training_corpora_v2/SHA256SUMS.json"},
    @{stage="actual_training_batch"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/anchor_20_all30.jsonl"},
    @{stage="actual_training_batch"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/phase_b_refit_all30_v1_frozen.json"},
    @{stage="actual_training_batch"; path="src/freeze_and_materialize_balanced_behavioral_objective.py"},
    @{stage="actual_training_batch"; path="src/materialize_balanced_behavioral_phase_b.py"},
    @{stage="trainer_config"; path="src/train_pilot_qwen3.py"},
    @{stage="trainer_config"; path="src/train_pilot_v2_corrected_qwen3.py"},
    @{stage="trainer_config"; path="src/train_balanced_behavioral_dev_qwen3.py"},
    @{stage="trainer_config"; path="src/train_balanced_behavioral_phase_b_qwen3.py"},
    @{stage="trainer_config"; path="scripts/run_balanced_behavioral_phase_b_training_v1.sh"},
    @{stage="trainer_config"; path="outputs/checkpoints/Qwen3-8B/checkpoint_manifest.json"},
    @{stage="adapter_checkpoint"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/training_result.json"},
    @{stage="adapter_checkpoint"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/train_log.jsonl"},
    @{stage="adapter_checkpoint"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/latest_checkpoint.txt"},
    @{stage="adapter_checkpoint"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/formal_training_v1/anchor_20_all30/checkpoint-004058"},
    @{stage="evaluation_model_load"; path="src/generate_balanced_behavioral_phase_b_ood.py"},
    @{stage="evaluation_model_load"; path="src/freeze_balanced_behavioral_phase_b_adapter.py"},
    @{stage="evaluation_model_load"; path="src/materialize_balanced_behavioral_phase_b_ood.py"},
    @{stage="evaluation_model_load"; path="src/evaluate_balanced_behavioral_phase_b_ood.py"},
    @{stage="evaluation_model_load"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/query_manifest.json"},
    @{stage="evaluation_model_load"; path="outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1/frozen_ood_top1_v1/generation_run_manifest.json"},
    @{stage="evaluation_model_load"; path="outputs/phase_b_ood_eval_v1/pre_execution_audit.json"}
)

$records = foreach ($item in $items) {
    $p = $item.path
    if (-not (Test-Path -LiteralPath $p)) {
        [pscustomobject]@{stage=$item.stage; status="MISSING"; path=$p; type=$null; bytes=$null; sha256=$null; copied_to=$null}
        continue
    }
    $entry = Get-Item -LiteralPath $p
    if ($entry.PSIsContainer) {
        $files = @(Get-ChildItem -LiteralPath $p -Recurse -File)
        $listing = $files | ForEach-Object {
            [pscustomobject]@{path=$_.FullName.Substring((Get-Location).Path.Length+1).Replace('\','/'); bytes=$_.Length; sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()}
        }
        $listPath = Join-Path $Out (($item.stage + "_directory_listing.json") -replace '[^A-Za-z0-9_.-]','_')
        $listing | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 $listPath
        [pscustomobject]@{stage=$item.stage; status="FOUND"; path=$p; type="directory"; bytes=($files|Measure-Object Length -Sum).Sum; sha256="SEE_DIRECTORY_LISTING"; copied_to=$listPath.Replace('\','/')}
    } else {
        $hash=(Get-FileHash -Algorithm SHA256 -LiteralPath $p).Hash.ToLowerInvariant()
        $safe=($p -replace '[:\\/]','__')
        $dest=Join-Path $Raw $safe
        Copy-Item -LiteralPath $p -Destination $dest -Force
        [pscustomobject]@{stage=$item.stage; status="FOUND"; path=$p.Replace('\','/'); type="file"; bytes=$entry.Length; sha256=$hash; copied_to=$dest.Replace('\','/')}
    }
}

$records | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $Out "artifact_inventory.json")
$records | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $Out "artifact_inventory.csv")
$summary = [ordered]@{
    audit_date="2026-09-18"
    policy="read-only artifact audit; no retraining"
    found=($records|Where-Object status -eq "FOUND").Count
    missing=($records|Where-Object status -eq "MISSING").Count
    missing_paths=@($records|Where-Object status -eq "MISSING"|ForEach-Object path)
}
$summary | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $Out "summary.json")
$summary | ConvertTo-Json -Depth 5
