from __future__ import annotations
import argparse,time
from pathlib import Path
import pandas as pd
from build_candidate_count_cost_experiment import load,OUT
from run_trace_abstraction_prototype import run_case_eval

ROOT=Path(__file__).resolve().parents[1];CASES=ROOT/'rtl_cases_real_scale120'
def signals(case):
 import csv,re
 with (CASES/case/'waveform_good.csv').open(encoding='utf-8-sig',newline='') as h:head=next(csv.reader(h))
 return [re.sub(r'\[.*$','',x.strip()) for x in head if x.strip()!='time_ps']
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',default=str(OUT/'validation_timing.csv'));ap.add_argument('--resume',action='store_true');args=ap.parse_args();out=Path(args.out).resolve();out.parent.mkdir(parents=True,exist_ok=True);pool=load();old=pd.read_csv(out,encoding='utf-8-sig') if args.resume and out.exists() else pd.DataFrame();done=set(zip(old.model_label,old.case_id,old.slot)) if not old.empty else set();rows=[] if old.empty else old.to_dict('records')
 for i,r in enumerate(pool.itertuples(),1):
  key=(r.model_label,r.case_id,r.slot)
  if key in done:continue
  start=time.perf_counter();ev=run_case_eval(case_id=r.case_id,assertion_text=r.assertion_text,signal_names=signals(r.case_id),use_property=False,runtime_dir=out.parent/'validation_runtime'/r.model_label/r.case_id/f'slot_{r.slot}',cases_root=CASES);elapsed=time.perf_counter()-start
  rows.append({'model_label':r.model_label,'case_id':r.case_id,'parent_bug_id':r.parent_bug_id,'slot':r.slot,'validation_time_sec':elapsed,'compile_ok_replay':ev['compile_ok'],'strict_success_replay':bool(ev['compile_ok'] and ev['correct_pass'] and ev['buggy_fail'] and ev['antecedent_hit'] and ev['non_vacuous'] and ev['heldout_correct_pass'] and ev['heldout_buggy_fail'] and ev['heldout_antecedent_hit'] and ev['heldout_non_vacuous'])});pd.DataFrame(rows).to_csv(out,index=False,encoding='utf-8-sig');print(f'[{i}/{len(pool)}] {r.model_label} {r.case_id} slot={r.slot} {elapsed:.3f}s',flush=True)
 print(out)
if __name__=='__main__':main()
