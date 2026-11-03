"""Run the existing native 2x2 ablation with a logged, clarified shared interface.

No supplied assertion templates, manually edited model outputs or synthetic
model responses. Old runs remain immutable. Unknowns and refusals are retained.
"""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import research15_native_interface as interface
import research15_native_models as models
import research15_native_experiment as experiment
import research15_search_runtime as runtime
import research_fifo_experiment as fifo
from research_native_model import invoke
from research15_evidence import paired_ledger
from research15_acceptance import inspect, sha

ROOT=interface.ROOT
BASE=ROOT/'deliverables/research16_ablation_20261016_r01'
ORIGINAL_CONTEXT=models.context


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def dump(path,obj):interface.dump(Path(path),obj)


def context():
    ctx=ORIGINAL_CONTEXT()
    ctx['sampling_contract']={
        'sample':'All port and reference values are sampled immediately before the SAME posedge NBA updates.',
        'overlapped_implication':'|-> checks the consequent at the antecedent sampling edge.',
        'nonoverlapped_implication':'|=> checks at the NEXT sampling edge; it does not express same-edge equality.',
        'input_identity':'sdata is the currently presented input, not the historical item leaving the FIFO.',
        'output_identity':'mdata is the current output; ref_expected is the oldest outstanding accepted input.',
        'empty_reference':'ref_expected has meaning only while ref_count is positive.',
        'reference_timing':'Use current reference state for current output acceptance; no $past is needed for a same-sample comparison.'}
    ctx['finite_drain_contract']='At drain_due, at least 18 consecutive input-idle output-ready samples have elapsed, for actual RAM capacity <=8 and pipeline<=2. No accepted, noncancelled input may remain outstanding then. This marker is a trusted finite test condition, not a global liveness proof.'
    ctx['output_schema']={'assertions':[{'antecedent':'Boolean expression',
        'consequent':'Boolean expression','timing':'same_sample OR next_sample',
        'obligations':['one named obligation'],'reason':'Explain the event and sampling relation'}]}
    ctx['instructions']='Return JSON only. For EACH assertion choose two Boolean expressions and a timing enum. Do not put implication operators, clocks, reset wrappers, ## sequences, assert or cover into either expression. The generic compiler inserts the chosen temporal operator and reset wrapper. Choose same_sample when both expressions concern the current edge, next_sample only when the consequent is required one cycle later. Expressions may use the permitted port/reference identifiers. Do not add a property field. No empty or constantly false antecedent. No manual trigger field.'
    return ctx


def build_request(ctx):
    return dict(model=models.MODEL,stream=True,format='json',options=models.OPTIONS,
        messages=[dict(role='system',content='Generate structured temporal assertions. Select antecedent, consequent and timing from the supplied specification. Return only the requested JSON schema, not free-form SVA.'),
                  dict(role='user',content=json.dumps(ctx))])


def structured_call(folder,ctx,digest):
    """Generic syntax assembly; every predicate and timing is model-selected."""
    request=build_request(ctx)
    result,content=invoke(request,folder,dump,digest,timeout=900)
    candidate=None
    if result['status']=='response_received':
        try:
            value=json.loads(content)
            dump(folder/'structured_response.json',value)
            assertions=[]
            operators={'same_sample':'|->','next_sample':'|=>'}
            for item in value['assertions']:
                ant,cons=item['antecedent'],item['consequent']
                assert isinstance(ant,str) and isinstance(cons,str)
                assert not any(x in ant+cons for x in ('|->','|=>','##')),'expressions_must_not_include_temporal_operators'
                operator=operators[item['timing']]
                assertions.append(dict(property=f'({ant}) {operator} ({cons})',
                    obligations=item['obligations'],reason=item.get('reason','')))
            candidate=interface.normalize_candidate(dict(assertions=assertions))
            result['candidate_status']='parsed_from_model_selected_expressions_and_timing'
            dump(folder/'assembly.json',dict(mapping=operators,semantic_changes=False,
                rule='Parenthesize model expressions, insert model-selected timing operator, add fixed clock/reset/diagnostic wrappers. No signal substitution or temporal correction.'))
        except Exception as exc:
            candidate=None;result.update(candidate_status='rejected',candidate_error=repr(exc))
    if candidate:
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text(interface.candidate_sva(candidate))
    dump(folder/'result.json',result)
    return result,candidate


def configure(base):
    global BASE
    BASE=base
    interface.OUT=models.OUT=experiment.OUT=BASE
    models.context=context
    models.call=structured_call
    models.OPTIONS=dict(seed=20261016,temperature=0,num_predict=1024,num_ctx=16384,num_gpu=0,num_thread=8)


def prepare():
    BASE.mkdir(parents=True,exist_ok=False)
    experiment.snapshot(BASE/'startup_source_snapshot')
    shutil.copy2(__file__,BASE/'startup_source_snapshot/research16_ablation.py')
    shutil.copy2(runtime.RTL,BASE/'axis_fifo.v')
    dump(BASE/'plan.json',dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        model=models.MODEL,options=models.OPTIONS,max_initial_calls=2,calls_per_arm=1,
        arms=experiment.ARMS,search_budget_per_method_per_seed=6,
        modifications='Structured model-selected antecedent/consequent/timing, assembled by generic syntax rules. Shared human-authored sampling explanation. No candidate assertion supplied or semantically edited. All groups use identical frontend.',
        initial_selection='First actually generated candidate passing no FP/unknown/miss and positive order-payload detection on the common development replay. At most one feedback revision.',
        search='Reuse fixed 4-policy search, 2 configurations, 6 queries each. Only contract tail-loss witness given to B/D; A/C receive only common evidence.',
        independent_test='Fresh secret-generated seeds materialized after all four versions are frozen. Same input grammar; new transactions and depth4/pipeline2. Never refine after viewing test results.',
        scope='One model seed, one engineering fault family on actual FIFO RTL. No historical FIFO bug or global non-regression claim.',
        no_success_guarantee=True))
    print('PREPARED',BASE,flush=True)


def qualify(candidate,folder):
    rows=fifo.stimulus(2026101501)
    for row in rows:row['drain_due']=0
    compiled=runtime.build(candidate,folder/'compiled',2,0)
    if compiled['native']['compile_status']!='passed':
        q=dict(qualified=False,reason='native_compile_failed',native=compiled['native'])
        dump(folder/'qualification.json',q);return q
    fixed=runtime.execute(compiled,folder/'correct',rows,'correct')
    mutant=runtime.execute(compiled,folder/'corrupt',rows,'corrupt')
    ledger=paired_ledger(fixed,mutant,'common:d2:p0:s2026101501')
    dump(folder/'ledger.json',ledger)
    info=inspect(ledger['ledger'])
    q=dict(qualified=not info['unknown'] and not info['false_positives'] and not info['misses'] and bool(info['detections']),
        counts={k:len(info[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')},
        scope='Common finite order-payload qualification, not all obligations',
        feedback=experiment.feedback(ledger,candidate,False),
        legal_failure_samples=[t for t in fixed['trace'] if any('cycle='+str(t['cycle'])==f['detail'] for f in fixed['native']['failures'])][:3])
    dump(folder/'qualification.json',q)
    return q


def initial():
    if (BASE/'model_calls').exists():raise FileExistsError('Do not rerun model attempts in an existing run')
    digest=models.service();previous=None;qualification=None
    for attempt in range(2):
        ctx=context()
        ctx['task']='Generate exactly one order_payload assertion. Whenever an OUTPUT handshake occurs with an outstanding accepted input, compare the full output payload against the oldest queued input AT THAT SAME SAMPLE. Do not impose next-cycle timing, do not compare input pins against the reference, do not use previous values. Choose the implication according to the supplied sampling contract. Protect this obligation only; other obligations will be evaluated separately.'
        if qualification is not None:
            ctx.update(current_assertions=previous,actual_native_feedback=qualification,
                revision_task='Correct the rejected assertion using this actual development feedback; return the complete replacement JSON.')
        call,candidate=models.call(BASE/'model_calls'/f'initial_{attempt}',ctx,digest)
        if candidate is None:
            qualification=dict(qualified=False,reason='model_or_interface_rejection',call=call)
        else:qualification=qualify(candidate,BASE/'initial_qualification'/f'v{attempt}')
        dump(BASE/'initial_qualification'/f'v{attempt}'/'decision.json',qualification)
        print('INITIAL',attempt,qualification.get('counts'),qualification['qualified'],flush=True)
        if qualification['qualified']:
            dump(BASE/'shared_initial.json',candidate)
            dump(BASE/'shared_initial_freeze.json',dict(candidate_sha256=sha(candidate),source=f'model_calls/initial_{attempt}',
                model_calls=attempt+1,no_manual_candidate_edit=True,scope='Common finite qualification only'))
            return
        previous=candidate
    dump(BASE/'initial_failure.json',qualification)


def search():
    assert (BASE/'shared_initial.json').exists(),'No qualified initial; preserve failure'
    subprocess.run([sys.executable,str(ROOT/'scripts/research15_search_experiment.py'),
        '--candidate',str(BASE/'shared_initial.json'),'--out',str(BASE/'search'),'--budget','6'],check=True)


def baseline():
    experiment.baseline()
    p=read(BASE/'protocol.json')
    p['holdout']=None
    p['holdout_policy']='New random seeds generated only after all arms freeze; no model calls after test results.'
    p['initial_actual_model_calls']=read(BASE/'shared_initial_freeze.json')['model_calls']
    dump(BASE/'protocol.json',p)


def arms():
    witness=BASE/'search/treatment_witness.json'
    assert read(witness),'Search did not find a qualified treatment witness; no synthetic substitute'
    experiment.arms(witness)


def holdout():
    assert (BASE/'all_arms_freeze.json').exists(),'All arms must be frozen'
    assert not (BASE/'holdout').exists(),'Independent tests cannot be regenerated after viewing results'
    p=read(BASE/'protocol.json')
    assert p['holdout'] is None,'Holdout seeds already materialized'
    p['holdout']=[dict(seed=secrets.randbelow(2**31),family=f) for f in ('random','tail_loss','reset_pending')]
    p['holdout_created_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    p['all_arms_freeze_file_sha256']=hashlib.sha256((BASE/'all_arms_freeze.json').read_bytes()).hexdigest()
    dump(BASE/'protocol.json',p)
    experiment.holdout()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','initial','search','baseline','arms','holdout'])
    p.add_argument('--run',default=BASE.name);args=p.parse_args()
    if Path(args.run).name!=args.run:raise ValueError('run must be one directory name')
    configure(ROOT/'deliverables'/args.run)
    globals()[args.action]()
