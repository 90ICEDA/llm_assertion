#!/usr/bin/env python3
"""Reconstruct frozen disagreement-guided collisions and preserve all evidence.

This is an evidence inventory and conservative audit, not an automatic proof of
assertion quality. Run from any directory with Python 3.10+.
"""
import csv
import hashlib
import itertools
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v1"
OUT = ROOT / "deliverables/feedback_collision_reaudit_20261002"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path):
    return str(path.relative_to(ROOT)).replace("\\", "/")


def stable(*parts):
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    failures = []
    for parent_dir in sorted((BASE / "behavioral_probes_v3").iterdir()):
        if not parent_dir.is_dir():
            continue
        parent = parent_dir.name
        try:
            pr = read(parent_dir / "parent_result.json")
            ids = pr["policies"]["disagreement_guided"]
            chosen = {r["candidate_id"]: r for r in pr["candidate_sets"]
                      if r["probe_policy"] == "disagreement_guided"}
            ev = {}
            for slot in range(1, 9):
                cid = f"{parent}__v3_slot_{slot:02d}"
                ep = BASE / f"sequential_generation_v3_pilot30/{parent}/slot_{slot:02d}/attempt_01/evidence.json"
                ev[cid] = (read(ep), ep)
            roots = ("rtl_cases_real_scale210_independent_next", "rtl_cases_real_scale210_independent",
                     "rtl_cases_real_active", "rtl_cases_real_scale120", "rtl_cases_real_iverilog_ready", "rtl_cases_real")
            case = next((ROOT / name / parent for name in roots if (ROOT / name / parent).exists()), None)
            if case is None:
                failures.append({"parent": parent, "error": "case directory missing"})
                case = ROOT / roots[0] / parent
            context = {name: rel(case / name) if (case / name).exists() else None
                       for name in ("spec.md", "mutation.diff", "buggy.v", "correct.v", "golden.sva")}
            results = {}
            for cid in chosen:
                results[cid] = {}
                for pid in ids:
                    rp = parent_dir / "runs" / pid / cid / "result.json"
                    try:
                        d = read(rp)
                        results[cid][pid] = {
                            "fp": d["fp"], "tp": d["tp"],
                            "fixed_fail_hits": d["rtl"]["correct"]["fail_hits"],
                            "buggy_fail_hits": d["rtl"]["buggy"]["fail_hits"],
                            "fixed_antecedent_hits": d["rtl"]["correct"]["antecedent_hits"],
                            "buggy_antecedent_hits": d["rtl"]["buggy"]["antecedent_hits"],
                            "result_path": rel(rp),
                        }
                    except (OSError, KeyError, ValueError) as exc:
                        failures.append({"parent": parent, "candidate": cid, "probe": pid,
                                         "path": rel(rp), "error": str(exc)})
            for a, b in itertools.combinations(sorted(chosen), 2):
                ca, cb = chosen[a], chosen[b]
                if ca["fp_probe_ids"] != cb["fp_probe_ids"] or ca["tp_mutant_ids"] != cb["tp_mutant_ids"]:
                    continue
                ea, pa = ev[a]
                eb, pb = ev[b]
                diffs = []
                for pid in ids:
                    x, y = results[a].get(pid), results[b].get(pid)
                    if x and y and (x["fixed_fail_hits"], x["buggy_fail_hits"]) != (y["fixed_fail_hits"], y["buggy_fail_hits"]):
                        diffs.append({"probe_id": pid, "a_fixed": x["fixed_fail_hits"],
                                      "b_fixed": y["fixed_fail_hits"], "a_buggy": x["buggy_fail_hits"],
                                      "b_buggy": y["buggy_fail_hits"],
                                      "a_result": x["result_path"], "b_result": y["result_path"]})
                same_sva = ea.get("sva") == eb.get("sva")
                relation = "equivalent" if same_sva else "UNKNOWN"
                category = "both acceptable" if same_sva and ea.get("fixed_safe") and ea.get("target_detect") and ea.get("non_vacuous") else "unknown"
                confidence = "high" if same_sva else "low"
                note = "Identical SVA text; existing finite probes support the same verdict." if same_sva else "Distinct SVA semantics require obligation-based review; equal binary feedback and fail-hit counts do not establish equal quality."
                if parent == "case510_cc_spill_register_flush_push_priority" and {a[-2:], b[-2:]} == {"06", "07"}:
                    relation = "A_BETTER" if a.endswith("06") else "B_BETTER"
                    category = "quality difference"
                    confidence = "high"
                    note = "Existing held-flush replay shows slot 07 false-positive on fixed RTL and slot 06 passes; both detect buggy RTL. Slot 06 is PARTIAL against the full obligation."
                rows.append({
                    "pair_id": stable("disagreement_guided", parent, a, b),
                    "parent_id": parent, "candidate_A": a, "candidate_B": b,
                    "assertion_A": ea.get("sva"), "assertion_B": eb.get("sva"),
                    "semantic_difference": "identical SVA" if same_sva else f"A: {ea.get('ast')}; B: {eb.get('ast')}",
                    "feedback_signature": {"policy": "disagreement_guided", "fp_probe_ids": ca["fp_probe_ids"], "tp_mutant_ids": ca["tp_mutant_ids"]},
                    "quality_relation": relation, "category": category,
                    "count_difference": bool(diffs), "count_difference_probes": diffs,
                    "count_interpretation": "Fail-hit count is event frequency on a finite stimulus; no quality ordering follows without a fixed-RTL false positive or missed repair obligation." if diffs else "No fail-hit difference in selected probes.",
                    "evidence": {"candidate_A": rel(pa), "candidate_B": rel(pb),
                                 "case_context": context,
                                 "held_flush_replay": "deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/replay.md" if category == "quality difference" else None},
                    "reason": note, "confidence": confidence,
                })
        except (OSError, KeyError, ValueError) as exc:
            failures.append({"parent": parent, "error": str(exc)})
    (OUT / "pairs.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")
    (OUT / "failures.json").write_text(json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {"pairs": len(rows), "count_difference_pairs": sum(x["count_difference"] for x in rows),
               "quality_relations": dict(Counter(x["quality_relation"] for x in rows)),
               "categories": dict(Counter(x["category"] for x in rows)), "failures": len(failures)}
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
