from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from trace_representation_contract import case_contract_inputs, validate_temporal_relation_abstraction
from trace_router import canonical_hash


ROOT = Path(__file__).resolve().parents[1]
ARM_METHOD = {
    "raw": "spec_rtl_raw_trace",
    "temporal": "spec_rtl_temporal_relation_abstraction",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def arm_budget(route: str, total_k: int) -> dict[str, int]:
    if route == "raw": return {"raw": total_k}
    if route == "temporal": return {"temporal": total_k}
    if route != "both": raise ValueError(f"Unsupported route: {route}")
    if total_k < 2: raise ValueError("route=both requires total k >= 2")
    return {"raw": (total_k + 1) // 2, "temporal": total_k // 2}


def main() -> None:
    parser = argparse.ArgumentParser(description="Dispatch frozen trace-router decisions to real raw/temporal generation calls.")
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument("--routing", default=str(ROOT / "outputs/trace_router/test_routing.csv"))
    parser.add_argument("--policy", default=str(ROOT / "outputs/trace_router/locked_policy.json"))
    parser.add_argument("--temporal-summaries", default=str(ROOT / "outputs/formal_temporal_abstractions/temporal_abstractions.json"))
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/trace_router_dispatch"))
    parser.add_argument("--total-k", type=int, default=2)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--generate-only", action="store_true", help="With --execute, call models and persist pending candidates without WSL evaluation.")
    args = parser.parse_args()

    cases_root, routing_path, policy_path = Path(args.root).resolve(), Path(args.routing).resolve(), Path(args.policy).resolve()
    temporal_path, output_dir = Path(args.temporal_summaries).resolve(), Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if not policy.get("locked") or policy.get("policy_sha256") != canonical_hash(policy):
        raise RuntimeError("Refusing dispatch: policy is unlocked or its SHA-256 does not match")
    if int(policy.get("k", -1)) != args.total_k:
        raise RuntimeError(f"Budget mismatch: policy k={policy.get('k')} but dispatcher total-k={args.total_k}")
    if args.execute and policy.get("data_status") != "formal_compliant":
        raise RuntimeError("Refusing real generation: locked policy is not marked formal_compliant")

    with routing_path.open(encoding="utf-8-sig", newline="") as handle:
        routing = list(csv.DictReader(handle))
    if not routing: raise RuntimeError("Routing file is empty")
    if any(row.get("policy_sha256") != policy["policy_sha256"] for row in routing):
        raise RuntimeError("Routing rows do not match the locked policy SHA-256")
    routing_hash, temporal_hash = file_sha256(routing_path), file_sha256(temporal_path)
    temporal_rows = json.loads(temporal_path.read_text(encoding="utf-8"))
    temporal_lookup = {row["case_id"]: row["abstracted_summary"] for row in temporal_rows}
    manifest = json.loads((cases_root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    meta_lookup = {row["name"]: row for row in manifest}

    required_temporal = {row["case_id"] for row in routing if row["route"] in {"temporal", "both"}}
    contract_failures = {}
    for case_id in sorted(required_temporal):
        if case_id not in temporal_lookup:
            contract_failures[case_id] = ["missing_temporal_abstraction"]
            continue
        errors = validate_temporal_relation_abstraction(
            temporal_lookup[case_id], **case_contract_inputs(cases_root / case_id, meta_lookup.get(case_id, {}))
        )
        if errors: contract_failures[case_id] = errors
    if contract_failures:
        raise RuntimeError(f"Temporal contract gate failed: {json.dumps(contract_failures, ensure_ascii=False)}")

    plan_rows = []
    for row in routing:
        for arm, arm_k in arm_budget(row["route"], args.total_k).items():
            plan_rows.append({
                "model": row["model"], "case_id": row["case_id"], "parent_bug_id": row["parent_bug_id"],
                "route": row["route"], "representation": arm, "method": ARM_METHOD[arm],
                "arm_k": arm_k, "total_k": args.total_k, "policy_sha256": policy["policy_sha256"],
                "routing_sha256": routing_hash, "temporal_summaries_sha256": temporal_hash,
                "temporal_contract": "passed" if arm == "temporal" else "not_applicable",
                "execution_status": "planned",
            })
    plan_path = output_dir / "generation_dispatch_plan.csv"
    with plan_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(plan_rows[0])); writer.writeheader(); writer.writerows(plan_rows)

    grouped: dict[tuple[str, str, int], list[str]] = defaultdict(list)
    for row in plan_rows: grouped[(row["model"], row["method"], row["arm_k"])].append(row["case_id"])
    commands = []
    generation_dir = output_dir / "generated"
    for (model, method, arm_k), case_ids in sorted(grouped.items()):
        command = [
            sys.executable, str(ROOT / "src/run_trace_representation_ablation.py"),
            "--root", str(cases_root), "--output-dir", str(generation_dir),
            "--temporal-summary-json", str(temporal_path), "--model", model,
            "--method", method, "--candidates-per-cell", str(arm_k),
        ]
        for case_id in sorted(case_ids): command.extend(["--case", case_id])
        if args.generate_only:
            command.append("--generate-only")
        commands.append({"model": model, "method": method, "arm_k": arm_k, "case_count": len(case_ids), "argv": command})
    commands_path = output_dir / "generation_commands.json"
    commands_path.write_text(json.dumps(commands, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.execute:
        for item in commands:
            subprocess.run(item["argv"], cwd=ROOT, check=True)
        for row in plan_rows: row["execution_status"] = "executed"
        with plan_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(plan_rows[0])); writer.writeheader(); writer.writerows(plan_rows)

    summary = {
        "execute": bool(args.execute), "generate_only": bool(args.generate_only),
        "policy_sha256": policy["policy_sha256"], "policy_data_status": policy.get("data_status"),
        "routing_sha256": routing_hash, "temporal_summaries_sha256": temporal_hash,
        "routing_model_case_rows": len(routing), "routing_case_count": len({x["case_id"] for x in routing}),
        "routing_parent_count": len({x["parent_bug_id"] for x in routing}), "total_k": args.total_k,
        "route_counts": Counter(x["route"] for x in routing), "planned_arm_rows": len(plan_rows),
        "planned_candidate_count": sum(x["arm_k"] for x in plan_rows),
        "required_temporal_case_count": len(required_temporal), "temporal_contract_failures": 0,
        "command_group_count": len(commands), "budget_rule": "single arm gets total_k; both gets ceil(k/2) raw plus floor(k/2) temporal",
    }
    (output_dir / "dispatch_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__": main()
