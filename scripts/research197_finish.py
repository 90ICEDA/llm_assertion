"""Post-freeze local pipeline. No external model calls, no automatic retries."""
import argparse
from pathlib import Path
import subprocess
import sys
import time
from research194_refinement_runner import ROOT,read,dump,file_hash


def finish(prepared,execution,out):
    from research197_prepare import verify
    verify(prepared)
    prepared,execution,out=(Path(p).resolve() for p in (prepared,execution,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_versions_must_freeze')
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'deliverables'
    cost=base/'research197_cost_sections_20261104_r01';cards=base/'research197_case_cards_20261104_r01'
    ind=base/'research197_independent_20261104_r01';report=base/'reguard_mechanisms_20261104_r07'
    phases=[('register_cost','research197_cost_sections.py',['register','--prepared',prepared,'--execution',execution,'--out',cost]),
        ('select_cards','research197_cards.py',['select','--prepared',prepared,'--execution',execution,'--out',cards]),
        ('independent_acceptance','research197_independent.py',['--prepared',prepared,'--execution',execution,'--out',ind]),
        ('evaluate_cost','research197_cost_sections.py',['evaluate','--out',cost,'--acceptance',ind/'native']),
        ('analyze_cost','research197_cost_sections.py',['analyze','--out',cost]),
        ('attach_cards','research197_cards.py',['attach','--out',cards,'--acceptance',ind/'native']),
        ('report','research197_results.py',['--prepared',prepared,'--execution',execution,'--acceptance',ind/'native','--cost',cost,'--out',report])]
    dump(out/'protocol.json',dict(model_calls=0,source_bindings={str(ROOT/'scripts'/s):file_hash(ROOT/'scripts'/s) for _,s,_ in phases},
        phase_order=[name for name,_,_ in phases],execution_outcome_sha256=file_hash(execution/'outcome.json')))
    records=[]
    for name,script,args in phases:
        dump(out/'status.json',dict(status='running',phase=name,completed=records,model_calls=0));print('PHASE',name,flush=True)
        start=time.monotonic();result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*[str(a) for a in args]],cwd=ROOT)
        records.append(dict(phase=name,exit_code=result.returncode,wall_seconds=time.monotonic()-start))
        if result.returncode:
            dump(out/'status.json',dict(status='failed',phase=name,completed=records,model_calls=0,retried=False));raise SystemExit(result.returncode)
    dump(out/'status.json',dict(status='local_phases_completed',completed=records,model_calls=0,plot_and_final_audit_pending=True))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('prepared','execution','out'):p.add_argument('--'+key,required=True,type=Path)
    a=p.parse_args();finish(a.prepared,a.execution,a.out)
