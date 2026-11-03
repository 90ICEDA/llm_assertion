"""Durable, fail-closed pilot budgets. Local tests are not model experiments."""
import json
import os
import time
from pathlib import Path

ARMS=('A','B','C','D')
CAPS={'windows':5,'public':14,'history':105,'independent':56}


class BudgetError(RuntimeError):pass


class Budget:
    def __init__(self,path,model,seed=7907):
        self.path=Path(path);self.model=model;self.seed=seed
        if self.path.exists():raise BudgetError('resume_not_allowed')
        self.state=dict(maximum=8,seed=seed,stopped=False,stop_reason=None,events=[],
            arms={a:dict(calls=[],plan_passed=False,native_passed=False,frozen=False,terminal=False,phases=[]) for a in ARMS})
        self.save()

    def save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.pending')
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(self.state,f,indent=2);f.flush();os.fsync(f.fileno())
        tmp.replace(self.path)

    def require(self,condition,reason):
        if not condition:raise BudgetError(reason)

    def event(self,kind,arm,**data):
        self.state['events'].append(dict(kind=kind,arm=arm,at=time.time(),**data));self.save()

    def reserve(self,arm,stage,request,request_hash):
        self.require(arm in ARMS and stage in ('plan','sva'),'invalid_arm_or_stage')
        s=self.state['arms'][arm]
        self.require(not self.state['stopped'] and not s['terminal'] and not s['frozen'],'closed')
        self.require(stage not in s['calls'],'no_retry_or_transferred_slot')
        self.require(sum(len(x['calls']) for x in self.state['arms'].values())<8,'total_cap')
        self.require(stage=='plan' or s['plan_passed'] is True,'plan_required_before_sva')
        self.require(request.get('model')==self.model and request.get('seed')==self.seed,'model_seed_changed')
        self.require(request.get('max_tokens')==2048,'output_cap_changed')
        size=sum(len(m['content']) for m in request['messages'])
        self.require(size<=64000,'input_character_cap')
        s['calls'].append(stage)
        self.event('model_reserved',arm,stage=stage,request_sha256=request_hash,characters=size)

    def plan(self,arm,accepted):
        s=self.state['arms'][arm]
        self.require(s['calls']==['plan'] and not s['terminal'] and not s['plan_passed'],'invalid_plan_transition')
        s['plan_passed']=accepted is True
        if accepted is not True:s['terminal']=True
        self.event('plan_result',arm,accepted=s['plan_passed'])

    def native(self,arm,phase,count):
        s=self.state['arms'][arm]
        self.require(not self.state['stopped'],'globally_stopped')
        self.require(phase in CAPS and count==CAPS[phase],'native_case_cap_or_inventory')
        self.require(phase not in s['phases'],'native_phase_not_repeatable')
        if phase=='independent':
            self.require(all(x['frozen'] for x in self.state['arms'].values()),'all_arms_must_freeze')
            self.require(all(x['terminal'] for x in self.state['arms'].values()),'all_arms_must_finish')
            self.require(any(x['native_passed'] for x in self.state['arms'].values()),'accepted_pilot_required')
        else:
            self.require(s['calls']==['plan','sva'] and not s['terminal'],'sva_required_before_native')
            if phase=='public':self.require('windows_passed' in s,'window_gate_required')
            if phase=='history':self.require('public_passed' in s,'public_gate_required')
        s['phases'].append(phase);self.event('native_reserved',arm,phase=phase,cases=count)

    def phase_pass(self,arm,phase):
        s=self.state['arms'][arm];self.require(phase in s['phases'],'phase_not_run')
        self.require(phase in ('windows','public'),'invalid_stage_gate')
        s[phase+'_passed']=True;self.event('phase_pass',arm,phase=phase)

    def finish(self,arm,accepted):
        s=self.state['arms'][arm]
        self.require(not s['frozen'],'already_frozen')
        if accepted is True:self.require('history' in s['phases'] and s['plan_passed'] is True,'full_history_required')
        s['native_passed']=accepted is True;s['terminal']=True
        self.event('arm_terminal',arm,accepted=s['native_passed'])

    def freeze(self,arm,candidate_hash):
        s=self.state['arms'][arm]
        self.require(s['terminal'] and not s['frozen'],'terminal_once_before_freeze')
        s['frozen']=True;self.event('freeze',arm,candidate_hash=candidate_hash)

    def stop(self,reason):
        self.state['stopped']=True;self.state['stop_reason']=reason
        self.event('global_stop',None,reason=reason)


def tests(folder):
    folder=Path(folder);checks=[];index=0
    request=dict(model='local-test-fixture',seed=7907,max_tokens=2048,messages=[dict(content='local fixture only')])
    def new():
        nonlocal index
        index+=1;return Budget(folder/f'fixture_{index}.json',request['model'])
    def rejects(name,fn):
        try:fn()
        except BudgetError:checks.append(name)
        else:raise AssertionError(name)
    x=new();rejects('SVA without plan blocked',lambda:x.reserve('A','sva',request,'fixture'))
    x.reserve('A','plan',request,'fixture');rejects('plan retransmission blocked',lambda:x.reserve('A','plan',request,'fixture'))
    x.plan('A',False);rejects('failed plan cannot generate',lambda:x.reserve('A','sva',request,'fixture'))
    for value in (None,'unknown',1):
        x=new();x.reserve('A','plan',request,'fixture');x.plan('A',value)
        rejects('nonboolean pass cannot unlock '+str(value),lambda:x.reserve('A','sva',request,'fixture'))
    for key,value in [('seed',7919),('model','other'),('max_tokens',4096)]:
        x=new();q=dict(request);q[key]=value
        rejects('changed '+key,lambda:x.reserve('A','plan',q,'fixture'))
    x=new();q=dict(request);q['messages']=[dict(content='x'*64001)]
    rejects('oversized request blocked',lambda:x.reserve('A','plan',q,'fixture'))
    x=new();x.reserve('A','plan',request,'fixture');x.stop('local_transport_fixture')
    rejects('transport blocks other arm',lambda:x.reserve('B','plan',request,'fixture'))
    rejects('cannot resume run ledger',lambda:Budget(x.path,request['model']))
    x=new();x.reserve('A','plan',request,'fixture');x.plan('A',True);x.reserve('A','sva',request,'fixture')
    rejects('SVA retry blocked',lambda:x.reserve('A','sva',request,'fixture'))
    rejects('history before public blocked',lambda:x.native('A','history',105))
    rejects('public before windows blocked',lambda:x.native('A','public',14))
    rejects('wrong case budget blocked',lambda:x.native('A','windows',6))
    rejects('accept before history blocked',lambda:x.finish('A',True))
    x.native('A','windows',5);x.phase_pass('A','windows');x.native('A','public',14);x.phase_pass('A','public');x.native('A','history',105)
    rejects('native history repeat blocked',lambda:x.native('A','history',105))
    x.finish('A',True);x.freeze('A','fixture_hash')
    rejects('test before all freezes blocked',lambda:x.native('A','independent',56))
    for a in ('B','C','D'):x.finish(a,False);x.freeze(a,'fixture_baseline')
    x.native('A','independent',56);checks.append('independent after all frozen and accepted')
    rejects('independent repeat blocked',lambda:x.native('A','independent',56))
    rejects('no calls after freeze',lambda:x.reserve('B','plan',request,'fixture'))
    x=new()
    for a in ARMS:x.finish(a,False);x.freeze(a,'fixture_baseline')
    rejects('no independent when no accepted candidate',lambda:x.native('A','independent',56))
    x=new()
    for a in ARMS:x.reserve(a,'plan',request,'fixture');x.plan(a,True);x.reserve(a,'sva',request,'fixture')
    assert sum(len(s['calls']) for s in x.state['arms'].values())==8
    checks.append('all eight slots bounded and reserved durably')
    rejects('ninth call blocked',lambda:x.reserve('A','plan',request,'fixture'))
    return dict(passed=True,checks=checks,fixture_only=True,real_model_calls=0,real_native_calls=0)
