"""Offline validation of legal-feedback bindings and native qualification logs."""
import argparse
import json
import re
from pathlib import Path
from unittest.mock import patch
import research57_legal_refinement as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for n,h in g.read(prep/'sealed.json').items():check('seal/'+n,g.old.digest(prep/n)==h)
    for n,h in g.read(prep/'source_hashes.json').items():check('source/'+n,g.old.digest(g.ROOT/'scripts'/n)==h)
    for n,h in g.read(prep/'failure_binding.json').items():check('evidence/'+n,g.old.digest(g.ROOT/n)==h)
    g.native_flow.prior.components(prep)
    pack=g.read(prep/'evidence_pack.json')
    for kind in ('representative_false_alarms','representative_targets'):
        for row in pack[kind]:
            result=g.read(g.R56/f'v0/{row["cohort"]}/result.json')
            raw=next(r for r in result['ledger'] if r['evidence_id']==row['evidence_id'])
            check('representative/'+row['evidence_id'],row==dict(cohort=row['cohort'],**g.row_view(raw)))
    target={ob:[] for ob in ('op_bit28_illegal','illegal_branch_persists')}
    for cohort in ('history','search'):
        result=g.read(g.R56/f'v0/{cohort}/result.json');info=g.old.acceptance.inspect(result['ledger'])
        for ob in target:target[ob]+=[k for k in info['detections'] if info['rows'][k]['obligation']==ob]
    private=g.read(prep/'target_preservation.private.json')
    check('exact_target_keys',{k:set(v) for k,v in private.items()}=={k:set(v) for k,v in target.items()})
    check('420_and270',len(target['op_bit28_illegal'])==420 and len(target['illegal_branch_persists'])==270)
    for b in g.read(prep/'added_legal_probe_binding.json'):
        original=next(t for t in g.read(prep/(b['cohort']+'_cases.json')) if t['id']==b['source_transaction_id'])
        replay=next(t for t in g.read(prep/'alignment_cases.json') if t['id']==b['replay_transaction_id'])
        check('legal_probe_exact/'+b['assertion'],replay=={**original,'id':b['replay_transaction_id']})
    for label in ('actual_overbroad','local_correct_control'):
        sources=g.read(prep/'qualification_sources.json')
        folder=g.ROOT/sources[label] if label in sources else prep/'qualification'/label/'native'
        measured_prep=folder.parents[2];candidate=g.read(folder.parent/'candidate.json')
        result=g.read(folder/'result.json');rows=g.read(folder/'samples.json');gate=g.read(folder/'alignment_gate.json')
        check(label+'/input_samples',rows==g.old.samples(g.read(prep/'alignment_cases.json'),'alignment'))
        traces={};markers={};natives={}
        for rev in ('before','after'):
            path=folder/rev;natives[rev]=g.read(path/'result.json');n=natives[rev]
            check(label+'/'+rev+'/compiled_executed',n['compile_status']=='passed' and n['execution_status']=='completed')
            check(label+'/'+rev+'/original_rtl',all(str(measured_prep/rev/name) in n['compile']['argv'] and g.old.digest(measured_prep/rev/name)==g.old.digest(prep/rev/name) for name in ('ibex_decoder.sv','ibex_defines.sv')))
            check(label+'/'+rev+'/exact_bench',(path/'tb.sv').read_text()==g.old.bench(candidate,rows,g.old.CONFIGS,folder/'stimulus.txt'))
            traces[rev]=g.common.trace(path/'execute.log');log=(path/'execute.log').read_text()
            markers[rev]={kind:{(m[0],int(m[1])) for m in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',log,re.M)} for kind in ('TRIGGER','ASSERT_FAIL')}
            check(label+'/'+rev+'/complete_trace',set(traces[rev])==set(range(len(rows))))
            check(label+'/'+rev+'/wave',(path/'wave.vcd').stat().st_size>0)
        issues=[]
        for row in result['ledger']:
            s=row['sample'];sid=s['sample_id'];cfg=row['configuration'];ci=g.old.CONFIGS.index(cfg);rev=row['revision']
            actual={v:(int(traces[v][sid]['observed'],2)>>ci)&1 for v in traces}
            expected=g.old.historical.oracle(s['instruction'],s['instr_new'],cfg)
            ok=s==rows[sid] and row['expected']==expected and row['observed']==actual[rev] and actual['after']==expected
            for v in traces:
                t=traces[v][sid];ok &= int(t['instr'],16)==s['instruction'] and int(t['new'])==s['instr_new'] and int(t['txn'])==s['transaction_id'] and int(t['phase'])==s['phase']
            for a in row['native']['assertions']:
                prop=next(p for p in candidate['assertions'] if p['id']==a['id']);name=a['id']+f'_c{ci}'
                trigger=(name,sid-prop['delay']) in markers[rev]['TRIGGER'];failed=(name,sid) in markers[rev]['ASSERT_FAIL']
                detect=rev=='before' and actual[rev]!=expected and trigger and failed and (name,sid) not in markers['after']['ASSERT_FAIL']
                ok &= (trigger,failed,detect)==(a['trigger'],a['failed'],a['causal_detection'])
            if not ok:issues.append(row['evidence_id'])
        check(label+'/ledger_from_raw',not issues and len(result['ledger'])==len(rows)*6)
        info=g.old.acceptance.inspect(result['ledger'])
        check(label+'/counts',result['counts']=={k:len(info[k]) for k in result['counts']})
        guard=g.native_flow.prior.all_property_guard(result,natives,candidate)
        check(label+'/all_property_guard',guard==gate['all_property_guard'])
        check(label+'/expected_gate',gate['accepted']==(label=='local_correct_control'))
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata_only',prep)
        req=model._payload(current,None,feedback,'sva')
        check('actual_payload_equals_sealed',req==g.read(prep/'request.preview.json'))
        body=json.loads(req['messages'][1]['content'])
        check('actual_model_candidate_in_request',body['current_assertions']==g.read(g.R56/'v0/model_call/candidate.json'))
        check('original_rtl_unabridged',all(body['rtl'][rev][p.name]==p.read_text() for rev in ('before','after') for p in (prep/rev).glob('*.sv')))
        check('private_target_ids_not_sent',not any(k in req['messages'][1]['content'] for ids in private.values() for k in ids if k not in [r['evidence_id'] for r in pack['representative_targets']]))
        try:model._payload(current,None,dict(extra='x'*g.MAX_MESSAGE_BYTES),'sva')
        except RuntimeError as exc:check('oversize_refused_before_network',str(exc)=='local_request_byte_budget_exceeded_before_submission')
        else:raise AssertionError('oversized_request_allowed')
        check('two_call_cap_no_calls',model.config['max_model_calls']==2 and model.calls==[])
    check('no_test_data_generated',not (prep/'independent').exists())
    check('old_outcome_unchanged',g.read(g.R56/'outcome.json')['status']=='no_accepted_sva')
    g.dump(out/'result.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0))
    print('LEGAL_REFINEMENT_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
