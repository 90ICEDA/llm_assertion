"""Native SVA S0-S3 development replication on the complex FIFO runtime.

Unchanged S0 ordinary, S1 candidate disagreement, S2 contract_novelty from
research65; S3 optional active temporal acquisition. No model calls or holdouts.
"""
import argparse
import csv
from pathlib import Path
import shutil
import time

import research64_search_value as b
import research65_search_policy as policies
import research_active_temporal as active

ROOT = b.ROOT
METHODS = dict(S0='ordinary', S1='candidate_disagreement', S2='contract_novelty', S3='active_temporal')
SEEDS = (19307, 19319, 19331)
BUDGET = 4
NAMES = ('bounded', 'valid')


def descriptions(candidates):
    return [dict(property='\n'.join(a['property'] for a in c['assertions'])) for c in candidates.values()]


def options():
    dimensions = dict(overlap=['trigger','response','transaction'], reset_pending=['exception','transaction'],
                      tail_loss=['window','vacuity'], drain=['window','response'],
                      backpressure=['trigger','response','window','exception'], random=['trigger','vacuity'])
    return [dict(id=f'{f}:{d}', family=f, duration=d, dimensions=dimensions[f], obligations=list(policies.TARGETS[f]),
                 estimated_cost=16, constraints=['source_valid_persistence','accepted_transaction_alignment','reset_epoch_cancellation'],
                 boundary=d) for f,d in policies.ACTIONS]


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    for name in NAMES:
        target=out/'candidates'/(name+'.json');target.parent.mkdir(exist_ok=True)
        shutil.copy2(b.SOURCES[name],target)
    shutil.copy2(b.extension.runtime.RTL,out/'axis_fifo.v')
    b.dump(out/'protocol.json',dict(methods=METHODS,seeds=SEEDS,budget=BUDGET,parent='axis_fifo',depth=4,pipeline=1,
        candidates={n:str(b.SOURCES[n].relative_to(ROOT)) for n in NAMES},modes=b.MODES,
        same_candidate_and_budget=True,native_executions_per_query=16,expected_search_queries=48,
        shared_public_queries=[dict(family='overlap',duration=None),dict(family='backpressure',duration=1)],
        accounting='All submitted queries including unknown and duplicate consume 16 native executions; two builds/smokes and two common public queries separate; no free simulator/solver during selection',
        selection='Unchanged legacy S0-S2 selectors; S3 structural candidate dimensions, confirmed protection deficit, confirmed-gap novelty and measured native-execution cost; weights2/2/1 fixed before execution',
        protection='Causal independent-obligation detections only; observed violations never credited as protection. Known gaps retained for refinement.',
        constraints='Same existing source handshake scheduler and independent accepted-transaction queue monitor. Candidate predictions never decide legality.',
        oracle='research64 query + research15 paired ledger; legal control, same accepted inputs, independent first target violation, native miss and confirmed attribution all required; unknown excluded from discovery',
        dedup='parent/candidate_content/FN_or_FP/obligation/mechanism; duration variants collapsed; public gaps subtracted; seeds/cycles not independent bugs',
        independence='Development replication of known artificial faults, not unseen-fault acceptance or historical bug generalization',
        failure_policy='Stop on infrastructure exception; retain partial raw artifacts, no hidden retries or seed/budget changes',
        native_sva=True,model_calls=0,tokens=0,formal_calls=0,prepared_at=time.time()))
    files=list((ROOT/'scripts').glob('research*.py'))
    (out/'source_snapshot').mkdir()
    for p in files:shutil.copy2(p,out/'source_snapshot'/p.name)
    b.dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():b.digest(p) for p in files})
    b.dump(out/'sealed.json',{p.relative_to(out).as_posix():b.digest(p) for p in out.rglob('*') if p.is_file()})
    b.dump(out/'outcome.json',dict(status='prepared'))


def run(out):
    b.verify(out)
    assert b.read(out/'outcome.json')['status']=='prepared'
    candidates={n:b.read(out/'candidates'/(n+'.json')) for n in NAMES}
    records=[];calls=[];public=[];begin=time.perf_counter()
    b.dump(out/'outcome.json',dict(status='running'))
    try:
        with b.extension.installed():
            builds={n:b.loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
            b.dump(out/'builds.json',builds)
            assert all(builds[n]['native']['compile_status']=='passed' for n in NAMES), 'native_build_failed'
            def query(path, context):
                return b.query(path,builds,candidates,NAMES,b.schedule(context['stimulus_seed'],context['family'],context['duration']),context,calls)
            for i,(family,duration) in enumerate((('overlap',None),('backpressure',1))):
                public.append(query(out/'public'/f'q{i}',dict(pair='bounded__valid',stage='public',method='common',seed=0,
                    query=i,family=family,duration=duration,stimulus_seed=19300+i)))
            b.dump(out/'public_feedback.json',public)
            qualified=all(r['healthy'] and all(r['correct_accepts'].values()) for r in public)
            b.dump(out/'qualification.json',dict(qualified=qualified,reason='common legal native controls',full_parent_pass=False))
            assert qualified, 'public_qualification_failed_no_search_credit'
            public_keys={k for r in public for k in r['gap_keys']}
            for si,seed in enumerate(SEEDS):
                order=list(METHODS);order=order[si:]+order[:si]
                for method in order:
                    policy=policies.factory(METHODS[method],seed) if method!='S3' else active.ActiveSelector(descriptions(candidates),list(b.grammar.OBLIGATIONS))
                    history=[];seen=set(public_keys)
                    def observe(result):
                        if method=='S3':
                            policy.observe(f"{result['family']}:{result['duration']}", 'confirmed' if result['healthy'] else 'unknown',
                                list(result['fixed_obligation_checks']),result['gap_keys'],result['native_executions'],
                                [o for o,n in result['causal_protected'].items() if n>0])
                        else:history.append(policies.update(policy,METHODS[method],result['family'],result))
                    for r in public:observe(r)
                    for q in range(BUDGET):
                        path=out/'queries'/f's{seed}'/method/f'q{q}'
                        start=time.perf_counter()
                        decision=policy.select(options()) if method=='S3' else policies.decision(policy,METHODS[method],seed,q,history)
                        chosen=decision['chosen'] if method=='S3' else decision
                        elapsed=time.perf_counter()-start
                        b.dump(path/'selection.json',dict(decision=decision,permitted_history=history))
                        r=query(path,dict(pair='bounded__valid',stage='search',method=method,seed=seed,query=q,
                            family=chosen['family'],duration=chosen['duration'],stimulus_seed=seed*100+q))
                        r.update(first_new_keys=sorted(set(r['gap_keys'])-seen),
                                 public_unexposed_keys=sorted(set(r['gap_keys'])-public_keys),selector_seconds=elapsed)
                        seen.update(r['gap_keys']);observe(r)
                        b.dump(path/'result.json',r);records.append(r)
                        b.dump(out/'records.json',records);b.dump(out/'reference_costs.json',calls)
                        print('QUERY193',seed,method,q,r['family'],r['duration'],len(r['first_new_keys']),flush=True)
        b.dump(out/'outcome.json',dict(status='completed',queries=len(records),native_sva=True,model_calls=0,tokens=0,wall_seconds=time.perf_counter()-begin))
    except BaseException as exc:
        b.dump(out/'outcome.json',dict(status='interrupted',error=repr(exc),queries=len(records),model_calls=0))
        raise
    finally:
        b.dump(out/'records.json',records);b.dump(out/'reference_costs.json',calls)
    report(out)


def report(out):
    rr=b.read(out/'records.json');totals=[];curves=[];paired=[]
    sets={m:{k for r in rr if r['method']==m for k in r['public_unexposed_keys']} for m in METHODS}
    for m in METHODS:
        rows=[r for r in rr if r['method']==m]
        totals.append(dict(method=m,queries=len(rows),confirmed_gaps=len(sets[m]),gap_keys=sorted(sets[m]),
            exclusive_gaps=len(sets[m]-set().union(*(v for k,v in sets.items() if k!=m))),
            unknown=sum(r['unknown'] for r in rows),later_attribution_unknown=sum(r['later_attribution_unknown'] for r in rows),
            native_executions=sum(r['native_executions'] for r in rows),
            query_wall_seconds=sum(r['query_wall_seconds'] for r in rows),
            selector_seconds=sum(r['selector_seconds'] for r in rows),model_calls=0,tokens=0))
        for q in range(BUDGET):
            prefix=[r for r in rows if r['query']<=q]
            curves.append(dict(method=m,queries_per_seed=q+1,actual_queries=len(prefix),
                actual_native_executions=sum(r['native_executions'] for r in prefix),
                confirmed_gaps=len({k for r in prefix for k in r['public_unexposed_keys']})))
    for seed in SEEDS:
        ss={m:{k for r in rr if r['method']==m and r['seed']==seed for k in r['public_unexposed_keys']} for m in METHODS}
        for m in ('S0','S1','S2'):
            paired.append(dict(seed=seed,comparator=m,S3_only=sorted(ss['S3']-ss[m]),comparator_only=sorted(ss[m]-ss['S3'])))
    for name,value in [('method_totals',totals),('cost_curve',curves),('paired_gain',paired)]:b.dump(out/(name+'.json'),value)
    with (out/'cost_curve.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(curves[0]));writer.writeheader();writer.writerows(curves)
    b.dump(out/'cost.json',b.native_cost(out))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(7,4))
        for m in METHODS:
            rs=[r for r in curves if r['method']==m]
            ax.step([r['actual_native_executions'] for r in rs],[r['confirmed_gaps'] for r in rs],where='post',label=m)
        ax.set(xlabel='Actual native executions (3 paired seeds)',ylabel='Distinct public-unexposed candidate gaps',title='Complex FIFO native SVA search, one parent')
        ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(out/'cost_curve.png',dpi=180);plt.close(fig)
    except ImportError:b.dump(out/'plot_status.json',dict(status='matplotlib_unavailable'))
    lines=['# S0–S3 native FIFO development comparison','',
        'Same two archived model-generated candidates, 3 paired seeds and 4 queries/strategy/seed; 16 fresh native runs/query. Two common public queries are excluded from discovery credit. No model calls or holdout data.', '',
        '|Strategy|Queries|New confirmed gaps|Exclusive gaps|Native executions|Critical unknown|', '|---|---:|---:|---:|---:|---:|']
    for r in totals:lines.append(f"|{r['method']}|{r['queries']}|{r['confirmed_gaps']}|{r['exclusive_gaps']}|{r['native_executions']}|{r['unknown']}|")
    lines.extend(['','All faults are existing artificial variants. Candidate/obligation/mechanism gaps are not independent bugs. Search evidence alone does not establish SVA improvement or unseen-fault generalization.','',
        'Full paired positive and negative differences, selection rankings, original candidate bytes, independent transaction ledgers, native triggers/failures and actual execution logs are retained. Selection is structural prediction, with independent judgement only after execution.'])
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('SUMMARY193',[(r['method'],r['confirmed_gaps']) for r in totals],flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','run','report'))
    ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    globals()[a.action](a.out.resolve())
