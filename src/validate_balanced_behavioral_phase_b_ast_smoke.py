from __future__ import annotations
import argparse,csv,json,shutil,subprocess,sys,time
from pathlib import Path
from evaluate_frozen_top1_v1 import derived,primitive_bools,run_case_eval
from validate_pilot_v2_ast_smoke_v2 import KEYS,dump,native_parse,render,sha

ROOT=Path(__file__).resolve().parents[1]; P1=ROOT/"outputs/behavioral_preference_pilot_v1"; BASE=ROOT/"outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1"; SOURCE=BASE/"ast_smoke_v1"; OUT=BASE/"ast_smoke_v1_validation"
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--reuse-static-validation",action="store_true"); ap.add_argument("--resume",action="store_true"); args=ap.parse_args()
    if not args.reuse_static_validation and not shutil.which("iverilog"): raise SystemExit("ERROR: run inside WSL/Linux with iverilog")
    if args.reuse_static_validation:
        pyslang_version="11.0.0 (reused from first WSL static-validation pass)"
    else:
        import pyslang
        pyslang_version=getattr(pyslang,"__version__","unknown")
    with (P1/"selected_train_parents.csv").open(encoding="utf-8-sig",newline="") as f: parents={r["parent_bug_id"]:r for r in csv.DictReader(f)}
    interfaces={}
    for path in sorted((P1/"sequential_generation_v3_pilot30").rglob("evidence.json")):
        value=json.loads(path.read_text()); interfaces.setdefault(value["parent_bug_id"],{"signals":value["signals"],"clock":value.get("clock"),"reset":value.get("reset")})
    records=[]
    for evidence_path in sorted((SOURCE/"generations").rglob("evidence.json")):
        source=json.loads(evidence_path.read_text()); parent,slot=source["parent"],int(source["slot"]); source_dir=evidence_path.parent; dest=OUT/"records"/parent/f"slot_{slot:02d}"; dest.mkdir(parents=True,exist_ok=True)
        existing=dest/"validation_evidence.json"
        if args.resume and existing.is_file():
            old=json.loads(existing.read_text())
            if old.get("execution_completed") is True and old.get("compile_ok") is True:
                records.append(old); continue
        ast=json.loads((source_dir/"ast.json").read_text()); interface=interfaces[parent]; signals,clock,reset=interface["signals"],interface["clock"],interface["reset"]; schema=tuple(ast)==KEYS; used={ast["antecedent_signal"],ast["consequent_signal"]}; legal=used<=set(signals) and not used.intersection({clock,reset}); sva=render(ast,clock,reset); candidate=dest/"candidate.sva"; candidate.write_text(sva+"\n")
        if args.reuse_static_validation:
            old=json.loads((dest/"validation_evidence.json").read_text()); native_ok=old["pyslang_ok"]; diagnostics=old["pyslang_diagnostics"]
        else:
            native_ok,diagnostics,native_input=native_parse(sva,signals); (dest/"pyslang_input.sv").write_text(native_input); dump(dest/"pyslang_diagnostics.json",diagnostics)
        metadata=parents[parent]; case=ROOT/metadata["dataset_root"]/metadata["case_id"]; started=time.perf_counter()
        try: result=run_case_eval(case_id=metadata["case_id"],assertion_text=sva,signal_names=signals,use_property=False,runtime_dir=OUT/"runtime"/parent/f"slot_{slot:02d}",cases_root=case.parent)
        except Exception as exc: result={"compile_ok":False,"correct_pass":False,"buggy_fail":False,"antecedent_hit":False,"non_vacuous":False,"heldout_correct_pass":False,"heldout_buggy_fail":False,"heldout_antecedent_hit":False,"heldout_non_vacuous":False,"trace_overfit":False,"evaluation_error":f"{type(exc).__name__}: {exc}"}
        row={"status":"complete","variant":"anchor_20_all30","parent":parent,"slot":slot,"source_evidence_sha256":sha(evidence_path),"ast_sha256":sha(source_dir/"ast.json"),"schema_valid":schema,"render_ok":True,"signal_legal":legal,"pyslang_ok":native_ok,"pyslang_diagnostics":diagnostics,"candidate_sva_sha256":sha(candidate),**primitive_bools(result),**derived(result),"evaluation_error":result.get("evaluation_error"),"execution_completed":result.get("evaluation_error") in (None,""),"wall_clock_seconds":time.perf_counter()-started,"raw_evaluation":result}; dump(dest/"validation_evidence.json",row); records.append(row); print(parent,slot,schema,legal,native_ok,row["compile_ok"],row["execution_completed"],flush=True)
    required=("schema_valid","render_ok","signal_legal","pyslang_ok","compile_ok","execution_completed"); totals={x:sum(bool(r[x]) for r in records) for x in required}; groups={}
    for row in records: groups.setdefault(row["parent"],[]).append(row)
    group_gate={p:len(rs)==8 and all(all(r[x] for x in required) for r in rs) for p,rs in groups.items()}
    summary={"status":"pass" if len(records)==24 and all(v==24 for v in totals.values()) and all(group_gate.values()) else "fail","source_manifest_sha256":sha(SOURCE/"smoke_manifest.json"),"record_count":len(records),"totals":totals,"group_8_of_8":group_gate,"behavior_observations":{"fixed_safe":sum(r["fixed_safe"] for r in records),"target_detect":sum(r["target_detect"] for r in records),"strict_success":sum(r["strict_success"] for r in records),"non_vacuous":sum(r["non_vacuity_metric"] for r in records),"trace_overfit":sum(r["trace_overfit"] for r in records)},"timeouts_or_errors":sum(not r["execution_completed"] for r in records),"tool_versions":{"python":sys.version,"pyslang":pyslang_version,"iverilog":subprocess.run(["wsl","bash","-lc","iverilog -V"],capture_output=True,text=True).stdout.splitlines()[:2] if args.reuse_static_validation else subprocess.run(["iverilog","-V"],capture_output=True,text=True).stdout.splitlines()[:2]},"gate_definition":"24/24 schema, deterministic render, visible-signal, pyslang, executable harness compile and completed fixed/buggy/heldout execution; behavior outcomes recorded but not required to be uniformly successful"}; dump(OUT/"validation_summary.json",summary); dump(OUT/"validation_artifact_hashes.json",{str(p.relative_to(ROOT)).replace("\\","/"):sha(p) for p in sorted(OUT.rglob("*")) if p.is_file() and p.name!="validation_artifact_hashes.json"}); print(json.dumps(summary,sort_keys=True))
if __name__=="__main__": main()
