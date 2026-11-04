"""Replay a real archived edit, then physically search the changed candidate."""
import argparse
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,merge_measurements,query_union,file_hash
from research199_execution_core import configured
from research199_refinement import runtime
from research199_search import session
from research199_independent import FAULTS,mutate
import research197_cases as cases

def run(acquisition,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    cid=cases.IDS[0];seed=19711
    old=read(ROOT/'deliverables/research197_refinement_prepare_20261104_r01/protocol.json')
    b=read(old['baselines'][cid]);firstpath=Path(acquisition)/cid/str(seed)/'S3/query00/acquisition.json';first=read(firstpath)
    current=merge_measurements(cases.get_case(cid)['initial'],[b['measurement'],first['measurement']]);queries=query_union(b['queries'],first['queries'])
    adapter=cases.CaseAdapter(cid);core,runner=runtime('A3')
    prep=runner.prepare_first(adapter,'R3',seed,b['measurement'],queries,first,out/'prepared',max_rounds=2,current_measurement=current)
    state=read(prep['state']);core,runner,cache=configured('A3',state,adapter)
    archive=ROOT/'deliverables/research198_refinement_execute_20261104_r01'/cid/str(seed)/'S3_local_first/refinement/round01/model_edit.json'
    class Replay:
        provenance='archived_response_replay_qualification_not_new_model'
        def __init__(self):self.calls=0
        def __call__(self,request,folder):
            self.calls+=1
            if self.calls==1:return dict(status='archived_response_replay',model_calls=0,prompt_tokens=0,completion_tokens=0),read(archive)
            return dict(status='qualification_stop_after_second_acquisition',model_calls=0,prompt_tokens=0,completion_tokens=0),None
    s=session(cid,'S3',seed,out/'acquisition',baseline=b['measurement'],queries=b['queries'],cost_model=old['cost_models'][cid])
    outcome=runner.run_trajectory(adapter,'R3',seed,out/'trajectory',b['measurement'],b['queries'],s,Replay(),max_rounds=2,prepared=Path(prep['state']).parent)
    acquisitions=read(out/'trajectory/acquisitions.json');rounds=read(out/'trajectory/rounds.json')
    if len(acquisitions)!=2 or rounds[0]['status']!='accepted':raise ValueError('accepted_change_and_fresh_query_required')
    changed=read(out/'trajectory/round01/proposal.json');second=acquisitions[1]
    if second['candidate_sha256']!=core.digest(changed) or second['candidate_sha256']==core.digest(state['initial']):raise ValueError('not_current_candidate_acquisition')
    if not second['measurement']['native_complete'] or not second['measurement']['reference_complete']:raise ValueError('native_unknown_qualification')
    if second['cost']['native_execution_attempts']!=2:raise ValueError('second_acquisition_not_physically_executed')
    # Static reserved-site check only. No independent stimuli or grades exist.
    sites={}
    for case in cases.IDS:
        paths=cases.sources(case,out/'static_reserved_sites'/case,'correct');text=paths[0].read_text();modified=mutate(text,FAULTS[case])
        if text==modified:raise ValueError('mutation_noop')
        sites[case]=dict(original_sha256=file_hash(paths[0]),site_count=text.count(FAULTS[case]['search']),compiled=False,independent_executed=False)
    result=dict(status='qualified',model_calls=0,new_model_results=False,heldout_execution=False,
        first_query_reused=True,changed_candidate_sha256=core.digest(changed),second_query=second['query']['id'],
        second_query_native_jobs=2,query_changed=second['query']['id']!=first['query']['id'],
        archived_response_source=str(archive),archived_response_sha256=file_hash(archive),first_acquisition_source=str(firstpath),first_acquisition_sha256=file_hash(firstpath),
        native_cost=read(out/'trajectory/cost_components.json'),static_reserved_sites=sites,
        interpretation='Native online integration qualification after an accepted archived edit. The second model boundary is intentionally stopped; not a real model fallback trajectory or generalization result.')
    dump(out/'outcome.json',result);print({k:v for k,v in result.items() if k not in ('native_cost','static_reserved_sites')},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--acquisition',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.acquisition,a.out)
