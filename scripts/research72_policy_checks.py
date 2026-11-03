"""Local controller fixtures and read-only native preflight, NOT model results."""
import copy
import json
from pathlib import Path
from unittest.mock import patch

import research72_policy as q
import research68_result_audit as raw

b, read, dump = q.b, q.read, q.dump


def checks(out, prep):
    out.mkdir(parents=True, exist_ok=False)
    names = []
    def check(name, value):
        assert value, name
        names.append(name)
    initial = read(q.P/'shared_initial.json')
    checks_before = 0
    native_count = 0
    with b.extension.installed():
        for seed in b.SEEDS:
            ready = q.P/'ready'/f's{seed}'
            bodies = {}
            for name, arm in q.ARMS.items():
                source = ready/('search' if arm['search'] else 'ordinary')/'request.preview.json'
                req = read(prep/f's{seed}'/name/'request.preview.json')
                check(f'{seed}/{name} exact original request', req == read(source))
                bodies[name] = json.loads(req['messages'][1]['content'])
                check(f'{seed}/{name} no previous proposal', 'actual_previous_attempt' not in bodies[name])
                check(f'{seed}/{name} no archived run supplied', not any(
                    t in json.dumps(req) for t in ('research69_pilot','research71','independent_test')))
                config = read(prep/f's{seed}'/name/'model_config.json')
                check(f'{seed}/{name} equal finite budgets', config['max_model_calls']==2 and
                      config['max_tokens']==400000 and config['call_timeout']==300 and req['max_tokens']==2048)
                model = q.Model(out/'payload_preflight'/f's{seed}'/name, config, req)
                check(f'{seed}/{name} payload override exact and not sent', model._payload()==req and not model.calls)
                check(f'{seed}/{name} actual deadline metadata', read(model.out/'remote_transport_config.json')['timeout_seconds']==300)
            common = ('rtl_and_common_contract','confirmed_obligations','current_assertions',
                      'output_schema','temporal_semantics','ordinary_observations')
            check(f'{seed} common fields identical', all(bodies[a][k]==bodies['A'][k] for a in q.ARMS for k in common))
            check(f'{seed} first AC and BD match', bodies['A']==bodies['C'] and bodies['B']==bodies['D'])
            for case in read(ready/'search_cases.json'):
                check(f'{seed} treatment absent ordinary', all(case['id'] not in json.dumps(bodies[a]) for a in ('A','C')))
                check(f'{seed} treatment present search', all(case['id'] in json.dumps(bodies[a]['actual_observations']) for a in ('B','D')))
            # Replay the meaning from existing logs, not new simulation or model calls.
            binding = read(ready/'search/baseline_binding.json')
            for field, cases_name in (('common','common_cases.json'),('target','search_cases.json')):
                loc = b.gate.portable(binding[field]).parent
                native_count += raw.raw_replay(loc, read(ready/cases_name), initial, names)
                native = read(loc/'result.json')
                check(f'{seed} {field} qualified real misses', native['healthy'] and native['counts']['misses']>0 and
                      not native['counts']['false_positives'] and not native['counts']['unknown'])
    binding = read(q.P/'history_binding.json'); path = b.gate.portable(binding['path'])
    check('105 history bound by hash', b.search.digest(path)==binding['sha256'] and len(read(q.P/'history_cases.json'))==105)
    historic = read(path)
    check('history baseline actual native result qualified', historic['healthy'] and all(
        historic['counts'][k]==0 for k in ('misses','false_positives','unknown')))
    with b.extension.installed():
        native_count += raw.raw_replay(path.parent, read(q.P/'history_cases.json'), initial, names)

    # Real feedback construction on already-exposed development data only.
    for seed in b.SEEDS:
        ready = q.P/'ready'/f's{seed}'
        for name, arm in q.ARMS.items():
            small = b.campaign.baseline(ready, 'search' if arm['search'] else 'ordinary')
            call = dict(status='local_preflight_not_a_model_call')
            decision = dict(accepted=False, reasons=[dict(kind='preflight_visible_miss')], use_gate=arm['gate'])
            diagnostic = q.feedback_for(small, historic if arm['gate'] else None, decision, call, None, None, arm['gate'])
            request = b.campaign.request_from(read(prep/f's{seed}'/name/'request.preview.json'), initial, seed, diagnostic)
            body = json.loads(request['messages'][1]['content'])
            check(f'{seed}/{name} real feedback history isolation',
                  ('historical_replay' in body['actual_previous_attempt'])==arm['gate'])
            check(f'{seed}/{name} feedback binds only previous diagnostics', body['actual_previous_attempt']==diagnostic)
            for case in read(ready/'search_cases.json'):
                check(f'{seed}/{name} next request treatment isolation', arm['search'] or case['id'] not in json.dumps(body))
    try:
        q.feedback_for(None, historic, dict(use_gate=False), {}, None, None, False)
    except AssertionError: check('history cannot enter ordinary feedback', True)
    else: check('history cannot enter ordinary feedback', False)

    # State machine fixtures have no service and no simulator. Their fake
    # properties deliberately are NOT valid SVA or research observations.
    def exercise(label, name, sequence, transport=False):
        dest = out/'controller_fixtures'/label; captured=[]; replays=[]; models=[]
        budget = dict(reserved=0, per_arm={}, path=dest/'budget.json')
        class FakeModel:
            def __init__(self, folder, config, request):
                self.calls=[]; self.request=copy.deepcopy(request); self.config=config
            def call(self, folder, current, *args):
                i=len(self.calls); rule=sequence[i]
                captured.append(dict(request=copy.deepcopy(self.request), current=copy.deepcopy(current)))
                result=dict(status='transport_timeout' if transport else 'response_received',
                            fixture=True, candidate_status='fixture_not_real_model')
                self.calls.append(result)
                proposal=None
                if rule.get('candidate', True):
                    proposal=copy.deepcopy(initial)
                    proposal['assertions'][0]['property']='CONTROLLER_FIXTURE_NOT_EXECUTABLE_'+str(rule['identity'])
                    proposal['fixture_rule']=rule
                    dump(folder/'model_edit.json', dict(operation='replace_one', assertion_id='a4', assertions=[],
                        reason='Controller-only fixture, not actual generated SVA.'))
                return result,proposal
        def replay(candidate, folder, cases):
            replays.append(str(folder)); rule=candidate['fixture_rule']
            return dict(healthy=True, group=dict(ledger=[dict(history_ok=rule.get('history',True))]),
                        counts=dict(fixture=True), plain=rule.get('plain',True))
        def gate(before, after):
            okay=after[0]['history_ok']
            return dict(accepted=okay, reasons=[] if okay else [dict(kind='fixture_history_loss')])
        def feedback(small, full, decision, call, edit, previous, use_gate):
            assert use_gate or full is None
            return dict(own_fixture_diagnostic=True, historical_replay=bool(full))
        with patch.object(b.loop,'replay',replay), patch.object(b.campaign,'baseline',return_value={}), \
             patch.object(b.paired,'current_decision',side_effect=lambda before,after,edit:dict(
                 accepted=after['plain'],reasons=[] if after['plain'] else [dict(kind='fixture_target_failure')])), \
             patch.object(b.gate,'decide',gate), patch.object(q,'feedback_for',feedback), \
             patch.object(b.loop.model.native,'candidate_sva',return_value='// Controller fixture only; no executable SVA.\n'):
            try:
                current,result=q.run_arm(prep,dest,6711,name,budget,models,model_type=FakeModel)
            except q.paired.TransportStop:
                check(label+' transport stops after first call',transport and budget['reserved']==1 and len(models[0].calls)==1)
                check(label+' no incomplete arm freeze',not (dest/'core/freeze.json').exists())
                return None
        check(label+' calls match bounded iterations',len(captured)==result['calls']<=2 and budget['reserved']==len(captured))
        check(label+' no implicit cross-arm proposal',all(c['current']==initial for c in captured))
        check(label+' durable freeze matches active',read(dest/'core/frozen_candidate.json')==current)
        for i,d in enumerate(result['rounds']):
            if not d['accepted']:
                check(label+f' rejected v{i} retains baseline',read(dest/'core'/f'v{i}'/'active_candidate.json')==initial)
        return result,captured,replays
    result,requests,replays=exercise('ordinary_accept_stops','A',[dict(identity=1)])
    check('ordinary independent call stops at acceptance',result['accepted'] and result['calls']==1 and len(replays)==1)
    result,requests,replays=exercise('history_reject_then_repair','C',[
        dict(identity=1,history=False),dict(identity=2,history=True)])
    check('history rejection then own repair recorded',result['accepted'] and result['history_rejection_followed_by_acceptance'])
    second=json.loads(requests[1]['request']['messages'][1]['content'])
    check('rejection diagnostic enters own second call',second['actual_previous_attempt']['historical_replay'])
    result,requests,replays=exercise('repeat_is_rejected','B',[
        dict(identity=1,plain=False),dict(identity=1,plain=False)])
    check('repeated executable rejected without second native execution',not result['accepted'] and len(replays)==1 and result['rounds'][1]['repeated_executable'])
    result,requests,replays=exercise('invalid_interface_retains_baseline','D',[
        dict(candidate=False),dict(candidate=False)])
    check('invalid model interface never reaches native replay',not result['accepted'] and not replays)
    exercise('transport_terminal','A',[dict(candidate=False)],True)
    state={k:dict(frozen_hash='fixture') for k in q.KEYS};q.paired.barrier(state)
    for key in q.KEYS:
        incomplete=copy.deepcopy(state);del incomplete[key]
        try:q.paired.barrier(incomplete)
        except AssertionError:check('test barrier rejects missing '+key,True)
        else:check('test barrier rejects missing '+key,False)
    budget=dict(reserved=23,per_arm={'s6733/D':1},path=out/'budget_fixture.json')
    q.reserve(budget,'s6733/D',1)
    check('24th reserved call allowed',budget['reserved']==24)
    for arm,i in [('other',0),('s6733/D',2)]:
        try:q.reserve(budget,arm,i)
        except AssertionError:check('no budget overflow '+arm,True)
        else:check('no budget overflow '+arm,False)
    budget=dict(reserved=0,per_arm={},path=out/'budget_fixture2.json')
    q.reserve(budget,'arm',0)
    try:q.reserve(budget,'arm',0)
    except AssertionError:check('no resend same arm round',True)
    else:check('no resend same arm round',False)
    return dict(passed=True, checks=names, native_records_recomputed=native_count,
                real_model_calls=0, new_native_calls=0, credentials_read=False,
                fixtures_not_experiments=True, policy_effect_evaluated=False)
