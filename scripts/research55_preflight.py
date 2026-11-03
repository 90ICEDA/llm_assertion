"""Offline source, native trace, schema-feedback and isolation checks for research55."""
import argparse
import json
import re
from pathlib import Path
from unittest.mock import patch
import research55_native_plan_alignment as g


def run(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for name,sha in g.read(prep/'sealed.json').items():check('sealed/'+name,g.old.digest(prep/name)==sha)
    for name,sha in g.read(prep/'source_hashes.json').items():check('source/'+name,g.old.digest(g.ROOT/'scripts'/name)==sha)
    for name,sha in g.read(prep/'failure_binding.json').items():check('actual_failure/'+name,g.old.digest(g.ROOT/name)==sha)
    g.prior.components(prep)
    check('qualification_passed',g.read(prep/'qualification.json')['passed'])
    current=g.read(prep/'shared_initial.json');feedback=g.read(prep/'initial_feedback.json')
    with patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')):
        model=g.Model(out/'transport_metadata_only',prep)
        request=model._payload(current,None,feedback,'sva')
        check('sealed_request_matches_actual_transport',request==g.read(prep/'request.preview.json'))
        check('no_calls_during_preflight',model.calls==[])
        check('two_call_budget',model.config['max_model_calls']==2)
    body=json.loads(request['messages'][1]['content'])
    check('no_example_wrapper','output' not in body)
    check('private_answer_not_sent',not any(k in body for k in ('expected','expected.private','correct_answers')))
    check('actual_prior_proposals_in_feedback',all(x['actual_model_proposal']==g.read(g.R54/x['version']/'model_call/model_edit.json')
          for x in body['actual_development_feedback']['previous_real_attempts']))
    check('independent_test_not_present',not (prep/'independent').exists())
    check('old_research54_failure_unchanged',g.read(g.R54/'outcome.json')['status']=='no_accepted_sva')
    native_counts={}
    for folder in sorted((prep/'qualification').iterdir()):
        if not folder.is_dir():continue
        candidate=g.read(folder/'candidate.json');base=folder/'native';result=g.read(base/'result.json')
        gate=g.read(base/'alignment_gate.json');rows=g.read(base/'samples.json')
        check(folder.name+'/samples_from_development',rows==g.old.samples(g.read(prep/'alignment_cases.json'),'alignment'))
        check(folder.name+'/fixed_branch_unchanged',candidate['assertions'][0]==g.read(prep/'protected_branch.json'))
        traces={};markers={};natives={}
        for rev in ('before','after'):
            path=base/rev;native=g.read(path/'result.json');natives[rev]=native
            check(folder.name+'/'+rev+'/native_complete',native['compile_status']=='passed' and native['execution_status']=='completed')
            check(folder.name+'/'+rev+'/original_rtl',all(str(prep/rev/n) in native['compile']['argv'] for n in ('ibex_defines.sv','ibex_decoder.sv')))
            check(folder.name+'/'+rev+'/exact_property_testbench',(path/'tb.sv').read_text()==g.old.bench(candidate,rows,g.old.CONFIGS,base/'stimulus.txt'))
            traces[rev]=g.common.trace(path/'execute.log')
            check(folder.name+'/'+rev+'/sample_complete',set(traces[rev])==set(range(len(rows))))
            text=(path/'execute.log').read_text()
            markers[rev]={kind:{(m[0],int(m[1])) for m in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',text,re.M)} for kind in ('TRIGGER','ASSERT_FAIL')}
            check(folder.name+'/'+rev+'/wave_exists',(path/'wave.vcd').stat().st_size>0)
        issues=[]
        for row in result['ledger']:
            sample=row['sample'];sid=sample['sample_id'];ci=g.old.CONFIGS.index(row['configuration']);rev=row['revision']
            observed={v:(int(traces[v][sid]['observed'],2)>>ci)&1 for v in traces}
            expected=g.old.historical.oracle(sample['instruction'],sample['instr_new'],row['configuration'])
            ok=rows[sid]==sample and row['expected']==expected and row['observed']==observed[rev] and observed['after']==expected
            for v,t in traces.items():
                ok &= int(t[sid]['instr'],16)==sample['instruction'] and int(t[sid]['new'])==sample['instr_new']
                ok &= int(t[sid]['txn'])==sample['transaction_id'] and int(t[sid]['phase'])==sample['phase']
            for a in row['native']['assertions']:
                prop=next(p for p in candidate['assertions'] if p['id']==a['id']);name=a['id']+f'_c{ci}'
                trigger=(name,sid-prop['delay']) in markers[rev]['TRIGGER'];failed=(name,sid) in markers[rev]['ASSERT_FAIL']
                detected=rev=='before' and observed[rev]!=expected and observed['after']==expected and trigger and failed and (name,sid) not in markers['after']['ASSERT_FAIL']
                ok &= (trigger,failed,detected)==(a['trigger'],a['failed'],a['causal_detection'])
            if not ok:issues.append(row['evidence_id'])
        check(folder.name+'/raw_trace_and_covers',not issues and len(result['ledger'])==len(rows)*6)
        info=g.old.acceptance.inspect(result['ledger'])
        check(folder.name+'/counts_and_mapping',result['counts']=={k:len(info[k]) for k in result['counts']} and result['mapping']==info['mapping'])
        guard=g.prior.all_property_guard(result,natives,candidate)
        check(folder.name+'/all_property_gate',guard==gate['all_property_guard'])
        check(folder.name+'/window_bindings_complete',len(gate['bindings'])==12 and all(b['original_sampling_matches'] for b in gate['bindings']))
        check(folder.name+'/native_gate_decision',gate['accepted']==(g.old.admissible(result) and guard['accepted'] and all(b['accepted'] for b in gate['bindings'])))
        native_counts[folder.name]=dict(accepted=gate['accepted'],counts=result['counts'],required_untriggered=gate['required_untriggered'])
    check('four_controls',len(native_counts)==4)
    check('only_correct_control_passed',[name for name,r in native_counts.items() if r['accepted']]==['correct_local_control'])
    g.dump(out/'result.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,native_control_results=native_counts))
    print('NATIVE_ALIGNMENT_PREFLIGHT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
