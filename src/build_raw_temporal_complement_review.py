from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW = "spec_rtl_raw_trace"
TEMPORAL = "spec_rtl_temporal_relation_abstraction"
ATTRIBUTIONS = (
    "concrete_value_important", "exact_cycle_important", "cross_cycle_relation_important",
    "trigger_lost", "polarity_lost", "duration_lost", "raw_noise", "hardcoding",
    "vacuity", "too_strong",
)


def truth(value: str) -> bool:
    return str(value).strip().lower() == "true"


def success(row: dict[str, str]) -> bool:
    return all(truth(row[key]) for key in (
        "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous"
    ))


def parent_id(case_id: str) -> str:
    match = re.search(r"_from_(case\d+_.+)$", case_id)
    return match.group(1) if match else case_id


def quadrant(raw_ok: bool, temporal_ok: bool) -> str:
    if raw_ok and not temporal_ok:
        return "raw_success_temporal_fail"
    if temporal_ok and not raw_ok:
        return "temporal_success_raw_fail"
    return "both_success" if raw_ok else "both_fail"


def choose_sample(items: list[dict], count: int, rng: random.Random) -> list[dict]:
    shuffled = list(items)
    rng.shuffle(shuffled)
    chosen, used_parents = [], set()
    for item in shuffled:
        if item["parent_bug_id"] not in used_parents:
            chosen.append(item)
            used_parents.add(item["parent_bug_id"])
            if len(chosen) == count:
                return chosen
    for item in shuffled:
        if item not in chosen:
            item["parent_overlap_in_review"] = True
            chosen.append(item)
            if len(chosen) == count:
                break
    return chosen


def candidate_summary(rows: list[dict[str, str]]) -> str:
    parts = []
    for row in sorted(rows, key=lambda x: int(x["candidate_index"])):
        flags = []
        if not truth(row["heldout_antecedent_hit"]): flags.append("no-heldout-trigger")
        if not truth(row["heldout_non_vacuous"]): flags.append("vacuous")
        if not truth(row["heldout_correct_pass"]): flags.append("too-strong-on-good")
        if truth(row["literal_hardcoding"]): flags.append("literal-hardcoding")
        parts.append(f"c{row['candidate_index']} [{'|'.join(flags) or 'clean'}] {row['assertion_text']}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=str(ROOT / "outputs/scale120_trace_representation_ablation_data/multi_model_results_raw.csv"))
    parser.add_argument("--additional-results", action="append", default=[])
    parser.add_argument("--root", default=str(ROOT / "rtl_cases_real_scale120"))
    parser.add_argument("--additional-root", action="append", default=[])
    parser.add_argument("--summaries", default=str(ROOT / "outputs/scale120_abstracted_summary_inputs/scale120_abstracted_summaries_combined.json"))
    parser.add_argument("--additional-summaries", action="append", default=[])
    parser.add_argument("--output-dir", default=str(ROOT / "outputs/raw_temporal_complement_review"))
    parser.add_argument("--per-quadrant", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260719)
    args = parser.parse_args()

    all_rows = []
    for results_path in [args.results, *args.additional_results]:
        with Path(results_path).open(encoding="utf-8-sig", newline="") as handle:
            all_rows.extend(row for row in csv.DictReader(handle) if row["method"] in {RAW, TEMPORAL})
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in all_rows:
        grouped[(row["model_label"], row["case_id"], row["method"])].append(row)
    keys = sorted({(model, case) for model, case, _ in grouped})
    cells = []
    for model, case_id in keys:
        raw_rows, temporal_rows = grouped[(model, case_id, RAW)], grouped[(model, case_id, TEMPORAL)]
        raw_ok, temporal_ok = any(map(success, raw_rows)), any(map(success, temporal_rows))
        cells.append({
            "model": model, "case_id": case_id, "parent_bug_id": parent_id(case_id),
            "quadrant": quadrant(raw_ok, temporal_ok), "raw_success": raw_ok,
            "temporal_success": temporal_ok, "raw_rows": raw_rows, "temporal_rows": temporal_rows,
            "parent_overlap_in_review": False,
        })

    by_quadrant: dict[str, list[dict]] = defaultdict(list)
    for cell in cells: by_quadrant[cell["quadrant"]].append(cell)
    rng = random.Random(args.seed)
    selected = []
    for name in ("raw_success_temporal_fail", "temporal_success_raw_fail", "both_success", "both_fail"):
        if len(by_quadrant[name]) < args.per_quadrant:
            raise RuntimeError(f"{name} has only {len(by_quadrant[name])} model-case cells")
        selected.extend(choose_sample(by_quadrant[name], args.per_quadrant, rng))

    meta = {}
    for root_path in [args.root, *args.additional_root]:
        manifest = json.loads((Path(root_path) / "case_manifest.json").read_text(encoding="utf-8"))
        meta.update({item["name"]: item for item in manifest.get("cases", [])})
    summaries = {}
    for summaries_path in [args.summaries, *args.additional_summaries]:
        payload = json.loads(Path(summaries_path).read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else payload.get("cases", payload.get("items", []))
        for item in items:
            case_id = item.get("case_id") or item.get("name")
            summary_text = item.get("abstracted_summary") or item.get("temporal_relation_abstraction") or item.get("summary")
            if case_id and summary_text:
                summaries[case_id] = summary_text
    decisions_path = Path(args.output_dir) / "manual_decisions.json"
    decisions = {}
    if decisions_path.exists():
        decisions = {(x[0], x[1]): x[2:] for x in json.loads(decisions_path.read_text(encoding="utf-8"))}
    output_dir = Path(args.output_dir); output_dir.mkdir(parents=True, exist_ok=True)
    review_rows, markdown = [], [
        "# Raw vs formal-compliant temporal abstraction: manual review packet", "",
        f"Seed: `{args.seed}`; unit: model x case; k: 2; success: case-level any-of-k on held-out; temporal contract: formal_compliant.", "",
        f"Allowed attributions: {', '.join(ATTRIBUTIONS)}", "",
    ]
    for index, cell in enumerate(selected, 1):
        case_id = cell["case_id"]; case_meta = meta.get(case_id, {})
        row = {key: cell[key] for key in ("model", "case_id", "parent_bug_id", "quadrant", "raw_success", "temporal_success", "parent_overlap_in_review")}
        decision = decisions.get((cell["model"], case_id))
        if decision:
            primary, secondary, evidence = decision
            if primary not in ATTRIBUTIONS or secondary not in ATTRIBUTIONS:
                raise RuntimeError(f"Invalid manual attribution for {(cell['model'], case_id)}")
            row.update({"primary_attribution": primary, "secondary_attribution": secondary, "manual_evidence": evidence, "reviewer": "Codex", "review_status": "reviewed"})
        else:
            row.update({"primary_attribution": "", "secondary_attribution": "", "manual_evidence": "", "reviewer": "", "review_status": "pending"})
        review_rows.append(row)
        markdown.extend([
            f"## {index}. {cell['quadrant']} | {cell['model']} | {case_id}", "",
            f"Parent: `{cell['parent_bug_id']}`; overlap: `{cell['parent_overlap_in_review']}`; bug class: `{case_meta.get('bug_class','')}`; family: `{case_meta.get('bug_family','')}`", "",
            f"Spec: {case_meta.get('spec','')}", "", "Formal-compliant temporal input:", "", summaries.get(case_id, "(missing)"), "",
            "Raw candidates:", "", "```text", candidate_summary(cell["raw_rows"]), "```", "",
            "Temporal candidates:", "", "```text", candidate_summary(cell["temporal_rows"]), "```", "",
            f"Manual verdict: {row['review_status'].upper()} | primary={row['primary_attribution']} | secondary={row['secondary_attribution']}", "",
            f"Evidence: {row['manual_evidence']}", "",
        ])
    with (output_dir / "manual_review_sample.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(review_rows[0])); writer.writeheader(); writer.writerows(review_rows)
    (output_dir / "manual_review_packet.md").write_text("\n".join(markdown), encoding="utf-8")
    quadrant_rows = []
    for name in ("raw_success_temporal_fail", "temporal_success_raw_fail", "both_success", "both_fail"):
        population = [x for x in cells if x["quadrant"] == name]
        reviewed = [x for x in review_rows if x["quadrant"] == name]
        quadrant_rows.append({
            "quadrant": name,
            "model": "GPT+Claude model-case cells",
            "k": 2,
            "population_model_case_cells": len(population),
            "population_cases": len({x["case_id"] for x in population}),
            "population_parents": len({x["parent_bug_id"] for x in population}),
            "manual_review_rows": len(reviewed),
            "manual_review_parents": len({x["parent_bug_id"] for x in reviewed}),
            "parent_overlap_rows": sum(str(x["parent_overlap_in_review"]).lower() == "true" for x in reviewed),
            "deduplicated": "parent-preferred",
            "overlap": "explicit per row",
            "success_metric": "case-level any-of-k held-out",
            "temporal_contract": "formal_compliant",
            "primary_attributions": ";".join(f"{key}={value}" for key, value in sorted(Counter(x["primary_attribution"] for x in reviewed).items())),
        })
    with (output_dir / "quadrant_summary.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(quadrant_rows[0])); writer.writeheader(); writer.writerows(quadrant_rows)
    summary = {
        "model": "GPT and Claude, reported separately in rows", "k": 2,
        "sample_unit": "model_case", "success_unit": "case_level_any_of_k_heldout",
        "candidate_rows": len(all_rows), "case_model_cells": len(cells),
        "unique_cases": len({x['case_id'] for x in cells}), "unique_parents": len({x['parent_bug_id'] for x in cells}),
        "deduplicated": "selection prefers unique parent within quadrant", "overlap": "recorded per row",
        "temporal_contract": "formal_compliant", "quadrant_population": Counter(x["quadrant"] for x in cells),
        "manual_sample_per_quadrant": args.per_quadrant,
        "reviewed_rows": sum(x["review_status"] == "reviewed" for x in review_rows),
        "primary_attribution_counts": Counter(x["primary_attribution"] for x in review_rows if x["primary_attribution"]),
        "secondary_attribution_counts": Counter(x["secondary_attribution"] for x in review_rows if x["secondary_attribution"]),
    }
    (output_dir / "review_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__": main()
