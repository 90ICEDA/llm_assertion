from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

from run_multi_model_small_eval import MODEL_SPECS, MODEL_CALL_TELEMETRY, extract_sva_candidates, post_model_chat
from run_trace_abstraction_prototype import run_case_eval

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECT = ROOT / "outputs/019ed9f6-87cf-7830-adb8-595fe2ae140d/multi_model_eval_data"
DEFAULT_CASES = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUT = ROOT / "outputs/cross_model_qwen_two_stage_v1"


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def allowed_signals(case_dir: Path) -> list[str]:
    with (case_dir / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle))
    return [re.sub(r"\[.*$", "", x.strip()) for x in header if x.strip() != "time_ps"]


def qwen_spec() -> dict:
    return next(x for x in MODEL_SPECS if x["model_label"] == "Qwen")

IR_KEYS = {"trigger", "reset_condition", "polarity", "temporal_relation", "exact_delay", "duration", "consequent", "relevant_signals"}

def parse_ir(text: str) -> tuple[bool, bool, dict]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match: return False, False, {}
    try: value = json.loads(match.group(0))
    except Exception: return False, False, {}
    return isinstance(value, dict), isinstance(value, dict) and IR_KEYS.issubset(value), value if isinstance(value, dict) else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--direct-dir", default=str(DEFAULT_DIRECT)); ap.add_argument("--cases-root", default=str(DEFAULT_CASES)); ap.add_argument("--out-dir", default=str(DEFAULT_OUT)); ap.add_argument("--generate-only", action="store_true"); ap.add_argument("--candidates-per-cell", type=int, default=4)
    args = ap.parse_args(); direct, cases, out = Path(args.direct_dir).resolve(), Path(args.cases_root).resolve(), Path(args.out_dir).resolve(); out.mkdir(parents=True, exist_ok=True)
    log = pd.read_csv(direct / "multi_model_prompt_log.csv", encoding="utf-8-sig"); log = log[log.model_label == "Qwen"].sort_values(["case_id", "method"])
    cache_path = out / "two_stage_cache.json"; cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for i, row in enumerate(log.itertuples(), 1):
        key = f"{row.case_id}|{row.method}|k{args.candidates_per_cell}"
        if key in cache:
            print(f"[SKIP {i:02d}/{len(log):02d}] {key}", file=sys.stderr); continue
        original_prompt = Path(row.prompt_path).read_text(encoding="utf-8", errors="replace")
        ir_prompt = """Analyze the specification, RTL, and trace context below. Do not write SystemVerilog or SVA.
Return exactly one JSON object with these keys: trigger, reset_condition, polarity, temporal_relation,
exact_delay, duration, consequent, relevant_signals. Values must describe a general behavioral property,
not fixed trace cycles or trace-specific constants.\n\n""" + original_prompt
        t0 = len(MODEL_CALL_TELEMETRY); ir_response = post_model_chat(qwen_spec(), ir_prompt, temperature=0.2)
        ir_metric = dict(MODEL_CALL_TELEMETRY[-1]) if len(MODEL_CALL_TELEMETRY) > t0 else {}
        signals = allowed_signals(cases / row.case_id)
        sva_prompt = f"""Convert the structured property below into exactly {args.candidates_per_cell} distinct complete SystemVerilog
`assert property` statements. Return no explanation. Use only these signals: {', '.join(signals)}.
Use the stated reset convention. Do not strengthen or weaken the property and do not invent literals.

Structured property:
{ir_response}
"""
        candidates=[]; sva_responses=[]; sva_metrics=[]
        for attempt in range(3):
            attempt_prompt=sva_prompt
            if candidates: attempt_prompt += "\nDo not repeat these candidates:\n" + "\n".join(candidates)
            t1 = len(MODEL_CALL_TELEMETRY); sva_response = post_model_chat(qwen_spec(), attempt_prompt, temperature=0.0)
            sva_metrics.append(dict(MODEL_CALL_TELEMETRY[-1]) if len(MODEL_CALL_TELEMETRY) > t1 else {})
            sva_responses.append(sva_response)
            for candidate in extract_sva_candidates(sva_response):
                if candidate not in candidates: candidates.append(candidate)
                if len(candidates)>=args.candidates_per_cell: break
            if len(candidates)>=args.candidates_per_cell: break
        if len(candidates)<args.candidates_per_cell: raise RuntimeError(f"{key}: only {len(candidates)} distinct SVA candidates")
        ir_json_valid, ir_schema_complete, ir_value = parse_ir(ir_response)
        signal_set = set(signals); ir_signals = ir_value.get("relevant_signals", []) if isinstance(ir_value, dict) else []
        if not isinstance(ir_signals, list): ir_signals = []
        ir_signals_valid = bool(ir_signals) and set(map(str, ir_signals)).issubset(signal_set)
        cache[key] = {"case_id": row.case_id, "method": row.method, "ir_prompt": ir_prompt, "ir_response": ir_response, "ir_metric":ir_metric, "ir_json_valid":ir_json_valid,"ir_schema_complete":ir_schema_complete,"ir_signals_valid":ir_signals_valid,"sva_prompt": sva_prompt, "sva_responses": sva_responses, "sva_metrics":sva_metrics, "assertion_texts": candidates[:args.candidates_per_cell], "stage_call_count": 1+len(sva_metrics), "candidate_budget":args.candidates_per_cell}
        cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.generate_only: print(cache_path); return
    rows = []
    for key, item in sorted(cache.items()):
        metrics=[item.get("ir_metric",{}),*item.get("sva_metrics",[])]
        for candidate_index,assertion in enumerate(item["assertion_texts"],1):
            ev = run_case_eval(case_id=item["case_id"], assertion_text=assertion, signal_names=allowed_signals(cases/item["case_id"]), use_property=False, runtime_dir=out/"runtime"/item["case_id"]/item["method"]/f"cand_{candidate_index:02d}", cases_root=cases)
            rows.append({"model_label":"Qwen","baseline":"structured_property_to_sva","model_name":qwen_spec()["model_name"],"case_id":item["case_id"],"method":item["method"],"candidate_index":candidate_index,"assertion_text":assertion,"stage_call_count":item["stage_call_count"],"ir_json_valid":item.get("ir_json_valid",False),"ir_schema_complete":item.get("ir_schema_complete",False),"ir_signals_valid":item.get("ir_signals_valid",False),"generation_duration_sec":sum(float(x.get("duration_sec",0) or 0) for x in metrics) if candidate_index==1 else 0,"prompt_tokens":sum(int(x.get("prompt_tokens",0) or 0) for x in metrics) if candidate_index==1 else 0,"output_tokens":sum(int(x.get("output_tokens",0) or 0) for x in metrics) if candidate_index==1 else 0,"total_tokens":sum(int(x.get("total_tokens",0) or 0) for x in metrics) if candidate_index==1 else 0,**ev})
    result = pd.DataFrame(rows); result_path = out / "qwen_two_stage_results.csv"; result.to_csv(result_path,index=False,encoding="utf-8-sig")
    protocol = {"schema_version":2,"stage_1":"full context to structured property JSON; no SVA","stage_2":"structured property plus interface only to SVA; no trace","candidate_budget_per_cell":args.candidates_per_cell,"max_stage2_attempts":3,"cell_count":len(log),"direct_comparator":str((direct/'multi_model_results_raw.csv').resolve()),"sha256":{str(cache_path):sha(cache_path),str(result_path):sha(result_path),str((direct/'multi_model_results_raw.csv').resolve()):sha(direct/'multi_model_results_raw.csv')}}
    protocol_path=out/"two_stage_protocol.json";protocol_path.write_text(json.dumps(protocol,indent=2,ensure_ascii=False),encoding="utf-8");print(result_path)


if __name__ == "__main__": main()
