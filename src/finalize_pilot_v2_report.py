from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "outputs/behavioral_preference_pilot_v2"
TOP1 = PILOT / "frozen_top1_ast_v2"
EVAL = TOP1 / "execution_evaluation_v1"
OUT = PILOT / "final_report_v2"
NON_BEHAVIOR = ("ordinary_sft", "pass_count_dpo", "scalar_score_dpo")
FULL = "full_disagreement_dominance_dpo"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(value):
    return "N/A" if value is None else f"{100 * value:.2f}%"


def main() -> None:
    metrics_path = EVAL / "frozen_top1_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    generation = list((TOP1 / "generations").rglob("evidence.json"))
    evaluations = list((EVAL / "records").rglob("evaluation.json"))
    if len(generation) != 240 or len(evaluations) != 240:
        raise RuntimeError("incomplete frozen Top-1 evidence")
    decisions = {}
    for split in ("unseen_parent", "unseen_bug_family"):
        methods = metrics["summaries"][split]["methods"]
        best_scs = max(methods[name]["SCS@1"] for name in NON_BEHAVIOR)
        tied = [name for name in NON_BEHAVIOR if methods[name]["SCS@1"] == best_scs]
        full = methods[FULL]
        delta = full["SCS@1"] - best_scs
        fixed_safe_floor = max(methods[name]["Fixed-Safe"] for name in tied)
        decisions[split] = {
            "strongest_non_behavior_scs": best_scs,
            "strongest_non_behavior_methods": tied,
            "full_scs": full["SCS@1"],
            "scs_delta": delta,
            "required_delta": 0.05,
            "scs_gate": delta >= 0.05,
            "full_fixed_safe": full["Fixed-Safe"],
            "fixed_safe_reference": fixed_safe_floor,
            "fixed_safe_no_decrease": full["Fixed-Safe"] >= fixed_safe_floor,
        }
    decision = "GO" if all(x["scs_gate"] and x["fixed_safe_no_decrease"] for x in decisions.values()) else "NO-GO"
    hashes = {
        "query_manifest": sha(TOP1 / "query_manifest.json"),
        "pre_generation_leakage_audit": sha(TOP1 / "pre_generation_leakage_audit.json"),
        "generation_hash_manifest": sha(TOP1 / "top1_artifact_hashes.sha256"),
        "pre_execution_audit": sha(EVAL / "pre_execution_audit.json"),
        "metrics": sha(metrics_path),
        "evaluation_hash_manifest": sha(EVAL / "evaluation_artifact_hashes.json"),
        "smoke_validation_hash_manifest": sha(PILOT / "ast_smoke_v2_validation/validation_artifact_hashes.sha256"),
    }
    report = {
        "status": "complete",
        "decision": decision,
        "generation_count": len(generation),
        "evaluation_count": len(evaluations),
        "project_ood": "structural N/A; all three frozen projects occur in Pilot training",
        "go_no_go": decisions,
        "summaries": metrics["summaries"],
        "audits": {
            "all_failures_retained_in_denominator": True,
            "heldout_outcomes_used_for_generation": False,
            "repair": False,
            "reranker": False,
            "selector": False,
            "hashes": hashes,
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    json_path = OUT / "pilot_v2_final_report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Behavioral Preference Pilot v2 — Final Report", "", f"Status: **{decision}**.", "",
        "## Frozen Top-1", "", "| Split | Method | SCS@1 | Fixed-Safe | Target Detect | Family Recall | Non-vacuity | TOR | Compile |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for split in ("unseen_parent", "unseen_bug_family"):
        for method, values in metrics["summaries"][split]["methods"].items():
            lines.append(f"| {split} | {method} | {pct(values['SCS@1'])} | {pct(values['Fixed-Safe'])} | {pct(values['Target Detect'])} | {pct(values['Family Recall'])} | {pct(values['Non-vacuity'])} | {pct(values['TOR'])} | {pct(values['compile_rate'])} |")
    lines += ["", "## Go/no-go", ""]
    for split, value in decisions.items():
        lines.append(f"- {split}: full SCS@1 {pct(value['full_scs'])}; strongest non-behavior SCS@1 {pct(value['strongest_non_behavior_scs'])}; delta {100*value['scs_delta']:+.2f}pp; +5pp gate={'PASS' if value['scs_gate'] else 'FAIL'}; Fixed-Safe gate={'PASS' if value['fixed_safe_no_decrease'] else 'FAIL'}.")
    lines += ["", "Project-OOD is structural N/A because Pilot training covers all three frozen projects.", "", "All 240 one-shot generations remain in the denominator; no repair, reranking, selector, deletion, or held-out outcomes were used.", ""]
    (OUT / "pilot_v2_final_report.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "SHA256SUMS.json").write_text(json.dumps({"pilot_v2_final_report.json": sha(json_path), "pilot_v2_final_report.md": sha(OUT / "pilot_v2_final_report.md")}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "decision": decision, "go_no_go": decisions, "report": str(json_path.relative_to(ROOT)).replace("\\", "/")}, sort_keys=True))


if __name__ == "__main__":
    main()
