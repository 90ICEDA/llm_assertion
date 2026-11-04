"""Native typed-operation and three-stage controller probes; handwritten only."""
import argparse
import copy
from pathlib import Path
import research197_cases as cases
from research197_refinement import runtime
from research194_refinement_runner import read,dump,ROOT,bind_measurement,model_evidence

def run(qualification,out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False);rows=[]
    for cid,edit in [
        (cases.IDS[1],dict(op='match_transaction_window',assertion='matching',field='consequent',request='inp_req && inp_gnt',request_id='inp_id',request_data='inp_data',response_id='out_id',response_data='out_data',cancel='!rst_n || clear',min_cycles=1,max_cycles=8)),
        (cases.IDS[2],dict(op='set_delay',assertion='capture',field='antecedent',expression=cases.delta.EVENT,cycles=1))]:
        core,runner=runtime('T');a=cases.CaseAdapter(cid);baseline=read(Path(qualification)/cid/'candidate0.json')
        ctl=runner.controller_from(a,'R3',baseline,1);response=dict(edits=[edit],reason='Handwritten operator qualification; never a model result.')
        proposal,record=ctl.parse(response,model_evidence(baseline),a.validate)
        measured=a.evaluate(proposal,out/cid/'native',cases.query_pool(cid)[:2])
        verdict=ctl.observe(proposal,measured,edit_record=record,baseline=baseline)
        rows.append(dict(case_id=cid,edit=edit,result=verdict));dump(out/'typed_operations.json',rows)
        print('TYPED',cid,verdict['decision']['accepted'],flush=True)
    cid=cases.IDS[0];core,runner=runtime();a=cases.CaseAdapter(cid);baseline=read(Path(qualification)/cid/'candidate0.json')
    ctl=runner.controller_from(a,'R3',baseline,3);stages=[]
    responses=[dict(edits=[dict(op='set_response_window',assertion='window',field='consequent',response='out_valid',min_cycles=2,max_cycles=21,anchor_cycles=21)],reason='Known weak local probe: intentionally does not repair the historical early-valid defect.'),
      dict(edits=[dict(op='add_assertion',assertion=cases.prop('weak_latency','launch','!out_valid','exact_latency','next_sample'))],reason='Known weak composition probe: only checks one early sample; must not count as progress.'),
      dict(assertions=[*a.case['candidate_pool'][1],cases.prop('no_early',' || '.join(cases.past('launch',n) for n in range(1,18)),'!out_valid','exact_latency')],reason='Handwritten regeneration qualification, not a model-generated repair.')]
    for index,response in enumerate(responses):
        stage=ctl.stage;proposal,record=ctl.parse(response,model_evidence(baseline),a.validate)
        measured=a.evaluate(proposal,out/'fallback'/f'round{index+1}'/'native',cases.query_pool(cid)[:2])
        verdict=ctl.observe(proposal,measured,edit_record=record,baseline=baseline)
        stages.append(dict(stage=stage,response=response,decision=verdict['decision'],next_stage=ctl.stage))
        dump(out/'fallback.json',stages);print('FALLBACK',stage,verdict['decision']['accepted'],ctl.stage,flush=True)
    passed=[r['stage'] for r in stages]==['local','compose','regenerate'] and not stages[0]['decision']['accepted'] and not stages[1]['decision']['accepted'] and stages[2]['decision']['accepted']
    dump(out/'outcome.json',dict(status='qualified' if passed and all(r['result']['decision']['accepted'] for r in rows) else 'failed',model_calls=0,
      actual_native_fallback_stages=[r['stage'] for r in stages],interpretation='Handwritten proposals verify typed operators and measured fallback receipts. Actual model choices and branch coverage must be reported separately after new authorization.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--qualification',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.qualification,a.out)
