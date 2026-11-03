"""New independent batch after research132's reset-control exposure failure.

Only the reset_cancels_tail input recipe changes. Assertions, RTL, oracle,
acceptance checks and other generators remain byte-for-byte inherited.
research132 results stay failed and its ENTIRE batch is excluded as development.
"""
import argparse
from pathlib import Path
import time
import research132_fifo_independent as r

ROOT,read,dump,rel,digest=r.ROOT,r.read,r.dump,r.rel,r.digest
PREVIOUS=ROOT/'deliverables/research132_prepare_20261026_r01'
OLD_INPUTS=ROOT/'deliverables/research132_inputs_20261026_r01'
OLD_RUN=ROOT/'deliverables/research132_independent_20261026_r01'
ORIGINAL_SCHEDULE=r.schedule


def schedule(rng,family):
    rows=ORIGINAL_SCHEDULE(rng,family)
    if family!='reset_cancels_tail':return rows
    original_intents=[t['cycle'] for t in rows if t['intent']]
    fourth=original_intents[-1]
    fifth=fourth+rng.randint(14,18)
    reset_at=fourth+rng.randint(33,40)
    reset_width=rng.randint(2,4)
    fair=rng.randint(24,40)
    initial_reset=[]
    for t in rows:
        if not t['rst']:break
        initial_reset.append(t['cycle'])
    resets=set(initial_reset)|set(range(reset_at,reset_at+reset_width))
    # First four raw outputs can complete. Correct side then accepts a fifth
    # transaction under parked output ready; both sides really cancel pending
    # accepted work on reset. The faulty side also cancels its hidden fourth.
    intents=set(original_intents+[fifth]);low=set(range(fourth+10,reset_at+reset_width))
    length=reset_at+reset_width+fair+2
    values=rng.sample(range(1,2**32),length)
    return [dict(cycle=c,rst=int(c in resets),intent=int(c in intents),ready=int(c not in low),
        data=values[c],drain_due=int(c==length-1)) for c in range(length)]


def seal(out):
    r.check_inputs(PREVIOUS,OLD_INPUTS)
    prior=read(OLD_RUN/'outcome.json')
    assert prior['completed'] and prior['failed']==8 and not prior['all_scoped_checks_passed']
    results=read(OLD_RUN/'progress.json')
    bad=[x for x in results if not x['passed']]
    assert all(x['task_id']=='reset_cancels_tail' and x['reasons']==['actual_reset_cancellation'] for x in bad)
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'candidate.json',read(PREVIOUS/'candidate.json'))
    protocol=read(PREVIOUS/'protocol.json')
    protocol['campaign']='research133'
    protocol['generator_correction']='reset_cancels_tail: add a fifth accepted transaction under output backpressure before reset, so BOTH correct and drop traces really cancel pending work. Same exposure criterion, never relaxed.'
    protocol['previous_batch_status']='research132 remains 120/128; eight controls lacked correct-side cancellation. Entire128-input batch promoted to development before this new freeze.'
    protocol['route_stop']='One new complete batch only. Any remaining failure is reported; no automatic further recipe repair or rerun.'
    dump(out/'protocol.json',protocol)
    old_cases=read(OLD_INPUTS/'cases.json')
    ex=read(PREVIOUS/'exclusions.json')
    ex['input_hashes']=sorted(set(ex['input_hashes'])|{r.sha(c['rows']) for c in old_cases})
    ex['timing_hashes']=sorted(set(ex['timing_hashes'])|{r.timing_hash(c['rows']) for c in old_cases})
    ex['sources'].append(dict(path=rel(OLD_INPUTS/'cases.json'),sha256=digest(OLD_INPUTS/'cases.json'),input_count=128))
    dump(out/'exclusions.json',ex)
    dump(out/'development_promotion.json',dict(entire_batch=rel(OLD_INPUTS),cases=128,
        input_hashes=[r.sha(c['rows']) for c in old_cases],reason='Used to repair test-generator applicability, no assertion edits.',
        old_outcome_sha256=digest(OLD_RUN/'outcome.json'),original_failure_retained=True))
    paths=list((ROOT/'scripts').glob('*.py'))+[r.FROZEN,r.base.extension.runtime.RTL,
        PREVIOUS/'sealed.json',OLD_INPUTS/'sealed.json',OLD_INPUTS/'cases.json',OLD_RUN/'outcome.json',OLD_RUN/'progress.json']
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in paths})
    dump(out/'tools.json',read(PREVIOUS/'tools.json'))
    dump(out/'freeze.json',dict(created_unix=time.time(),candidate_sha256=r.EXPECTED,
        candidate_file_sha256=digest(r.FROZEN),protocol_sha256=digest(out/'protocol.json'),
        inputs_generated=False,model_calls=0,acceptance_unchanged=True))
    dump(out/'sealed.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    r.verify(out)
    print('SEALED133; assertion/RTL/oracle/acceptance unchanged; all132 inputs excluded',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('seal','generate','run','audit','verify'))
    for name in ('prepared','inputs','out','run'):ap.add_argument('--'+name,type=Path)
    a=ap.parse_args()
    for name in ('prepared','inputs','out','run'):
        if getattr(a,name):setattr(a,name,getattr(a,name).resolve())
    r.schedule=schedule
    if a.action=='seal':seal(a.out)
    elif a.action=='generate':r.generate(a.prepared,a.out)
    elif a.action=='run':
        r.run(a.prepared,a.inputs,a.out)
        path=a.out/'SUMMARY.md'
        path.write_text(path.read_text(encoding='utf-8').replace('# research132 ', '# research133 ',1)+
            '\nresearch132原批次保留120/128与8个控制曝光失败；整批转开发。此次仅修正复位取消控制的激励，接受条件未放宽，128个输入全部重新生成。内部ind132 ID前缀来自复用执行器，不表示重用旧输入；新种子和输入哈希见split.json。\n',encoding='utf-8')
    elif a.action=='audit':r.audit(a.prepared,a.inputs,a.run,a.out)
    else:r.verify(a.prepared);print('SEALED133 VERIFIED')
