"""Separate local replay of actual model responses with optional label metadata.

research57's sealed interface failures stay failures. This prospective adapter
accepts optional assertion IDs only, never changing predicates or timing. No LLM
calls. Complete development replay diagnoses both actual proposals, even when a
small probe would reject them; no independent testing or retrospective success.
"""
import argparse
import copy
import json
import re
from pathlib import Path
import research57_legal_refinement as g


def adapt(value,current):
    if type(value) is not dict or set(value)!={'operation','reason','assertions'}:raise ValueError('top_level_fields')
    if type(value['assertions']) is not list:raise ValueError('assertions_not_array')
    clean=copy.deepcopy(value);labels=[];seen=set()
    for index,item in enumerate(clean['assertions'],1):
        if type(item) is not dict:raise ValueError('assertion_not_object')
        if 'id' in item:
            label=item.pop('id')
            if type(label) is not str or not re.fullmatch(r'[A-Za-z_]\w*',label) or label in seen or label=='a0':
                raise ValueError('invalid_duplicate_or_reserved_label')
            seen.add(label)
        else:label=None
        labels.append(dict(model_label=label,native_label=f'a{index}'))
    candidate,gate=g.native_flow.frontend(clean,current)
    if candidate is None:raise ValueError(json.dumps(gate))
    for raw,compiled in zip(value['assertions'],candidate['assertions'][1:]):
        assert all(raw[k]==compiled[k] for k in ('antecedent','consequent','timing','obligations'))
    assert candidate['assertions'][0]==current['assertions'][0]
    return candidate,labels


def audit_native(folder,candidate,prep,cohort):
    result=g.read(folder/'result.json');rows=g.old.samples(g.read(prep/(cohort+'_cases.json')),cohort)
    assert rows==g.read(folder/'samples.json')
    trace={};marks={}
    for rev in ('before','after'):
        path=folder/rev;n=g.read(path/'result.json')
        assert n['compile_status']=='passed' and n['execution_status']=='completed'
        assert (path/'tb.sv').read_text()==g.old.bench(candidate,rows,g.old.CONFIGS,folder/'stimulus.txt')
        assert all(str(prep/rev/name) in n['compile']['argv'] for name in ('ibex_decoder.sv','ibex_defines.sv'))
        trace[rev]=g.common.trace(path/'execute.log');assert set(trace[rev])==set(range(len(rows)))
        log=(path/'execute.log').read_text();marks[rev]={kind:{(m[0],int(m[1])) for m in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',log,re.M)} for kind in ('TRIGGER','ASSERT_FAIL')}
        assert (path/'wave.vcd').stat().st_size>0
    for r in result['ledger']:
        s=r['sample'];sid=s['sample_id'];ci=g.old.CONFIGS.index(r['configuration']);rev=r['revision']
        expected=g.old.historical.oracle(s['instruction'],s['instr_new'],r['configuration'])
        actual={v:(int(trace[v][sid]['observed'],2)>>ci)&1 for v in trace}
        assert r['expected']==expected and r['observed']==actual[rev] and actual['after']==expected
        for v in trace:
            t=trace[v][sid]
            assert int(t['instr'],16)==s['instruction'] and int(t['new'])==s['instr_new'] and int(t['txn'])==s['transaction_id'] and int(t['phase'])==s['phase']
        for a in r['native']['assertions']:
            p=next(p for p in candidate['assertions'] if p['id']==a['id']);name=a['id']+f'_c{ci}'
            triggered=(name,sid-p['delay']) in marks[rev]['TRIGGER'];failed=(name,sid) in marks[rev]['ASSERT_FAIL']
            detected=rev=='before' and actual[rev]!=expected and triggered and failed and (name,sid) not in marks['after']['ASSERT_FAIL']
            assert (a['trigger'],a['failed'],a['causal_detection'])==(triggered,failed,detected)
    info=g.old.acceptance.inspect(result['ledger'])
    assert result['counts']=={k:len(info[k]) for k in result['counts']}
    assert result['mapping']==info['mapping']
    assert set(result['required_untriggered'])=={k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']}
    return len(result['ledger'])


def run(prep,source,out):
    out.mkdir(parents=True,exist_ok=False)
    for n,h in g.read(prep/'sealed.json').items():assert g.old.digest(prep/n)==h,n
    original_outcome_hash=g.old.digest(source/'outcome.json')
    current=g.read(prep/'shared_initial.json');baseline=g.read(prep/'baseline_full.json')
    protected=g.read(prep/'target_preservation.private.json');checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    value=g.read(source/'v0/model_call/model_edit.json');candidate,labels=adapt(value,current)
    check('actual_predicate_bytes_preserved',all(a['antecedent']==b['antecedent'] and a['consequent']==b['consequent'] and a['timing']==b['timing'] for a,b in zip(value['assertions'],candidate['assertions'][1:])))
    for name,mutation in [('reserved',lambda v:v['assertions'][0].update(id='a0')),('unknown_field',lambda v:v['assertions'][0].update(extra=True)),('invalid_id',lambda v:v['assertions'][0].update(id='x;'))]:
        bad=copy.deepcopy(value);mutation(bad)
        try:adapt(bad,current)
        except ValueError:check('reject/'+name,True)
        else:raise AssertionError(name)
    duplicate=copy.deepcopy(value);duplicate['assertions'].append(copy.deepcopy(duplicate['assertions'][0]))
    try:adapt(duplicate,current)
    except ValueError:check('reject/duplicate_label',True)
    else:raise AssertionError('duplicate_label')
    dump=g.dump
    dump(out/'protocol.json',dict(scope='Local compatibility replay of immutable real research57 responses',model_calls=0,
        allowed_change='Optional id is label metadata only; all predicate strings, obligations and timing preserved exactly.',
        original_experiment_unchanged=True,full_development_replay_even_if_probe_would_fail=True,independent_test='not_run'))
    dump(out/'adapter_checks.json',dict(passed=True,checks=checks))
    versions=[]
    try:
        for name in ('v0','v1'):
            raw=g.read(source/name/'model_call/model_edit.json')
            content=g.read(source/name/'model_call/response.assembled.json')['message']['content']
            assert json.loads(content)==raw
            proposed,labels=adapt(raw,current);folder=out/name
            dump(folder/'source.json',dict(model_edit=(source/name/'model_call/model_edit.json').relative_to(g.ROOT).as_posix(),
                model_edit_sha256=g.old.digest(source/name/'model_call/model_edit.json'),response_sha256=g.old.digest(source/name/'model_call/response.stream.raw'),
                original_interface_decision=g.read(source/name/'decision.json'),labels=labels,predicates_rewritten=False))
            dump(folder/'candidate.json',proposed)
            (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in proposed['assertions'])+'\n')
            h=g.old.replay(proposed,g.read(prep/'history_cases.json'),'history',folder/'history',prep)
            s=g.old.replay(proposed,g.read(prep/'search_cases.json'),'search',folder/'search',prep)
            verified=sum(audit_native(folder/cohort,proposed,prep,cohort) for cohort in ('history','search'))
            combined=g.common.combine(h,s);decision=g.old.decide(baseline,combined)
            guards={cohort:g.native_flow.prior.all_property_guard(result,{rev:g.read(folder/cohort/rev/'result.json') for rev in ('before','after')},proposed) for cohort,result in [('history',h),('search',s)]}
            info=g.old.acceptance.inspect(combined['ledger'])
            lost={ob:sorted(set(ids)-info['detections']) for ob,ids in protected.items()}
            for cohort,guard in guards.items():
                if not guard['accepted']:decision['accepted']=False;decision['reasons'].append(dict(kind='all_property_false_alarm_or_unknown',cohort=cohort,details=guard))
            if any(lost.values()):decision['accepted']=False;decision['reasons'].append(dict(kind='lost_research56_target_detection',counts={ob:len(ids) for ob,ids in lost.items()}))
            dump(folder/'decision.json',decision);dump(folder/'all_property_guard.json',guards);dump(folder/'lost_target_evidence.json',lost)
            summary=dict(version=name,development_checks_pass=decision['accepted'],counts=combined['counts'],
                preserved={ob:len(ids)-len(lost[ob]) for ob,ids in protected.items()},lost={ob:len(ids) for ob,ids in lost.items()},
                required_untriggered=len(combined['required_untriggered']),raw_rows_audited=verified)
            versions.append(summary);print('LABEL_REPLAY',json.dumps(summary),flush=True)
    finally:
        assert g.old.digest(source/'outcome.json')==original_outcome_hash
        dump(out/'outcome.json',dict(status='local_compatibility_diagnosis',versions=versions,model_calls=0,
            original_research57_still_rejected=True,independent_test='not_run',frozen=False))
        dump(out/'cost.json',g.old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--source-run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.source_run.resolve(),a.out.resolve())
