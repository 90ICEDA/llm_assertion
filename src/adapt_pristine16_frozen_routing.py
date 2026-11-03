from __future__ import annotations

import argparse, csv, hashlib, json, re, shutil
from collections import Counter
from pathlib import Path
from typing import Any

from trace_router import CONTROL_TOKENS, DELAY_RE, canonical_hash, file_sha256, route

ROOT=Path(__file__).resolve().parents[1]

def seal_hash(payload:dict[str,Any])->str:
    clean=dict(payload);clean.pop("seal_sha256",None)
    return hashlib.sha256(json.dumps(clean,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def load_csv(path:Path)->list[dict[str,str]]:
    with path.open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def leaf(name:str)->str:return name.split(".")[-1]

def features(case_dir:Path,meta:dict[str,Any],primary:dict[str,Any])->dict[str,Any]:
    good=load_csv(case_dir/"waveform_good.csv");bad=load_csv(case_dir/"waveform_bad.csv")
    bmap={r["time_ps"]:r for r in bad};pairs=[(g,bmap[g["time_ps"]]) for g in good if g["time_ps"] in bmap]
    diff_rows=[]
    for i,(g,b) in enumerate(pairs):
        ds=sorted(k for k in set(g)&set(b) if k!="time_ps" and g[k]!=b[k])
        if ds:diff_rows.append((i,ds))
    if not diff_rows:raise RuntimeError(f"no primary divergence: {case_dir.name}")
    first=diff_rows[0][0];window=0
    expected=first
    for index,_ in diff_rows:
        if index!=expected:break
        window+=1;expected+=1
    all_diff=sorted({leaf(s) for _,signals in diff_rows for s in signals})
    relevant=[str(x) for x in meta.get("relevant_signals",[])]
    control=sum(any(token in s.lower() for token in CONTROL_TOKENS) for s in relevant)
    ratio=control/len(relevant) if relevant else 0.0
    temporal_type=str(meta.get("temporal_type", ""));spec=str(meta.get("spec", ""))
    cross=meta.get("bug_class")=="temporal_cross_cycle" or "cross-cycle" in temporal_type.lower()
    # Use the representation generator's primary provenance as an independent consistency check.
    prov=primary["provenance"]
    if int(prov["first_divergence_time_ps"])!=int(pairs[first][0]["time_ps"]):
        raise RuntimeError(f"representation/waveform divergence mismatch: {case_dir.name}")
    return {"case_id":case_dir.name,"parent_bug_id":meta["parent_bug_id"],"trace_length":len(pairs),
        "first_divergence_distance":first,"divergence_window":window,"differing_signal_count":len(all_diff),
        "is_cross_cycle":bool(cross),"has_explicit_delay":bool(DELAY_RE.search(spec+" "+temporal_type)),
        "control_signal_ratio":round(ratio,6),"data_signal_ratio":round(1-ratio,6),"differing_signals":",".join(all_diff)}

def main()->None:
    ap=argparse.ArgumentParser(description="Read-only adapter from sealed pristine waveforms to a frozen router policy.")
    ap.add_argument("--root",default=str(ROOT/"rtl_cases_real_scale210_independent"));ap.add_argument("--seal",default=str(ROOT/"outputs/pristine_trace_router_v1/sealed_test_manifest.json"))
    ap.add_argument("--representations",default=str(ROOT/"outputs/pristine_trace_router_v1/trace_representations.json"));ap.add_argument("--policy",default=str(ROOT/"outputs/formal_multimodel/locked_policy_multimodel.json"))
    ap.add_argument("--output-dir",default=str(ROOT/"outputs/pristine_trace_router_v1"));args=ap.parse_args()
    root,seal_path,reps_path,policy_path,out=map(Path,(args.root,args.seal,args.representations,args.policy,args.output_dir));out.mkdir(parents=True,exist_ok=True)
    policy=json.loads(policy_path.read_text(encoding="utf-8"));seal=json.loads(seal_path.read_text(encoding="utf-8"));reps=json.loads(reps_path.read_text(encoding="utf-8"))
    if not policy.get("locked") or canonical_hash(policy)!=policy.get("policy_sha256"):raise RuntimeError("policy is not cryptographically locked")
    if seal_hash(seal)!=seal.get("seal_sha256") or not seal.get("sealed"):raise RuntimeError("pristine seal hash mismatch")
    for pk,hk in (("router_code_path","router_code_sha256"),("dev_results_path","dev_results_sha256"),("dev_results_manifest_path","dev_results_manifest_sha256"),("temporal_summaries_path","temporal_summaries_sha256"),("manifest_path","manifest_sha256")):
        p=Path(policy["provenance"][pk]);
        if not p.exists() or file_sha256(p)!=policy["provenance"][hk]:raise RuntimeError(f"policy provenance mismatch: {pk}")
    rep_lookup={x["case_id"]:x for x in reps};rows=[];flat=[];view_cases=[];models=sorted(policy["params"]["model_overlap_resolution"])
    view=out/"dispatcher_view";view.mkdir(parents=True,exist_ok=True)
    for sealed in seal["cases"]:
        cid=sealed["case_id"];d=root/cid
        for fn,key in (("correct.v","correct_rtl_sha256"),("buggy.v","buggy_rtl_sha256"),("rtl_mutation.diff","mutation_diff_sha256")):
            if file_sha256(d/fn)!=sealed[key]:raise RuntimeError(f"sealed artifact changed: {cid}/{fn}")
        meta=json.loads((d/"case_metadata.json").read_text(encoding="utf-8"));r=rep_lookup[cid];primary=next(x for x in r["representations"] if x["variant"]=="primary")
        feat=features(d,meta,primary);flat.append({"case_id":cid,"abstracted_summary":primary["temporal_relation_abstraction"],"source":"sealed_pristine_primary_contract_v1"})
        vd=view/cid;exp=vd/"experiment";prompts=exp/"prompts";prompts.mkdir(parents=True,exist_ok=True)
        for source in d.glob("tb*"):shutil.copy2(source,vd/source.name)
        for name in ("correct.v","buggy.v","rtl_mutation.diff"):shutil.copy2(d/name,vd/name)
        spec=str(meta["spec"]);visible={leaf(c).split("[")[0] for c in load_csv(d/"waveform_good.csv")[0] if c!="time_ps"}
        allowed=[s for s in meta.get("relevant_signals",[]) if s.split("[")[0] in visible]
        if not allowed:raise RuntimeError(f"no visible allowed signals: {cid}")
        raw="Good trace (observed primary CSV):\n"+primary["raw_trace"]["good_csv"]+"\nBad trace (observed primary CSV):\n"+primary["raw_trace"]["bad_csv"]
        base=f"Allowed signals:\n{', '.join(allowed)}\n\nSpecification:\n{spec}\n";rtl=(d/"correct.v").read_text(encoding="utf-8")
        (exp/"spec.txt").write_text(spec+"\n",encoding="utf-8");(exp/"trace_good.txt").write_text(primary["raw_trace"]["good_csv"],encoding="utf-8");(exp/"trace_bad.txt").write_text(primary["raw_trace"]["bad_csv"],encoding="utf-8");(exp/"trace_summary.txt").write_text(primary["naive_summary"]+"\n",encoding="utf-8")
        (prompts/"prompt_1_spec_only.txt").write_text(base,encoding="utf-8");(prompts/"prompt_2_spec_plus_rtl.txt").write_text(base+"\nRTL:\n"+rtl,encoding="utf-8");(prompts/"prompt_3_spec_rtl_raw_trace.txt").write_text(base+"\nRTL:\n"+rtl+"\n\n"+raw,encoding="utf-8")
        view_cases.append(meta)
        for model in models:
            decision,reason=route(feat,model,policy["params"]);rows.append({"model":model,**feat,"route":decision,"route_reason":reason,"policy_sha256":policy["policy_sha256"],"seal_sha256":seal["seal_sha256"],"representations_sha256":file_sha256(reps_path)})
    routing=out/"test_routing.csv"
    with routing.open("w",encoding="utf-8-sig",newline="") as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    temporal=out/"dispatcher_temporal_primary.json";temporal.write_text(json.dumps(flat,indent=2,ensure_ascii=False),encoding="utf-8")
    (view/"case_manifest.json").write_text(json.dumps({"cases":view_cases},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    summary={"adapter":"pristine_waveform_adapter_v1","read_only_sources":True,"policy_refit":False,"dispatcher_view":str(view.resolve()),"policy_sha256":policy["policy_sha256"],"seal_sha256":seal["seal_sha256"],"case_count":len(seal["cases"]),"parent_count":len({x["parent_bug_id"] for x in rows}),"model_case_rows":len(rows),"models":models,"route_counts":Counter(x["route"] for x in rows),"routing_sha256":file_sha256(routing),"representations_sha256":file_sha256(reps_path),"temporal_primary_sha256":file_sha256(temporal),"dev_test_parent_overlap":False}
    (out/"routing_adapter_summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8");print(json.dumps(summary,indent=2,ensure_ascii=False))

if __name__=="__main__":main()
