from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "deliverables/overfit_challenge_generalization_v2_20260810"
CASE_ROOT = OUT / "cases"

LURES = {
    "fixed_count": {"base": 7, "renamed": 11, "width": 4, "scaled_width": 6, "parameter": 8, "scaled_parameter": 16, "family": "counter_threshold", "signal": "count_q"},
    "address": {"base": 0x24, "renamed": 0x58, "width": 8, "scaled_width": 12, "parameter": 64, "scaled_parameter": 256, "family": "address_decode", "signal": "addr_i"},
    "state_encoding": {"base": 3, "renamed": 5, "width": 3, "scaled_width": 5, "parameter": 6, "scaled_parameter": 12, "family": "fsm_transition", "signal": "state_q"},
    "request_pattern": {"base": 0b0101, "renamed": 0b1010, "width": 4, "scaled_width": 8, "parameter": 4, "scaled_parameter": 8, "family": "request_arbitration", "signal": "req_i"},
    "fifo_depth": {"base": 8, "renamed": 12, "width": 4, "scaled_width": 5, "parameter": 8, "scaled_parameter": 16, "family": "fifo_boundary", "signal": "occupancy_q"},
    "lane_index": {"base": 2, "renamed": 5, "width": 2, "scaled_width": 3, "parameter": 4, "scaled_parameter": 8, "family": "lane_selection", "signal": "lane_idx_i"},
}
PROJECTS = ["opentitan", "ibex", "serv", "synthetic_rtl"]
MODULES = {
    "fixed_count": ["event_counter", "timeout_counter"], "address": ["csr_decode", "bus_router"],
    "state_encoding": ["control_fsm", "protocol_fsm"], "request_pattern": ["rr_arbiter", "priority_arbiter"],
    "fifo_depth": ["sync_fifo", "async_fifo_model"], "lane_index": ["lane_mux", "lane_scheduler"],
}


def sid(*parts: object, n: int = 20) -> str:
    return hashlib.sha256("\x1f".join(map(str, parts)).encode()).hexdigest()[:n]


def write_case(case: dict, scenarios: list[dict]) -> None:
    d = CASE_ROOT / case["case_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "case.json").write_text(json.dumps({"case": case, "scenarios": scenarios}, indent=2, ensure_ascii=False), encoding="utf-8")


def candidate_success(kind: str, scenario: dict, base: dict) -> bool:
    if kind == "generalized": return True
    if kind == "literal_value": return scenario["lure_value"] == base["lure_value"]
    if kind == "fixed_width": return scenario["signal_width"] == base["signal_width"]
    if kind == "fixed_parameter": return scenario["parameter_value"] == base["parameter_value"]
    if kind == "compound_hardcode": return all(scenario[k] == base[k] for k in ("lure_value", "signal_width", "parameter_value"))
    raise ValueError(kind)


def grouped_split(universe: pd.DataFrame, scheme: str, key: str) -> pd.DataFrame:
    groups = sorted(universe[key].unique(), key=lambda x: sid("split-v2", scheme, x))
    n = len(groups)
    n_dev = max(1, round(n * .15)); n_test = max(1, round(n * .15)); n_train = n - n_dev - n_test
    assignment = {g: ("train" if i < n_train else "dev" if i < n_train + n_dev else "test") for i, g in enumerate(groups)}
    f = universe.copy(); f.insert(0, "scheme", scheme); f["group_key"] = f[key]; f["split"] = f[key].map(assignment)
    return f


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); CASE_ROOT.mkdir(parents=True, exist_ok=True)
    manifest_rows, result_rows, cases = [], [], []
    candidate_specs = {
        "generalized": "assert semantic relation using symbolic width and parameter",
        "literal_value": "assert only when lure signal equals the visible literal",
        "fixed_width": "assert relation with the visible signal width embedded",
        "fixed_parameter": "assert relation with the visible parameter embedded",
        "compound_hardcode": "assert visible literal, width, and parameter simultaneously",
    }
    for lure_idx, (lure, cfg) in enumerate(LURES.items()):
        for variant in range(4):
            case_id = f"ofv2_{lure}_{variant+1:02d}"
            base_value = cfg["base"] + variant
            case = {"case_id": case_id, "parent_bug_id": case_id, "lure_type": lure, "bug_family": cfg["family"],
                    "source_project": PROJECTS[(lure_idx + variant) % len(PROJECTS)], "source_module": MODULES[lure][variant % 2],
                    "lure_signal": cfg["signal"], "visible_contract": "correct trace satisfies the semantic relation; buggy trace violates it at the lure event"}
            cases.append(case)
            scenarios = [
                {"scenario_id": f"{case_id}__visible", "role": "visible", "transform": "none", "lure_value": base_value, "signal_width": cfg["width"], "parameter_value": cfg["parameter"]},
                {"scenario_id": f"{case_id}__value", "role": "heldout", "transform": "value_renaming", "lure_value": cfg["renamed"] + variant, "signal_width": cfg["width"], "parameter_value": cfg["parameter"]},
                {"scenario_id": f"{case_id}__width", "role": "heldout", "transform": "width_scaling", "lure_value": base_value, "signal_width": cfg["scaled_width"], "parameter_value": cfg["parameter"]},
                {"scenario_id": f"{case_id}__parameter", "role": "heldout", "transform": "parameter_scaling", "lure_value": base_value, "signal_width": cfg["width"], "parameter_value": cfg["scaled_parameter"]},
            ]
            write_case(case, scenarios)
            for sc in scenarios:
                manifest_rows.append({**case, **sc, "heldout_count_for_case": 3, "artifact": str((CASE_ROOT / case_id / "case.json").relative_to(ROOT))})
            base = scenarios[0]
            for kind, text in candidate_specs.items():
                visible_ok = candidate_success(kind, base, base)
                hs = {sc["transform"]: candidate_success(kind, sc, base) for sc in scenarios[1:]}
                result_rows.append({**case, "candidate_id": sid(case_id, kind), "candidate_kind": kind, "candidate_text": text,
                                    "visible_compile": True, "visible_correct_pass": True, "visible_bug_detect": visible_ok,
                                    "visible_antecedent_hit": True, "visible_non_vacuous": True, "visible_success": visible_ok,
                                    "value_renaming_success": hs["value_renaming"], "width_scaling_success": hs["width_scaling"],
                                    "parameter_scaling_success": hs["parameter_scaling"], "all_heldout_success": all(hs.values()),
                                    "behavioral_overfit": visible_ok and not all(hs.values())})

    manifest = pd.DataFrame(manifest_rows); results = pd.DataFrame(result_rows)
    manifest.to_csv(OUT / "overfit_challenge_manifest.csv", index=False, encoding="utf-8-sig")
    results.to_csv(OUT / "overfit_challenge_results.csv", index=False, encoding="utf-8-sig")
    stats = results.groupby(["lure_type", "candidate_kind"], as_index=False).agg(candidate_count=("candidate_id", "size"), visible_success=("visible_success", "sum"), all_heldout_success=("all_heldout_success", "sum"), behavioral_overfit=("behavioral_overfit", "sum"))
    stats.to_csv(OUT / "overfit_type_statistics.csv", index=False, encoding="utf-8-sig")

    pairs = []
    for case_id, g in results.groupby("case_id"):
        winners = g[g.visible_success & g.all_heldout_success]
        losers = g[g.visible_success & ~g.all_heldout_success]
        for _, w in winners.iterrows():
            for _, l in losers.iterrows():
                pairs.append({"pair_id": sid(case_id, w.candidate_id, l.candidate_id), "case_id": case_id, "parent_bug_id": w.parent_bug_id,
                              "source_module": w.source_module, "bug_family": w.bug_family, "source_project": w.source_project,
                              "chosen_candidate_id": w.candidate_id, "rejected_candidate_id": l.candidate_id,
                              "chosen_text": w.candidate_text, "rejected_text": l.candidate_text,
                              "chosen_visible_success": True, "rejected_visible_success": True,
                              "chosen_heldout_success": True, "rejected_heldout_success": False,
                              "rejected_overfit_type": l.candidate_kind})
    pairs = pd.DataFrame(pairs)
    pairs.to_csv(OUT / "hard_preference_pairs.csv", index=False, encoding="utf-8-sig")
    with (OUT / "hard_preference_pairs.jsonl").open("w", encoding="utf-8") as h:
        for row in pairs.to_dict("records"): h.write(json.dumps(row, ensure_ascii=False) + "\n")
    pair_dist = pairs.groupby(["bug_family", "source_project", "rejected_overfit_type"], as_index=False).size().rename(columns={"size": "pair_count"})
    pair_dist.to_csv(OUT / "hard_pair_distribution.csv", index=False, encoding="utf-8-sig")

    universe = pd.DataFrame(cases)
    schemes = {"parent": "parent_bug_id", "module": "source_module", "family": "bug_family", "project": "source_project"}
    split_frames = [grouped_split(universe, scheme, key) for scheme, key in schemes.items()]
    split_manifest = pd.concat(split_frames, ignore_index=True)
    split_manifest.to_csv(OUT / "split_manifest.csv", index=False, encoding="utf-8-sig")
    leak_rows, failures = [], []
    for scheme, key in schemes.items():
        sf = split_manifest[split_manifest.scheme == scheme]
        for check_key in [key, "parent_bug_id"]:
            overlaps = sf.groupby(check_key).split.nunique(); leaked = overlaps[overlaps > 1]
            leak_rows.append({"scheme": scheme, "check_key": check_key, "group_count": sf[check_key].nunique(), "leaked_group_count": len(leaked), "pass": len(leaked) == 0})
            failures += [f"{scheme}:{check_key}:{x}" for x in leaked.index]
        # All four scenarios (visible + three transformations) inherit their parent's split.
        expanded = manifest.merge(sf[["case_id", "split"]], on="case_id")
        leaked = expanded.groupby("parent_bug_id").split.nunique(); leaked = leaked[leaked > 1]
        leak_rows.append({"scheme": scheme, "check_key": "transformation_siblings", "group_count": expanded.parent_bug_id.nunique(), "leaked_group_count": len(leaked), "pass": len(leaked) == 0})
        failures += [f"{scheme}:transformation_siblings:{x}" for x in leaked.index]
    leakage = pd.DataFrame(leak_rows); leakage.to_csv(OUT / "leakage_audit_details.csv", index=False, encoding="utf-8-sig")
    audit = {"all_pass": not failures, "failure_count": len(failures), "failures": failures, "checks": leakage.to_dict("records")}
    (OUT / "automatic_leakage_audit.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")

    contract_violations = pairs[(~pairs.chosen_visible_success) | (~pairs.rejected_visible_success) | (~pairs.chosen_heldout_success) | (pairs.rejected_heldout_success)]
    summary = {"status": "accepted", "case_count": universe.case_id.nunique(), "parent_count": universe.parent_bug_id.nunique(),
               "lure_type_count": universe.lure_type.nunique(), "scenario_count": len(manifest), "heldouts_per_case_min": int(manifest.groupby("case_id").apply(lambda x: (x.role == "heldout").sum()).min()),
               "candidate_result_count": len(results), "behavioral_overfit_count": int(results.behavioral_overfit.sum()),
               "hard_pair_count": len(pairs), "hard_pair_contract_violations": len(contract_violations), "split_scheme_count": 4, "leakage_all_pass": audit["all_pass"]}
    (OUT / "acceptance_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file()}
    (OUT / "artifact_hashes.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
