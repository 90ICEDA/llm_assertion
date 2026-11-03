from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from trace_representation_contract import validate_temporal_relation_abstraction

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "rtl_cases_real_scale210_independent"
SEAL = ROOT / "outputs/pristine_trace_router_v1/sealed_test_manifest.json"
OUT = ROOT / "outputs/pristine_trace_router_v1/trace_representations.json"
VARIANTS = {"primary": "", "heldout": "_holdout", "decoy": "_decoy"}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def short(name: str) -> str:
    return name.split(".")[-1]


def aligned(good: list[dict[str, str]], bad: list[dict[str, str]]) -> list[tuple[dict[str, str], dict[str, str]]]:
    bmap = {r["time_ps"]: r for r in bad}
    return [(g, bmap[g["time_ps"]]) for g in good if g["time_ps"] in bmap]


def difference(g: dict[str, str], b: dict[str, str]) -> list[str]:
    return sorted(k for k in set(g) & set(b) if k != "time_ps" and g[k] != b[k])


def match_columns(columns: list[str], signals: list[str]) -> list[str]:
    found = []
    for col in columns:
        leaf = short(col).split("[")[0]
        if any(leaf == s.split("[")[0] or leaf.endswith(s.split("[")[0]) for s in signals): found.append(col)
    return found


def input_like(column: str) -> bool:
    leaf = short(column).split("[")[0].lower()
    if leaf.endswith("_i") or leaf in {"clk", "rst", "rst_n", "enable", "drop", "select", "pause_req"}: return True
    if leaf.startswith("s_axis_") and not leaf.endswith("ready"): return True
    if leaf in {"m_axis_tready", "ready_i", "async_rstn_i", "async_sel_i", "test_en_i", "test_clk_i"}: return True
    return False


def build_variant(case_id: str, meta: dict[str, Any], variant: str, suffix: str) -> dict[str, Any]:
    directory = DATA / case_id
    gp, bp = directory / f"waveform_good{suffix}.csv", directory / f"waveform_bad{suffix}.csv"
    good, bad = rows(gp), rows(bp); pairs = aligned(good, bad)
    if not pairs: raise RuntimeError(f"no aligned samples: {case_id}/{variant}")
    div_index = next((i for i, (g, b) in enumerate(pairs) if difference(g, b)), None)
    if div_index is None: raise RuntimeError(f"no divergence: {case_id}/{variant}")
    dg, db = pairs[div_index]; diffs = difference(dg, db)
    relevant = list(meta.get("relevant_signals") or [])
    rel_cols = match_columns(list(dg), relevant)
    reset_cols = [c for c in dg if any(t in short(c).lower() for t in ("rst", "reset"))]
    trigger_candidates = [c for c in rel_cols if input_like(c) and c not in diffs]
    trigger_index = div_index
    trigger_cols: list[str] = []
    for i in range(div_index, 0, -1):
        changed = [c for c in trigger_candidates if pairs[i][0].get(c) != pairs[i-1][0].get(c)]
        if changed: trigger_index, trigger_cols = i, changed; break
    if not trigger_cols:
        trigger_cols = trigger_candidates[:3]
    if not trigger_cols:
        raise RuntimeError(f"no observable input/control trigger: {case_id}/{variant}")
    tg = pairs[trigger_index][0]
    delay_samples = div_index - trigger_index
    duration = 1
    for i in range(trigger_index + 1, len(pairs)):
        if any(pairs[i][0].get(c) != tg.get(c) for c in trigger_cols): break
        duration += 1
    polarity = "; ".join(f"{short(c)}={tg.get(c)}" for c in trigger_cols)
    divergence = "; ".join(f"{short(c)}: good={dg[c]}, bad={db[c]}" for c in diffs)
    reset = "; ".join(f"{short(c)}={tg.get(c)}" for c in reset_cols) or "no reset signal is visible in this trace"
    temporal = "\n".join([
        "Temporal-relation abstraction:",
        f"- Trigger: in the observed {variant} trace, {polarity} is the nearest relevant-signal event before divergence.",
        f"- Polarity: the observed trigger context is {polarity}; at divergence {divergence}.",
        f"- Ordering: the relevant trigger event precedes or coincides with the first good/bad divergence.",
        f"- Observed delay: the {variant} trace has an observed delay of exactly {delay_samples} sampled cycles from trigger to first divergence.",
        f"- Duration: the observed post-trigger values persist for {duration} sampled cycles in this trace.",
        f"- Reset: at the trigger, {reset}.",
        f"- Good/bad divergence: at observed time {dg['time_ps']} ps, {divergence}.",
        "- Generalization boundary: do not infer a universal property from absolute cycle indices or one-off literal constants; preserve only the observed polarity, ordering, delay, duration, reset context, and good/bad relation.",
    ])
    golden = meta.get("golden_sva") or ""
    golden_text = golden if isinstance(golden, str) else golden.get("sva") or golden.get("assertion") or ""
    expected = "" if isinstance(golden, str) else golden.get("expected_behavior", "")
    errors = validate_temporal_relation_abstraction(
        temporal, golden_sva=str(golden_text), expected_behavior=str(expected),
        correct_rtl=(directory/"correct.v").read_text(encoding="utf-8"), buggy_rtl=(directory/"buggy.v").read_text(encoding="utf-8"))
    events = []
    for i in range(1, len(good)):
        changed = [c for c in rel_cols if good[i].get(c) != good[i-1].get(c)]
        if changed: events.append({"time_ps": good[i]["time_ps"], "changes": {short(c): good[i][c] for c in changed}})
    naive = f"The paired {variant} traces contain {len(pairs)} aligned samples. Their first difference is at {dg['time_ps']} ps on {', '.join(short(c) for c in diffs)}; good/bad values are {divergence}."
    event = "Event abstraction:\n" + "\n".join(f"- observed time {e['time_ps']} ps: " + ", ".join(f"{k}->{v}" for k,v in e["changes"].items()) for e in events) + f"\n- first divergence: observed time {dg['time_ps']} ps; {divergence}."
    return {
        "variant": variant,
        "raw_trace": {"good_csv": gp.read_text(encoding="utf-8-sig"), "bad_csv": bp.read_text(encoding="utf-8-sig")},
        "naive_summary": naive, "event_abstraction": event, "temporal_relation_abstraction": temporal,
        "provenance": {"good_file": str(gp.relative_to(ROOT)), "bad_file": str(bp.relative_to(ROOT)), "sample_count": len(pairs), "trigger_time_ps": tg["time_ps"], "first_divergence_time_ps": dg["time_ps"], "observed_delay_samples": delay_samples, "differing_signals": [short(c) for c in diffs], "contract_errors": errors},
    }


def main() -> None:
    seal = json.loads(SEAL.read_text(encoding="utf-8")); output=[]
    for item in seal["cases"]:
        case_id=item["case_id"]; d=DATA/case_id
        meta=json.loads((d/"case_metadata.json").read_text(encoding="utf-8"))
        output.append({"case_id":case_id,"parent_bug_id":item["parent_bug_id"],"representations":[build_variant(case_id,meta,v,s) for v,s in VARIANTS.items()]})
    OUT.write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
    errors=[(c["case_id"],v["variant"],v["provenance"]["contract_errors"]) for c in output for v in c["representations"] if v["provenance"]["contract_errors"]]
    print(json.dumps({"cases":len(output),"variants":sum(len(c["representations"]) for c in output),"representations":sum(len(c["representations"])*4 for c in output),"temporal_contract_failures":len(errors)},indent=2))
    if errors:
        for x in errors: print(x)
        raise SystemExit(1)


if __name__ == "__main__": main()
