from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
DIRECT=ROOT/"outputs/019ed9f6-87cf-7830-adb8-595fe2ae140d/multi_model_eval_data/multi_model_results_raw.csv"
TWO_STAGE=ROOT/"outputs/cross_model_qwen_two_stage_v1/qwen_two_stage_results.csv"
OUT=ROOT/"outputs/cross_model_failure_analysis_v1"

def truth(d:pd.DataFrame,name:str,alt:str|None=None,default=False):
    key=name if name in d else alt
    if not key or key not in d:return pd.Series(default,index=d.index)
    return d[key].astype(str).str.lower().isin(["true","1","yes"])
def sha(p:Path):return hashlib.sha256(p.read_bytes()).hexdigest()
def annotate(d:pd.DataFrame)->pd.DataFrame:
    d=d.copy();d["compile_fail"]=~truth(d,"compile_ok");d["vacuity"]=truth(d,"compile_ok")&(~truth(d,"non_vacuous_buggy","non_vacuous")|~truth(d,"antecedent_hit_buggy","antecedent_hit"));d["too_strong"]=truth(d,"compile_ok")&~truth(d,"correct_pass");d["too_weak"]=truth(d,"compile_ok")&truth(d,"correct_pass")&~truth(d,"buggy_fail");d["false_positive"]=~truth(d,"heldout_correct_pass");d["missed_detection"]=truth(d,"heldout_correct_pass")&~truth(d,"heldout_buggy_fail");d["trace_overfit"]=truth(d,"trace_overfit");d["strict_success"]=truth(d,"compile_ok")&truth(d,"correct_pass")&truth(d,"buggy_fail")&truth(d,"antecedent_hit_buggy","antecedent_hit")&truth(d,"non_vacuous_buggy","non_vacuous")&truth(d,"heldout_correct_pass")&truth(d,"heldout_buggy_fail")&truth(d,"heldout_antecedent_hit")&truth(d,"heldout_non_vacuous");return d
METRICS=["compile_fail","vacuity","too_strong","too_weak","false_positive","missed_detection","trace_overfit","strict_success"]
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out-dir",default=str(OUT));args=ap.parse_args();out=Path(args.out_dir).resolve();out.mkdir(parents=True,exist_ok=True)
    direct=pd.read_csv(DIRECT,encoding="utf-8-sig");direct["baseline"]="direct_sva";frames=[direct]
    inputs=[DIRECT]
    if TWO_STAGE.exists():frames.append(pd.read_csv(TWO_STAGE,encoding="utf-8-sig"));inputs.append(TWO_STAGE)
    data=annotate(pd.concat(frames,ignore_index=True,sort=False));detail=out/"cross_model_annotated_candidates.csv";data.to_csv(detail,index=False,encoding="utf-8-sig")
    summaries=[]
    for scope,frame in [("candidate",data),("first_candidate",data.sort_values("candidate_index").drop_duplicates(["model_label","baseline","case_id","method"]))]:
      for keys,g in frame.groupby(["model_label","baseline"]):
        row={"scope":scope,"model":keys[0],"baseline":keys[1],"k":1 if scope=="first_candidate" else int(g.groupby(["case_id","method"]).size().max()),"sample_count":len(g),"case_count":g.case_id.nunique(),"cell_count":g.groupby(["case_id","method"]).ngroups}
        for x in METRICS:row[x+"_count"]=int(g[x].sum());row[x+"_rate"]=float(g[x].mean())
        summaries.append(row)
    # any-of-k: errors are reported as fraction of cells with any candidate exhibiting the error; success is any strict success.
    for keys,g in data.groupby(["model_label","baseline"]):
      cells=g.groupby(["case_id","method"])[METRICS].any();row={"scope":"case_method_any_of_k","model":keys[0],"baseline":keys[1],"k":int(g.groupby(["case_id","method"]).size().max()),"sample_count":len(cells),"case_count":g.case_id.nunique(),"cell_count":len(cells)}
      for x in METRICS:row[x+"_count"]=int(cells[x].sum());row[x+"_rate"]=float(cells[x].mean())
      summaries.append(row)
    summary=pd.DataFrame(summaries);summary_path=out/"cross_model_metric_summary.csv";summary.to_csv(summary_path,index=False,encoding="utf-8-sig")
    ir_path=out/"qwen_two_stage_ir_summary.json"
    if "ir_json_valid" in data.columns and data.ir_json_valid.notna().any():
      two=data[data.baseline=="structured_property_to_sva"].copy(); ir={"cell_count":len(two),"ir_json_valid_count":int(truth(two,"ir_json_valid").sum()),"ir_schema_complete_count":int(truth(two,"ir_schema_complete").sum()),"ir_signals_valid_count":int(truth(two,"ir_signals_valid").sum()),"ir_valid_but_sva_compile_fail_count":int((truth(two,"ir_schema_complete")&~truth(two,"compile_ok")).sum()),"compiled_but_not_strict_success_count":int((truth(two,"compile_ok")&~two.strict_success).sum())};ir_path.write_text(json.dumps(ir,indent=2),encoding="utf-8")
    outputs={str(detail):sha(detail),str(summary_path):sha(summary_path)}
    if ir_path.exists():outputs[str(ir_path)]=sha(ir_path)
    freeze={"status":"frozen" if TWO_STAGE.exists() else "direct_only_pending_qwen_two_stage","metric_definitions":{x:x for x in METRICS},"input_sha256":{str(p.resolve()):sha(p) for p in inputs},"output_sha256":outputs};(out/"cross_model_analysis_freeze.json").write_text(json.dumps(freeze,indent=2),encoding="utf-8");print(summary_path)
if __name__=="__main__":main()
