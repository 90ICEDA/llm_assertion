"""Small independent executor regressions and concrete minimal source defects."""
import argparse
import copy
from pathlib import Path
import obligation_isolated_search as iso
from obligation_isolated_search import x


def main(run):
    x.OUT=x.ROOT/'deliverables'/run;iso.configure()
    folder=x.OUT/'supplemental_qa';folder.mkdir(exist_ok=False)
    qualify=x.qualify;qualify.OUT=folder
    rows=[dict(rst=r,x=a,b=b) for r,a,b in [(0,0,0),(0,0,0),(1,2,0),(1,4,0),(1,8,1),(1,0,1),(1,0,0),(1,6,0),(0,0,0),(1,0,0),(1,0,0)]]
    candidates=[dict(antecedent='x',consequent='b',delay=2)]
    p,actual=qualify.simulate('multibit_boolean_delay_overlap_reset','reg [3:0] x; reg b;',rows,candidates)
    # Delayed truth of 2,4,8 => due at 4,5,6, with only 6 failing.
    # The 6 at cycle 7 is cancelled by reset at cycle 8.
    expected=[dict(cycle=i,trigger=int(rows[i]['x']!=0),fail=int(i==6)) for i in (2,3,4,5,6,7,9,10)]
    x.dump(p/'expected.json',expected);x.dump(p/'actual.json',actual)
    assert actual[0]==expected
    # Batch poisoning reproduced, followed by the SAME candidate texts through
    # strict isolation; errors remain unknown, not semantic failures.
    d=x.read(x.OUT/'frozen/filter/definition.json');cs=x.read(x.OUT/'frozen/filter/candidates.json')['candidates']
    inputs=x.policy.ordinary(d,3113)
    raw=x.engine.execute_run(d,inputs,cs,'supplemental_qa/filter_original_batch','correct')
    assert raw['status']=='unsupported_syntax'
    isolated=iso.evaluate(d,inputs,cs,'supplemental_qa/filter_isolated')
    assert isolated['status']=='partial_candidate_unknown' and len(isolated['unsupported_candidates'])==2
    assert all(r['candidate_ids']==['pool_filter_1'] for r in isolated['runs'])
    x.dump(folder/'filter_isolation.json',dict(original=raw['run_id'],isolated=isolated,candidate_texts_identical=True))
    # Minimal two-overlapping-transaction RTL witness. Not a model candidate.
    d=x.read(x.OUT/'frozen/stat/definition.json');pool=x.read(x.OUT/'frozen/stat/candidates.json')['candidates']
    rs=[]
    for i,(reset,done,length) in enumerate([(0,0,0),(0,0,0),(1,1,19),(1,1,73),(1,0,0)]):
        rs.append(dict(cycle=i,stimulus_id=f'stat_min:{i}',rst_ni=reset,frame_done_i=done,frame_len_i=length))
    q=iso.evaluate(d,rs,pool,'supplemental_qa/stat_overlap_minimal')
    correct=next(r for r in q['runs'] if r['variant']=='correct')
    oracle=x.read(x.ROOT/correct['run']/'independent_reference.json')
    failed=[c for e in oracle['events'] for c in e['checks'] if not c['passed']]
    assert len(failed)==1 and failed[0]['obligation']=='captured_length' and failed[0]['expected']==19 and failed[0]['actual']==73
    x.dump(folder/'stat_overlap_minimal.json',dict(query=q,confirmed=failed,
        minimum_scope='two reset samples plus two overlapping events and first due observation; no claim of globally shortest reset protocol',
        pending_later_transaction=True,conclusion='first transaction already violates deadline payload; later pending transaction is not counted as passed'))
    x.dump(folder/'summary.json',dict(passed=True,multibit_truth_delay2_overlap_reset=True,batch_poisoning_reproduced=True,
        isolation_preserves_unknowns=True,stat_fixed_RTL_captured_payload_defect=True,
        cost_scope='shared executor/reference qualification; excluded from search arms and model context',
        native_sva=False))
    print('supplemental_qa passed')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
