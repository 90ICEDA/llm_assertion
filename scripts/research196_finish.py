"""Local post-model pipeline: register examples/cost cuts, then independent tests.

No network or model transport. Requires the complete 64-version freeze.
Every phase has an immutable output; failures stop without automatic retries.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time
from research194_refinement_runner import ROOT,read,dump,file_hash


def finish(prepared,execution,out):
    prepared,execution,out=(Path(p).resolve() for p in (prepared,execution,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_versions_must_freeze_first')
    out.mkdir(parents=True,exist_ok=False);base=ROOT/'deliverables';cost=base/'research196_cost_sections_20261104_r01'
    cards=base/'research196_case_cards_20261104_r01';ind=base/'research196_independent_20261104_r01'
    report=base/'reguard_mechanisms_20261104_r05'
    phases=[
        ('register_cost','research196_cost_sections.py',['register','--prepared',prepared,'--execution',execution,'--out',cost]),
        ('select_cards','research196_cards.py',['select','--prepared',prepared,'--execution',execution,'--out',cards]),
        ('independent_acceptance','research196_independent.py',['--prepared',prepared,'--execution',execution,'--out',ind]),
        ('evaluate_cost_checkpoints','research196_cost_sections.py',['evaluate','--out',cost,'--acceptance',ind/'native']),
        ('analyze_cost','research196_cost_sections.py',['analyze','--out',cost]),
        ('attach_cards','research196_cards.py',['attach','--out',cards,'--acceptance',ind/'native']),
        ('report','research196_results.py',['--prepared',prepared,'--execution',execution,'--acceptance',ind/'native','--cost',cost,'--out',report])]
    dump(out/'protocol.json',dict(model_calls=0,source_bindings={str(ROOT/'scripts'/script):file_hash(ROOT/'scripts'/script) for _,script,_ in phases},
        phases=[name for name,_,_ in phases],execution_outcome_sha256=file_hash(execution/'outcome.json')))
    results=[]
    for name,script,args in phases:
        dump(out/'status.json',dict(status='running',phase=name,completed=results,model_calls=0))
        print('PHASE',name,flush=True);start=time.monotonic()
        result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts'/script),*[str(a) for a in args]],cwd=ROOT)
        results.append(dict(phase=name,exit_code=result.returncode,wall_seconds=time.monotonic()-start))
        if result.returncode:
            dump(out/'status.json',dict(status='failed',phase=name,completed=results,model_calls=0,retried=False))
            raise SystemExit(result.returncode)
    dump(out/'status.json',dict(status='local_phases_completed',completed=results,model_calls=0,windows_plot_render_pending=True,final_audit_pending=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();finish(a.prepared,a.execution,a.out)
