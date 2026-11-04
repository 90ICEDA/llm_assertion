"""Pay twelve first-query executions locally; no model/held-out access."""
import argparse
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research199_search import session
import research197_cases as cases

def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    old=ROOT/'deliverables/research197_refinement_prepare_20261104_r01/protocol.json';p=read(old)
    rows=[]
    for cid in cases.IDS:
        baseline=read(p['baselines'][cid])
        for seed in p['seeds']:
            for strategy in ('S0','S3'):
                folder=out/cid/str(seed)/strategy
                s=session(cid,strategy,seed,folder,baseline=baseline['measurement'],queries=baseline['queries'],cost_model=p['cost_models'][cid])
                a=s.acquire(cases.get_case(cid)['initial'],round=0)
                if a is None:raise ValueError('initial_query_budget_stop')
                rows.append(dict(case_id=cid,seed=seed,search=strategy,path=str(folder/'query00/acquisition.json'),
                    sha256=file_hash(folder/'query00/acquisition.json'),baseline=p['baselines'][cid]))
                dump(out/'progress.json',rows);print('FIRST_QUERY',cid,seed,strategy,len(a['new_gap_ids']),flush=True)
    dump(out/'outcome.json',dict(status='complete',model_calls=0,heldout_access=False,entries=rows,
        cost_models=p['cost_models'],source_protocol=str(old),source_protocol_sha256=file_hash(old),
        native_compile_attempts=sum(read(r['path'])['cost']['native_compile_attempts'] for r in rows)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);run(p.parse_args().out)
