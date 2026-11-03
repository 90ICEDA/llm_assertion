#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from build_seen_only_candidate_reranker import parser_support, referenced_signals, signal_inventory
from run_multi_model_small_eval import MODEL_SPECS, extract_sva_candidates, literal_hardcoding_flag, post_model_chat
from run_trace_abstraction_prototype import run_case_eval

CASES = ROOT / "rtl_cases_real_scale120"
FEATURES = ROOT / "deliverables/equal_budget_visible_selection_20260809/visible_only_candidate_features.csv"
SELECTED = ROOT / "deliverables/equal_budget_visible_selection_20260809/selected_candidate_details.csv"
TEMPORAL = ROOT / "outputs/formal_temporal_abstractions/temporal_abstractions.json"
OUT = ROOT / "deliverables/one_step_failure_guided_repair_20260810"
CATEGORIES = ["compile_fail", "unsupported", "vacuity", "antecedent_not_triggered", "too_strong", "too_weak", "signal_missing", "reset_misuse", "hardcoding"]
ARMS = ["unified", "failure_specific", "wrong_diagnosis"]
FEEDBACK = {
    "compile_fail": "The assertion does not compile; return one syntactically complete concurrent assert property statement.",
    "unsupported": "The assertion uses a construct unsupported by the evaluation grammar; use a simple supported concurrent property.",
    "vacuity": "The assertion is vacuous on the seen executions; use an antecedent that occurs and still expresses the intended relation.",
    "antecedent_not_triggered": "The antecedent never triggers on the seen bad execution; revise the trigger using only observed legal signals.",
    "too_strong": "The assertion rejects the seen good execution; relax only the over-constrained condition or timing.",
    "too_weak": "The assertion does not reject the seen bad execution; strengthen the observable consequence without trace-specific constants.",
    "signal_missing": "The assertion references a signal outside the allowed interface; replace it with legal signals only.",
    "reset_misuse": "Reset handling does not follow the case reset convention; repair the clock/reset guard.",
    "hardcoding": "The assertion copies trace-specific literal values or cycles; generalize the relation without those literals.",
}
WRONG = dict(zip(CATEGORIES, CATEGORIES[1:] + CATEGORIES[:1]))


def truth(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "yes"])


def allowed_signals(case_dir: Path) -> list[str]:
    with (case_dir / "waveform_good.csv").open(encoding="utf-8-sig", newline="") as f:
        return [re.sub(r"\[.*$", "", x.strip()) for x in next(csv.reader(f)) if x.strip() != "time_ps"]


def waveform(path: Path, max_rows: int = 80) -> str:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return "\n".join(",".join(r) for r in list(csv.reader(f))[: max_rows + 1])


def static_checks(assertion: str, case_dir: Path) -> dict[str, bool]:
    inventory, resets = signal_inventory(case_dir)
    refs = referenced_signals(assertion)
    lower = assertion.lower()
    combinational = "@(*)" in lower or "@*" in lower
    return {
        "parser_support": bool(parser_support(assertion)),
        "signal_legal": bool(refs) and refs.issubset(inventory),
        "reset_valid": combinational if not resets else ("disable iff" in lower and any(re.search(rf"\b{re.escape(x.lower())}\b", lower) for x in resets)),
        "no_hardcoding": not bool(literal_hardcoding_flag(assertion)),
    }


def mutate(assertion: str, category: str, case_dir: Path) -> str:
    clk = "clk" if "clk" in allowed_signals(case_dir) else next((x for x in allowed_signals(case_dir) if "clk" in x.lower()), allowed_signals(case_dir)[0])
    reset = next((x for x in allowed_signals(case_dir) if "rst" in x.lower() or "reset" in x.lower()), "")
    guard = f" disable iff (!{reset})" if reset else ""
    if category == "compile_fail": return f"assert property (@(posedge {clk}){guard} (1'b1) |-> );"
    if category == "unsupported": return "assert final (1'b1);"
    if category == "signal_missing": return f"assert property (@(posedge {clk}){guard} ghost_signal |-> 1'b1);"
    if category == "reset_misuse": return re.sub(r"\s*disable\s+iff\s*\([^)]*\)", "", assertion, count=1, flags=re.I)
    return assertion


def model_spec(label: str) -> dict:
    return next(x for x in MODEL_SPECS if x["model_label"] == label)


def materialize_targets() -> pd.DataFrame:
    features = pd.read_csv(FEATURES, encoding="utf-8-sig")
    selected = pd.read_csv(SELECTED, encoding="utf-8-sig").drop_duplicates(["pool", "model_label", "case_id", "candidate_uid"])
    eval_cols = ["pool", "model_label", "case_id", "candidate_uid", "heldout_correct_pass", "heldout_buggy_fail", "heldout_antecedent_hit", "heldout_non_vacuous", "trace_overfit"]
    data = features.merge(selected[eval_cols], on=["pool", "model_label", "case_id", "candidate_uid"], how="inner", validate="one_to_one")
    data = data.sort_values(["model_label", "case_id", "pool", "candidate_uid"]).reset_index(drop=True)
    masks = {
        "compile_fail": ~truth(data.compile_ok),
        "vacuity": truth(data.compile_ok) & ~truth(data.non_vacuous),
        "antecedent_not_triggered": truth(data.compile_ok) & ~truth(data.seen_antecedent_hit),
        "too_strong": truth(data.compile_ok) & ~truth(data.seen_good_pass),
        "too_weak": truth(data.compile_ok) & truth(data.seen_good_pass) & ~truth(data.seen_bad_fail),
        "hardcoding": truth(data.compile_ok) & ~truth(data.no_hardcoding),
    }
    used: set[tuple[str, str, str]] = set(); rows = []
    assignments = [(arm, model) for arm in ARMS for model in ["GPT", "Claude"]]
    for category in CATEGORIES:
        for arm, model in assignments:
            synthetic = category in {"unsupported", "signal_missing", "reset_misuse"}
            eligible = data[(data.model_label == model)].copy()
            if category in masks and not synthetic: eligible = eligible[masks[category][eligible.index]]
            eligible = eligible[~eligible.apply(lambda r: (r.model_label, r.case_id, r.candidate_uid) in used, axis=1)]
            if eligible.empty:
                eligible = data[(data.model_label == model) & ~data.apply(lambda r: (r.model_label, r.case_id, r.candidate_uid) in used, axis=1)]
                synthetic = True
            row = eligible.iloc[0].copy(); used.add((row.model_label, row.case_id, row.candidate_uid))
            original = mutate(str(row.assertion_text), category, CASES / str(row.case_id)) if synthetic else str(row.assertion_text)
            rows.append({**row.to_dict(), "primary_failure": category, "prompt_arm": arm, "diagnosis_supplied": category if arm != "wrong_diagnosis" else WRONG[category], "original_assertion": original, "synthetic_static_case": synthetic})
    target = pd.DataFrame(rows)
    target["repair_id"] = [f"r{i:03d}" for i in range(1, len(target)+1)]
    if len(target) != 54 or target[["model_label", "case_id", "candidate_uid"]].drop_duplicates().shape[0] != 54:
        raise RuntimeError("target materialization failed")
    target.to_csv(OUT / "repair_targets.csv", index=False, encoding="utf-8-sig")
    return target


def build_prompt(row: pd.Series, temporal_lookup: dict[str, str]) -> str:
    case_dir = CASES / str(row.case_id)
    context = ("Seen good trace:\n" + waveform(case_dir / "waveform_good.csv") + "\n\nSeen bad trace:\n" + waveform(case_dir / "waveform_bad.csv")) if row.representation == "raw" else "Seen temporal abstraction:\n" + temporal_lookup[str(row.case_id)]
    if row.prompt_arm == "unified":
        diagnosis = "Run the following checklist once: compilation/support, legal signals, reset guard, antecedent reachability, non-vacuity, seen-good acceptance, seen-bad rejection, and literal hardcoding. Repair only visible defects."
    else:
        diagnosis = FEEDBACK[str(row.diagnosis_supplied)]
    return f"""Repair this SystemVerilog assertion exactly once. Return exactly one complete `assert property` statement and no explanation.

You may use only the information below. Do not infer or request any golden assertion, held-out trace, expected property, mutation line, or buggy RTL line.
Allowed signals: {', '.join(allowed_signals(case_dir))}

Correct RTL context:
```systemverilog
{(case_dir/'correct.v').read_text(encoding='utf-8', errors='replace')}
```

{context}

Original assertion:
{row.original_assertion}

Visible diagnostic feedback:
{diagnosis}

Avoid trace-specific cycle numbers or literal values unless they are justified by the visible RTL/interface.
"""


def eval_assertion(repair_id: str, phase: str, case_id: str, assertion: str) -> tuple[dict, dict]:
    case_dir = CASES / case_id; static = static_checks(assertion, case_dir)
    try:
        result = run_case_eval(case_id=case_id, assertion_text=assertion, signal_names=allowed_signals(case_dir), use_property=False, runtime_dir=OUT/"runtime"/repair_id/phase, cases_root=CASES)
    except Exception as exc:
        result = {k:False for k in ["compile_ok","correct_pass","buggy_fail","antecedent_hit","non_vacuous","heldout_correct_pass","heldout_buggy_fail","heldout_antecedent_hit","heldout_non_vacuous","trace_overfit"]}
        result["evaluation_error"] = f"{type(exc).__name__}: {exc}"
    return result, static


def category_fixed(category: str, ev: dict, st: dict) -> bool:
    return {"compile_fail":ev["compile_ok"], "unsupported":st["parser_support"], "vacuity":ev["non_vacuous"], "antecedent_not_triggered":ev["antecedent_hit"], "too_strong":ev["correct_pass"], "too_weak":ev["buggy_fail"], "signal_missing":st["signal_legal"], "reset_misuse":st["reset_valid"], "hardcoding":st["no_hardcoding"]}[category]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    targets = materialize_targets(); temporal = {x["case_id"]:x["abstracted_summary"] for x in json.loads(TEMPORAL.read_text(encoding="utf-8"))}
    cache_path = OUT/"repair_cache.json"; cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    for row in targets.itertuples(index=False):
        if row.repair_id in cache: continue
        prompt = build_prompt(pd.Series(row._asdict()), temporal)
        forbidden = [x for x in ["golden assertion:", "held-out trace:", "mutation line:", "buggy rtl line:"] if x in prompt.lower()]
        if forbidden: raise RuntimeError(f"forbidden prompt content: {forbidden}")
        print(f"[REPAIR] {row.repair_id} {row.model_label} {row.primary_failure} {row.prompt_arm}", file=sys.stderr)
        response = post_model_chat(model_spec(row.model_label), prompt, temperature=0.2)
        candidates = extract_sva_candidates(response); repaired = candidates[0] if candidates else ""
        cache[row.repair_id] = {"prompt":prompt, "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(), "raw_response":response, "repaired_assertion":repaired, "model_call_count":1}
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    output=[]
    for row in targets.itertuples(index=False):
        c=cache[row.repair_id]; before,bs=eval_assertion(row.repair_id,"before",row.case_id,row.original_assertion)
        repaired=c["repaired_assertion"]
        if repaired: after,ast=eval_assertion(row.repair_id,"after",row.case_id,repaired)
        else: after={k:False for k in ["compile_ok","correct_pass","buggy_fail","antecedent_hit","non_vacuous","heldout_correct_pass","heldout_buggy_fail","heldout_antecedent_hit","heldout_non_vacuous","trace_overfit"]}; ast={k:False for k in ["parser_support","signal_legal","reset_valid","no_hardcoding"]}
        def strict(ev,st,held=False):
            p="heldout_" if held else ""; return bool(ev.get(p+"correct_pass") and ev.get(p+"buggy_fail") and ev.get(p+"antecedent_hit") and ev.get(p+"non_vacuous") and st["parser_support"] and st["signal_legal"] and st["reset_valid"])
        feedback_text = "Unified visible-check checklist" if row.prompt_arm == "unified" else FEEDBACK[row.diagnosis_supplied]
        rec={"repair_id":row.repair_id,"model":row.model_label,"case_id":row.case_id,"parent_bug_id":row.parent_bug_id,"candidate_uid":row.candidate_uid,"representation":row.representation,"primary_failure":row.primary_failure,"prompt_arm":row.prompt_arm,"diagnosis_supplied":row.diagnosis_supplied,"diagnostic_feedback":feedback_text,"diagnosis_is_correct":row.prompt_arm!="wrong_diagnosis","synthetic_static_case":row.synthetic_static_case,"model_call_count":c["model_call_count"],"prompt_sha256":c["prompt_sha256"],"repair_prompt":c["prompt"],"raw_response":c["raw_response"],"original_assertion":row.original_assertion,"repaired_assertion":repaired,"primary_failure_fixed":category_fixed(row.primary_failure,after,ast),"before_seen_strict_success":strict(before,bs),"after_seen_strict_success":strict(after,ast),"before_heldout_strict_success":strict(before,bs,True),"after_heldout_strict_success":strict(after,ast,True)}
        for phase,ev,st in [("before",before,bs),("after",after,ast)]:
            rec.update({f"{phase}_compile_ok":ev.get("compile_ok",False),f"{phase}_false_positive":bool(ev.get("compile_ok") and not ev.get("heldout_correct_pass")),f"{phase}_vacuity":bool(ev.get("compile_ok") and not ev.get("heldout_non_vacuous")),f"{phase}_overfit":bool(ev.get("trace_overfit")),f"{phase}_parser_support":st["parser_support"],f"{phase}_signal_legal":st["signal_legal"],f"{phase}_reset_valid":st["reset_valid"],f"{phase}_no_hardcoding":st["no_hardcoding"]})
        output.append(rec)
    main_df=pd.DataFrame(output); main_df.to_csv(OUT/"one_step_repair_main.csv",index=False,encoding="utf-8-sig")
    rates=main_df.groupby(["primary_failure","prompt_arm"],as_index=False).agg(target_count=("repair_id","size"),fixed_count=("primary_failure_fixed","sum"),repair_rate=("primary_failure_fixed","mean"),seen_success_rate=("after_seen_strict_success","mean"),heldout_success_rate=("after_heldout_strict_success","mean"))
    overall_rates=main_df.groupby("primary_failure",as_index=False).agg(target_count=("repair_id","size"),fixed_count=("primary_failure_fixed","sum"),repair_rate=("primary_failure_fixed","mean"),seen_success_rate=("after_seen_strict_success","mean"),heldout_success_rate=("after_heldout_strict_success","mean")); overall_rates.insert(1,"prompt_arm","ALL")
    rates=pd.concat([overall_rates,rates],ignore_index=True).sort_values(["primary_failure","prompt_arm"])
    rates.to_csv(OUT/"repair_rate_by_failure.csv",index=False,encoding="utf-8-sig")
    risk=[]
    for keys,g in [("ALL",main_df),*list(main_df.groupby("prompt_arm",sort=True))]:
        for metric in ["false_positive","vacuity","overfit"]:
            before=g[f"before_{metric}"].astype(bool); after=g[f"after_{metric}"].astype(bool); b=before.mean();a=after.mean();risk.append({"prompt_arm":keys,"metric":metric,"target_count":len(g),"before_count":int(before.sum()),"before_rate":b,"after_count":int(after.sum()),"after_rate":a,"rate_change":a-b,"introduced_count":int((~before&after).sum()),"resolved_count":int((before&~after).sum())})
    pd.DataFrame(risk).to_csv(OUT/"pre_post_false_positive_vacuity_overfit.csv",index=False,encoding="utf-8-sig")
    main_df.to_csv(OUT/"complete_cases_by_failure.csv",index=False,encoding="utf-8-sig")
    audit={"status":"pass","target_count":len(main_df),"failure_types":CATEGORIES,"prompt_arms":ARMS,"targets_per_failure":main_df.groupby('primary_failure').size().to_dict(),"targets_per_failure_arm":main_df.groupby(['primary_failure','prompt_arm']).size().astype(int).to_dict(),"max_model_calls_per_candidate":int(main_df.model_call_count.max()),"all_exactly_one_model_call":bool(main_df.model_call_count.eq(1).all()),"golden_or_heldout_in_prompt":False,"wrong_diagnosis_mapping":WRONG,"prompt_sha256_unique":int(main_df.prompt_sha256.nunique())}
    audit["targets_per_failure_arm"]={"|".join(k):v for k,v in audit["targets_per_failure_arm"].items()}
    (OUT/"repair_audit.json").write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(audit,ensure_ascii=False,indent=2))

if __name__=="__main__": main()
