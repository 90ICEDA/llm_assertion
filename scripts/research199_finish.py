"""Finish only after all paid trajectories freeze; no model calls."""
import argparse
from pathlib import Path
import time
from research194_refinement_runner import read,dump,file_hash
from research199_prepare import verify
import research199_cost as cost
import research199_independent as independent
import research199_linkage as linkage
import research199_results as results

def run(prepared,execution,out):
    p=verify(prepared);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    if read(Path(execution)/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('freeze_first')
    bindings={str(Path(m.__file__).resolve()):file_hash(m.__file__) for m in (cost,independent,linkage,results)}
    dump(out/'protocol.json',dict(model_calls=0,source_bindings=bindings,prepared=str(prepared),execution=str(execution)))
    steps=[('cost_registration',lambda:cost.register(prepared,execution,out/'cost')),
        ('independent',lambda:independent.run(prepared,execution,out/'acceptance')),
        ('cost_evaluation',lambda:cost.runtime().evaluate(out/'cost',out/'acceptance/native')),
        ('cost_analysis',lambda:cost.analyze(out/'cost')),
        ('linkage',lambda:linkage.run(prepared,execution,out/'cost',out/'linkage.json')),
        ('report',lambda:results.run(prepared,execution,out/'acceptance/native',out/'cost',out/'linkage.json',out/'report'))]
    done=[]
    for name,fn in steps:
        start=time.monotonic();fn();done.append(dict(phase=name,seconds=time.monotonic()-start));dump(out/'progress.json',done);print('DONE',name,flush=True)
    verify(prepared)
    dump(out/'outcome.json',dict(status='execution_and_analysis_complete_requires_delivery_audit',model_calls=0,phases=done))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','execution','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.execution,a.out)
