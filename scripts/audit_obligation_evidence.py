"""Supplemental evidence verification; never writes into historical experiments."""
import argparse
import collections
import copy
import itertools
import json
from pathlib import Path
import re
import shutil
import time
import run_obligation_evidence as x
from obligation_evidence_monitor import monitor, evidence, check_inputs


def oracle_tests():
    """Literal expected answers on constructed port traces, separate QA cohort."""
    results=[]
    def run(k, rows, expected):
        d=x.definition(k)
        tr=[]
        for i,z in enumerate(rows):
            tr.append({**{n:0 for n in {**d['inputs'],**d['outputs']}},d['rst']:1,**z,'cycle':i})
        o=monitor(d,tr)
        actual=[(e['cycle'],c['obligation']) for e in o['events'] for c in e['checks'] if not c['passed'] and not c['conditional']]
        results.append(dict(case=k,passed=actual==expected,actual=actual,expected=expected,trace=tr,oracle=o))
        assert actual==expected,(k,actual,expected)
        return tr,o
    run('onehot',[{'rst_n':0},{'oh_i':2,'err_o':0},{'oh_i':6,'err_o':0},{'oh_i':9,'err_o':1}],[(2,'multihot_detect')])
    run('fifo',[{'rst_ni':0},{'push_i':0,'empty_o':1},{'push_i':1,'pop_i':0,'empty_o':0},{'push_i':1,'pop_i':1,'empty_o':1}],[(3,'nonempty_when_present')])
    tr,o=run('stat',[{'rst_ni':0},{'frame_done_i':1,'frame_len_i':19},{'frame_done_i':1,'frame_len_i':73},
        {'stat_valid_o':1,'stat_len_o':19},{'stat_valid_o':1,'stat_len_o':73},
        {'frame_done_i':1,'frame_len_i':99},{'rst_ni':0},{},{}],[])
    bad=copy.deepcopy(tr);bad[3]['stat_len_o']=73
    run('stat',bad,[(3,'captured_length')])
    early=copy.deepcopy(tr);early[2]['stat_valid_o']=1
    tr2,o2=run('stat',early,[(2,'valid_latency')])
    checks=[dict(cycle=r['cycle'],trigger=1,fail=int(r['cycle']==4)) for r in tr2 if r['rst_ni']]
    es=evidence(x.definition('stat'),tr2,checks,o2)
    assert not any(e['kind']=='false_positive' and e['cycle']==4 for e in es),'nonlegal prefix must not become FP'
    run('spill',[{'rst_ni':0},{'flush_i':1,'push_i':1,'data_i':0},{'valid_o':0,'data_o':0},
        {'flush_i':1,'push_i':1,'data_i':7},{'rst_ni':0},{'valid_o':0}],[])
    # Two samples after polarity flip do not qualify threshold two; third updates
    # the stored value for the NEXT pre-NBA observation.
    run('filter',[{'rst_n':0},{'enable_i':1,'filter_i':1,'thresh_i':2},
        {'enable_i':1,'filter_i':1,'thresh_i':2},{'enable_i':1,'filter_i':1,'thresh_i':2},
        {'enable_i':1,'filter_i':1,'thresh_i':2,'filter_o':1}],[])
    d=x.definition('onehot');assert check_inputs(d,[dict(rst_n=1,oh_i=16,en_i=0,addr_i=0)])
    x.dump(x.OUT/'oracle_qualification.json',dict(passed=True,cohort='hand_constructed_monitor_QA_not_natural_search',tests=results,
        limitations=['sampled reset semantics; asynchronous between-edge reset independently checked in SV qualification','independent specification monitor, not whole-design verification']))


def old_pairs():
    x.guard();folder=x.OUT/'legacy_replay';folder.mkdir(exist_ok=False)
    pairs=x.read(x.OUT/'pairs_frozen.json')
    focused=[p for p in pairs if p['natural_pair'] and p['status']=='distinguished_on_checked_legal_inputs']
    parents=collections.defaultdict(set)
    for p in focused:
        parents[p['parent_bug_id']].update([p['a'],p['b']])
    results={};sources={};n=0
    for parent,slots in parents.items():
        base=x.ROOT/'outputs/behavioral_preference_pilot_v1/behavioral_probes_v3'/parent
        pr=x.read(base/'parent_result.json');sources[str(base)]=x.snapshot(base/'parent_result.json')
        for probe in pr['policies']['disagreement_guided']:
            for slot in sorted(slots):
                cid=f'{parent}__v3_{slot}';oldfolder=base/'runs'/probe/cid
                old=x.read(oldfolder/'result.json')
                ident=x.digest([parent,probe,slot])[:20];target=folder/ident;target.mkdir()
                x.dump(target/'original_result.json',old)
                shutil.copy2(oldfolder/'checker.sv',target/'checker.sv')
                record=dict(parent=parent,probe=probe,slot=slot,original=x.rel(oldfolder),new=x.rel(target),variants={})
                for variant in ['correct','buggy']:
                    orig=old['rtl'][variant];argv=list(orig['compile_command'])
                    output=target/(variant+'.out');argv[argv.index('-o')+1]=str(output)
                    argv[-1]=str(target/'checker.sv')
                    rtl=x.ROOT/orig['rtl_path']
                    assert x.sha(rtl)==orig['rtl_sha256']
                    assert x.sha(target/'checker.sv')==old['checker_sha256']
                    # Copy the exact stimulus and RTL, preserving include paths.
                    for index,name in [(-3,variant+'_rtl.v'),(-2,'stimulus.v')]:
                        source=Path(argv[index]);shutil.copy2(source,target/name);argv[index]=str(target/name)
                    b=x.command(argv,target,variant+'_compile')
                    s=x.command(['vvp',str(output)],target,variant+'_simulate',15) if b['status']=='ok' else None
                    metric=None
                    if s and s['status']=='ok':
                        match=re.search(r'V3_PROBE_METRIC ant_hits=(\d+) fail_hits=(\d+)',(target/(variant+'_simulate.stdout')).read_text())
                        if match:metric=list(map(int,match.groups()))
                    expected=[orig['antecedent_hits'],orig['fail_hits']]
                    record['variants'][variant]=dict(compile=b,simulate=s,metrics=metric,expected=expected,matched=metric==expected)
                x.dump(target/'result.json',record);x.append(folder/'runs.jsonl',record)
                results[(parent,probe,slot)]=record;n+=1
                if n%50==0:print('LEGACY',n,flush=True)
    output=[]
    for pair in focused:
        parent=pair['parent_bug_id'];base=x.ROOT/'outputs/behavioral_preference_pilot_v1/behavioral_probes_v3'/parent
        pr=x.read(base/'parent_result.json');signatures={};all_matched=True
        for slot in [pair['a'],pair['b']]:
            fp=[];tp=[]
            for probe in pr['policies']['disagreement_guided']:
                r=results[(parent,probe,slot)];a=r['variants']['correct'];b=r['variants']['buggy']
                all_matched &= a['matched'] and b['matched']
                if a['metrics'] and a['metrics'][1]:fp.append(probe)
                if b['metrics'] and b['metrics'][1]:tp.append(probe)
            signatures[slot]=dict(fp_probe_ids=fp,tp_mutant_ids=tp)
        equal=signatures[pair['a']]==signatures[pair['b']]
        output.append(dict(pair_id=pair['pair_id'],parent=parent,a=pair['a'],b=pair['b'],all_raw_metrics_reproduced=all_matched,
            equal_binary_feedback=equal,signatures=signatures,old_signature=pair['old_signature'],
            old_signature_reproduced=all(set(signatures[pair['a']][n])==set(pair['old_signature'][n]) for n in ['fp_probe_ids','tp_mutant_ids'])))
    x.dump(folder/'pair_checks.json',output)
    x.dump(folder/'summary.json',dict(focused_pairs=len(output),equal=sum(p['equal_binary_feedback'] for p in output),
        old_signature_reproduced=sum(p['old_signature_reproduced'] for p in output),all_metrics_reproduced=all(p['all_raw_metrics_reproduced'] for p in output),
        physical_compiles=2*len(results),physical_simulations=sum(v['simulate'] is not None for r in results.values() for v in r['variants'].values()),
        sources=list(sources.values()),cost_scope='shared baseline, excluded from all search arms; no ranking labels given to search'))
    print(json.dumps(x.read(folder/'summary.json')))


def minimize():
    """Delta-reduce selected concrete witnesses using actual RTL and private oracle.

    QA cost is separate from search. Deletion-minimal is relative to deletion of
    a single active sample; no claim of globally shortest stimulus.
    """
    x.guard();(x.OUT/'minimal').mkdir(exist_ok=False)
    x.engine.OUT=x.OUT;x.engine.tb_text=x.checker.tb_text
    x.engine.sources=lambda d:(x.OUT/'frozen'/d['key']/'correct.v',x.OUT/'frozen'/d['key']/'buggy.v')
    queries=[json.loads(s) for s in (x.OUT/'search/queries.jsonl').read_text().splitlines()]
    picks=[]
    for k in x.IDS:
        evs=[e for q in queries if q['case']==k for e in q['evidence']]
        for kind in ['miss','false_positive']:
            candidates=[e for e in evs if e['kind']==kind]
            if candidates:picks.append((k,min(candidates,key=lambda e:e['cycle'])))
    results=[]
    for k,ev in picks:
        source=x.ROOT/ev['run'];d=x.read(source/'definition.json');cs=x.read(source/'candidates.json')
        c=next(z for z in cs if z['id']==ev['candidate_id']);rows=x.read(source/'input.json')[:ev['cycle']+1]
        name=k+'_'+ev['kind'];calls=[]
        def accepts(trial):
            for i,r in enumerate(trial):r['cycle']=i;r['stimulus_id']=f'min:{i}'
            if check_inputs(d,trial):return False,None
            label=f'minimal/{name}/{len(calls):04d}'
            raw=x.engine.execute_run(d,trial,[c],label,ev['variant']);folder=x.ROOT/raw['run_id']
            a=x.adjudicate_folder(folder,d) if raw['status']=='ok' else dict(status=raw['status'])
            x.dump(folder/'adjudication.json',a)
            # Preserve the same obligation component(s), not just any failure.
            components={z['obligation'] for z in ev['obligations'] if not z.get('conditional') and not z['passed']}
            hits=[z for group in a.get('evidence',[]) for z in group if z['kind']==ev['kind'] and
                  (not components or components & {v['obligation'] for v in z['obligations'] if not v['passed']})]
            calls.append(dict(run=raw['run_id'],status=a['status'],preserves=bool(hits),cycles=len(trial),seconds=raw['validation_wall_seconds']))
            return bool(hits),raw['run_id']
        ok,chosen=accepts(copy.deepcopy(rows));assert ok,(k,ev)
        changed=True
        while changed:
            changed=False
            for i in range(2,len(rows)):
                trial=copy.deepcopy(rows[:i]+rows[i+1:])
                ok,run=accepts(trial)
                if ok:rows=trial;chosen=run;changed=True;break
        results.append(dict(case=k,kind=ev['kind'],original_witness=ev,minimal_run=chosen,sampled_cycles=len(rows),
            minimality='one-active-sample deletion minimal while retaining initial two reset samples and environment legality',calls=calls))
        print('MINIMAL',name,len(rows),len(calls),flush=True)
    x.dump(x.OUT/'minimal/index.json',results)


def complete_ledger():
    x.guard();folder=x.OUT/'baseline/omitted_unknowns';folder.mkdir(exist_ok=False)
    mapping=x.read(x.OUT/'baseline/replay_mapping.json')
    finals=[r for r in x.read(x.OLD/'hidden_evaluations.json') if r['final']]
    all_runs=set(n for r in finals for n in r['evaluation']['run_ids'])
    extra={}
    for name in sorted(all_runs-set(mapping)):
        target=folder/x.digest(name)[:20]
        result=x.replay_one(x.ROOT/name,target);result['new_run']=x.rel(target);extra[name]=result
    mapping.update(extra)
    x.dump(folder/'replay_mapping.json',extra)
    rows=x.read(x.OUT/'problem_ledger.json')
    for row in rows:
        f=next(r for r in finals if r['case']==row['case'] and r['arm']==row['method'])
        names=f['evaluation']['run_ids'];missing=set(names)-set(row['original_run_ids'])
        row['original_run_ids']=names
        row['source_scope_correction']='Final hidden evaluation index includes unsupported runs omitted by old conditional_results.runs; initial audit preserved unchanged.'
        row['replays']+=[dict(original=n,replay=mapping[n]['new_run'],status=mapping[n]['status'],exact=mapping[n].get('identical_trace_check_records')) for n in sorted(missing)]
        if any(mapping[n]['status']!='ok' for n in names):
            row['categories']=sorted(set(row['categories'])|{'checker_or_execution_problem'})
            row['reclassified_status']='unknown_full_contract'
            row['unresolved'].append('Frozen expression is unsupported; compiler stderr in omitted_unknowns; not an assertion semantic failure')
    x.dump(x.OUT/'problem_ledger_complete.json',rows)
    x.dump(folder/'summary.json',dict(extra_runs=len(extra),total_runs=len(mapping),statuses=dict(collections.Counter(r['status'] for r in mapping.values())),
        exact_successful_replays=sum(r.get('identical_trace_check_records') is True for r in mapping.values()),
        ledger_cells=len(rows),original_states=dict(collections.Counter(r['original_status'] for r in rows)),
        classifications=dict(collections.Counter(r['reclassified_status'] for r in rows))))
    print(json.dumps(x.read(folder/'summary.json')))


def legacy_feedback():
    """Rebuild original FP/TP definition including fixed-safe TP gate and RTL ID.

    The initial raw-bug-alarm comparison is retained as a diagnostic, not called
    the historical feedback. No extra simulator calls are needed.
    """
    folder=x.OUT/'legacy_replay'
    runs=[json.loads(s) for s in (folder/'runs.jsonl').read_text().splitlines()]
    by={(r['parent'],r['probe'],r['slot']):r for r in runs}
    output=[]
    for p in x.read(x.OUT/'pairs_frozen.json'):
        if not p['natural_pair'] or p['status']!='distinguished_on_checked_legal_inputs':continue
        parent=p['parent_bug_id'];pr=x.read(x.ROOT/'outputs/behavioral_preference_pilot_v1/behavioral_probes_v3'/parent/'parent_result.json')
        sig={};matched=True
        for slot in [p['a'],p['b']]:
            fp=[];tp=[]
            for probe in pr['policies']['disagreement_guided']:
                r=by[(parent,probe,slot)];a=r['variants']['correct'];b=r['variants']['buggy']
                matched &= a['matched'] and b['matched']
                raw=x.read(x.ROOT/r['new']/'original_result.json')
                executable=a['metrics'] is not None and b['metrics'] is not None
                isfp=executable and a['metrics'][1]>0
                istp=executable and b['metrics'][1]>0 and a['metrics'][1]==0
                assert (isfp,istp)==(raw['fp'],raw['tp'])
                if isfp:fp.append(probe)
                if istp:tp.append(probe+'@'+raw['rtl']['buggy']['rtl_sha256'][:16])
            sig[slot]=dict(fp_probe_ids=sorted(fp),tp_mutant_ids=sorted(tp))
        expected={n:sorted(p['old_signature'][n]) for n in ['fp_probe_ids','tp_mutant_ids']}
        output.append(dict(pair_id=p['pair_id'],parent=parent,signatures=sig,equal=sig[p['a']]==sig[p['b']],
            original_signature_reproduced=sig[p['a']]==sig[p['b']]==expected,all_metrics_reproduced=matched))
    x.dump(folder/'corrected_feedback_checks.json',output)
    result=dict(pairs=len(output),equal=sum(r['equal'] for r in output),original_signature_reproduced=sum(r['original_signature_reproduced'] for r in output),
        all_metrics_reproduced=all(r['all_metrics_reproduced'] for r in output),additional_queries=0,
        definition='executable && fixed_fail>0 => FP; executable && fixed_fail==0 && buggy_fail>0 => TP; mutant ID probe@buggy_RTL_sha256[:16]',
        source='src/behavioral_preference_v3_probes.py:246-251,349',source_sha256=x.sha(x.ROOT/'src/behavioral_preference_v3_probes.py'),
        correction='Earlier pair_checks.json compared raw buggy alarms without the historical fixed-safe gate or mutant hash suffix. Preserved for transparency; use this corrected result for old-feedback reproduction.')
    x.dump(folder/'corrected_feedback_summary.json',result);print(json.dumps(result))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('action',choices=['oracle_tests','old_pairs','minimize','complete_ledger','legacy_feedback']);a=ap.parse_args()
    x.OUT=x.ROOT/'deliverables'/a.run
    globals()[a.action]()
