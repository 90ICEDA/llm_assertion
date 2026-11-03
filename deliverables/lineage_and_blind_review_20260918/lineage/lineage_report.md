# Existing experiment lineage audit

Scope: behavioral-preference Pilot v2 corrected data through the final Phase-B OOD evaluation. This audit reads and copies existing artifacts only. No training, generation, probe, or evaluation was rerun.

## Traceable chain

1. **Preference source.** The v1 disagreement-guided dominance pairs and dominance audit are present and hashed. Pair rows bind `chosen_id`, `rejected_id`, prompt path, response path, parent, and policy.
2. **Training text.** Pilot-v2 `training_corpora_v2` is present. It converts candidate outputs to canonical five-key compact JSON AST responses and freezes EOS supervision. The corpus files and their repository SHA manifest are preserved under `raw_evidence`.
3. **Actual training batch.** Phase B does not resample the corpus in the trainer. `anchor_20_all30.jsonl` is the materialized, ordered 4,058-step batch. The frozen manifest binds it to SHA-256 `05dfe1dbe0a9c18309ab66b3193ab76f19efd0c052ecc4c3e4c1e5ab039f1df0`, 245,760 response-loss tokens, 30 parents, and four objective buckets. Each row contains the actual prompt/response or chosen/rejected paths and loss-token count.
4. **Trainer/config.** `train_balanced_behavioral_phase_b_qwen3.py` validates the frozen schedule then delegates to `train_balanced_behavioral_dev_qwen3.py`. The latter executes rows once in file order with batch size 1, 4-bit NF4 QLoRA, LoRA r=8/alpha=16/dropout=.05 on `q_proj` and `v_proj`, AdamW lr=1e-4, DPO beta=.1, exact all-ones attention mask, EOS supervision, and 512-token maximum. The launcher requests `anchor_20_all30 --resume`.
5. **Base checkpoint.** `outputs/checkpoints/Qwen3-8B/checkpoint_manifest.json` is present and copied. The trainer and generator both use this local base path.
6. **Adapter/checkpoint.** The frozen OOD query manifest names `checkpoint-004058`, adapter SHA-256 `c1bc4c54f64a50acbdec3288de3325cffb6a05ed61a94a3c7a6df0ffd34bdb3a`, and training-result SHA-256 `73ae52fa074e081ee2b4a87fbbb6caaea6dc773723b42856014572ec8b2d7c65`. However, the adapter directory and all local training completion/log pointers are absent. They are not reconstructible from generated responses.
7. **Model actually loaded for generation.** `generate_balanced_behavioral_phase_b_ood.py` first hashes `adapter_model.safetensors`, loads the local Qwen3-8B base with 4-bit NF4, then calls `PeftModel.from_pretrained(base, ROOT/adapter_path, is_trainable=False)`. Per-query generation evidence repeats the same adapter path/hash. This proves the intended and historically recorded load binding, but current byte-level replay is blocked by the missing adapter.
8. **Evaluation.** The evaluation stage consumes the already rendered/generated assertion artifacts; it does not load a language model. `outputs/phase_b_ood_eval_v1/pre_execution_audit.json` and evaluation records bind the same adapter hash indirectly through generation evidence.

## Explicit MISSING artifacts

- `.../formal_training_v1/anchor_20_all30/training_result.json`
- `.../formal_training_v1/anchor_20_all30/train_log.jsonl`
- `.../formal_training_v1/anchor_20_all30/latest_checkpoint.txt`
- `.../formal_training_v1/anchor_20_all30/checkpoint-004058/` (including `adapter_model.safetensors`)

Therefore the preference → canonical text → exact scheduled batch → trainer/config portion is locally auditable, and the evaluation's declared adapter binding is consistent across manifests/evidence, but the physical adapter/checkpoint and original training log are **MISSING**. No claim of full end-to-end reproducibility should be made from this checkout.
