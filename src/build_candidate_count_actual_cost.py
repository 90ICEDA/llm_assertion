from __future__ import annotations

import argparse, hashlib, json, re
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
KS = (1, 2, 4, 8)

def sha(p: Path) -> str: return hashlib.sha256(p.read_bytes()).hexdigest()
def truth(s: pd.Series) -> pd.Series: return s.astype(str).str.lower().isin(("true", "1", "yes"))
def canon(x: object) -> str: return re.sub(r"\s+", " ", str(x or "")).strip()

def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--run-dir", default="outputs/candidate_count_cost_v2_actual"); ap.add_argument("--parent-map", default="outputs/dev_locked_score_reranker/selected_candidates.csv"); args=ap.parse_args()
    out=Path(args.run_dir).resolve(); rawp=out/"multi_model_results_raw.csv"; promptp=out/"multi_model_prompt_log.csv"
    raw=pd.read_csv(rawp, encoding="utf-8-sig"); prompts=pd.read_csv(promptp, encoding="utf-8-sig")
    raw=raw[raw.method.isin(("spec_rtl_raw_trace","spec_rtl_temporal_relation_abstraction"))].copy()
    raw["rep"]=raw.method.map({"spec_rtl_raw_trace":"raw","spec_rtl_temporal_relation_abstraction":"temporal"})
    raw["candidate_index"]=pd.to_numeric(raw.candidate_index).astype(int); raw["slot"]=2*(raw.candidate_index-1)+(raw.rep=="temporal").astype(int)+1
    raw["strict"]=truth(raw.compile_ok)&truth(raw.correct_pass)&truth(raw.buggy_fail)&truth(raw.antecedent_hit_buggy)&truth(raw.non_vacuous_buggy)&truth(raw.heldout_correct_pass)&truth(raw.heldout_buggy_fail)&truth(raw.heldout_antecedent_hit)&truth(raw.heldout_non_vacuous)
    raw["canonical"]=raw.assertion_text.map(canon)
    # Apply the already locked seen-only score signs; no held-out field enters selection.
    policy=json.loads((ROOT/"outputs/dev_locked_score_reranker/score_policy_lock.json").read_text()) ["weights"]
    raw["seen_score"]=(policy["compile"]*truth(raw.compile_ok).astype(int)+policy["seen_correct"]*truth(raw.correct_pass).astype(int)+policy["seen_buggy_fail"]*truth(raw.buggy_fail).astype(int)+policy["antecedent_hit"]*truth(raw.antecedent_hit_buggy).astype(int)+policy["non_vacuous"]*truth(raw.non_vacuous_buggy).astype(int)+policy["hardcoding"]*truth(raw.literal_hardcoding).astype(int))
    pm=pd.read_csv(args.parent_map,encoding="utf-8-sig")[["case_id","parent_bug_id"]].drop_duplicates(); raw=raw.merge(pm,on="case_id",how="left")
    if raw.groupby(["model_label","case_id"]).slot.nunique().min()!=8: raise RuntimeError("Fresh pool is incomplete: every model/case needs eight ordered candidates")
    metrics={}
    for r in prompts.itertuples():
        calls=json.loads(getattr(r,"generation_call_metrics_json","[]") or "[]"); metrics[(r.model_label,r.case_id,r.method)]=calls
    details=[]; summaries=[]
    for model, md in raw.groupby("model_label"):
        previous=set(); prev_pt=prev_ot=0; prev_gt=prev_vt=0.0
        for k in KS:
            sub=md[md.slot<=k]; cells=[]
            for case,g in sub.groupby("case_id"):
                g=g.sort_values("slot"); top=g.sort_values(["seen_score","slot"],ascending=[False,True]).iloc[0]
                cells.append({"model":model,"case_id":case,"parent_bug_id":g.parent_bug_id.iloc[0],"k":k,"first_candidate":bool(g.iloc[0].strict),"any_of_k":bool(g.strict.any()),"reranker_top1":bool(top.strict),"reranker_slot":int(top.slot),"duplicate_rate":1-g.canonical.nunique()/len(g)})
            c=pd.DataFrame(cells); details.extend(c.to_dict("records")); success=set(c.loc[c.any_of_k,"case_id"]); new=len(success-previous); previous=success
            pt=ot=0; gt=0.0; used=total_calls=0
            max_index_raw=(k+1)//2; max_index_temporal=k//2
            for (ml,case,method), calls in metrics.items():
                if ml!=model: continue
                limit=max_index_raw if method=="spec_rtl_raw_trace" else max_index_temporal
                for call in calls:
                    start=call.get("new_candidate_start")
                    if start is not None and int(start)<=limit:
                        total_calls+=1; used+=int(bool(call.get("usage_available"))); pt+=int(call.get("prompt_tokens") or 0); ot+=int(call.get("output_tokens") or 0); gt+=float(call.get("duration_sec") or 0)
            vt=float(pd.to_numeric(sub.validation_time_sec,errors="coerce").fillna(0).sum())
            dpt,dot,dgt,dvt=pt-prev_pt,ot-prev_ot,gt-prev_gt,vt-prev_vt; delta=dpt+dot
            summaries.append({"model":model,"k":k,"case_count":len(c),"parent_count":c.parent_bug_id.nunique(),"first_candidate_success_count":int(c.first_candidate.sum()),"first_candidate_success_rate":c.first_candidate.mean(),"any_of_k_success_count":int(c.any_of_k.sum()),"any_of_k_success_rate":c.any_of_k.mean(),"reranker_top1_success_count":int(c.reranker_top1.sum()),"reranker_top1_success_rate":c.reranker_top1.mean(),"duplicate_rate":c.duplicate_rate.mean(),"new_success_cases_vs_previous_k":new,"prompt_tokens_actual":pt,"output_tokens_actual":ot,"total_tokens_actual":pt+ot,"api_call_count":total_calls,"usage_call_count":used,"usage_complete":used==total_calls,"generation_time_sec":gt,"validation_time_sec":vt,"incremental_tokens":delta,"incremental_generation_time_sec":dgt,"incremental_validation_time_sec":dvt,"tokens_per_new_success":None if not new else delta/new,"generation_sec_per_new_success":None if not new else dgt/new,"validation_sec_per_new_success":None if not new else dvt/new})
            prev_pt,prev_ot,prev_gt,prev_vt=pt,ot,gt,vt
    dp=out/"candidate_count_case_results.csv"; sp=out/"candidate_count_summary.csv"; pd.DataFrame(details).to_csv(dp,index=False,encoding="utf-8-sig"); pd.DataFrame(summaries).to_csv(sp,index=False,encoding="utf-8-sig")
    inputs=[rawp,promptp,Path(args.parent_map).resolve(),ROOT/"outputs/dev_locked_score_reranker/score_policy_lock.json"]; outputs=[dp,sp]
    freeze={"status":"frozen_actual_provider_usage_and_timing","fresh_run":True,"candidate_order":["raw1","temporal1","raw2","temporal2","raw3","temporal3","raw4","temporal4"],"usage_policy":"provider response usage only; missing usage is never estimated","selection_policy":"dev-locked seen-only weights; held-out excluded","input_sha256":{str(p):sha(p) for p in inputs},"output_sha256":{str(p):sha(p) for p in outputs}}
    (out/"candidate_count_freeze.json").write_text(json.dumps(freeze,indent=2,ensure_ascii=False),encoding="utf-8"); print(sp)

if __name__=="__main__": main()
