"""Local preflight using actual replay data; no model or simulator invocation."""
import argparse
import json
from pathlib import Path
import research45_campaign as campaign
import research43_paired_ablation as old
import research17_loop as loop
import research31_gate as gate


def check(prep,out):
    out.mkdir(parents=True,exist_ok=False)
    old.check_sources(prep)
    initial=loop.read(prep/'shared_initial.json')
    rows=[]
    for name,seed,rounds in [('pilot',campaign.PILOT_SEED,3)]+[(f'arms/{n}',campaign.COMPARISON_SEED,2) for n in old.ARMS]:
        request=loop.read(prep/name/'request.preview.json')
        config=campaign.settings(seed,rounds)
        model=campaign.Model(out/name,config,request)
        assert model._payload()==request
        metadata=loop.read(out/name/'remote_transport_config.json')
        assert metadata['max_output_tokens']==request['max_tokens']==2048
        assert not model.calls
        before=campaign.baseline(prep,name)
        assert before['healthy']
        body=json.loads(request['messages'][1]['content'])
        assert all('reason' not in p for p in body['current_assertions'])
        reserve=sum(len(m['content'].encode()) for m in request['messages'])+2048+request['max_tokens']
        assert reserve<=config['max_tokens']
        # Exercise actual diagnostic projection and second-round serialization.
        empty=dict(accepted=False,reasons=[dict(kind='qualification_only_current_miss')])
        diagnostic=campaign.feedback(before,empty,{},None)
        updated=campaign.request_from(request,initial,seed,diagnostic)
        after=json.loads(updated['messages'][1]['content'])
        assert after['actual_previous_attempt']==diagnostic
        assert {k:v for k,v in after.items() if k!='actual_previous_attempt'}=={k:v for k,v in body.items() if k!='actual_previous_attempt'}
        allowed={c['id'] for c in loop.read(prep/name/'cases.json')}
        for category in ('legal_false_alarms','missed_obligations','unknown'):
            assert all(card['scenario'] in allowed for card in diagnostic[category])
        rows.append(dict(name=name,actual_native_baseline_healthy=True,second_round_scope_preserved=True,
            request_unchanged=True,conservative_first_call_reservation=reserve,request_sha256=old.digest(prep/name/'request.preview.json')))
    exclusions=set(loop.read(prep/'excluded_tests.json')['input_hashes'])
    previous=loop.read(loop.ROOT/'deliverables/research43_real_20261022_r01/common_independent_split.json')
    assert {loop.sha(c['rows']) for c in previous['boundary_cases']+previous['drain_cases']}<=exclusions
    binding=loop.read(prep/'bootstrap_binding.json');root=gate.portable(binding['path'])
    assert old.digest(root/'native/result.json')==binding['result_sha256']
    assert old.digest(root/'original_model_edit.json')==binding['edit_sha256']
    loop.dump(out/'qualification.json',dict(passed=True,requests=rows,prior_test_inputs_excluded=True,
        model_calls=0,native_calls=0,credential_read=False,scope='Preflight only; diagnostic rejection label is a validator fixture, not a real model outcome. All sampled observations come from existing actual native results.'))
    print('PREFLIGHT_PASSED',len(rows),'requests',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();check(a.prepared.resolve(),a.out.resolve())
