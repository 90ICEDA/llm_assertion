"""Fixed full-set versus atomic-edit pilot; same model and native acceptance."""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import research107_atomic_edits as rep

r=rep.previous;p,x=r.p,r.x
ROOT,read,dump,sha=r.ROOT,r.read,r.dump,r.sha
SOURCE=ROOT/'deliverables/research104_prepare_20261025_r01'
ARMS=('C','E')


def protected_failures():
    paths=[]
    for name in ('research100_real_20261025_r01','research104_real_20261025_r01'):
        root=ROOT/'deliverables'/name
        paths+=[root/n for n in ('authorization.json','outcome.json','cost.json','budget_ledger.json')]
        for folder in list(root.glob('v*/model_call'))+list(root.glob('*/v*/model_call')):
            paths.extend(f for f in folder.iterdir() if f.is_file())
    return {f.relative_to(ROOT).as_posix():sha(f) for f in paths}


def prepare(out):
    r.verify(SOURCE);out.mkdir(parents=True,exist_ok=False)
    for n in ('initial.json','proposal.json','baseline_full.json','source_binding.json','history_cases.json','search_cases.json','excluded_words.json','protected93.json'):
        shutil.copy2(SOURCE/n,out/n)
    for rev in ('before','after'):shutil.copytree(SOURCE/rev,out/rev)
    current=read(out/'proposal.json');rec=r.records(r.VERSION/'native')
    for arm in ARMS:dump(out/arm/'request.preview.json',rep.request(current,rec,r.VERSION/'native',arm,0))
    dump(out/'protected_failures.json',protected_failures())
    protocol=dict(name='research108_atomic_edit_representation_pilot',selection='Previously observed research100 T candidate. New sealed single-seed public-generation pilot; research100/104 failures are preserved.',
        variable='Only output representation: C complete OP set; E model-selected keep/remove/replace/add on that set. Same model, shared task/background/development facts and initial candidate. E can express the same1..3 OP sets as C; no model action selected or repaired locally.',
        interpretation='Public generation capability only. Not contract-search or preservation mechanism benefit, not separate action success rate, not new historical task population.',
        information='Initial temporal facts byte-identical. Each continuation sees only its own actual allowed developer diagnostics. Same actual native acceptance and per-arm budget. BRANCH immutable.',
        acceptance='Unchanged current9 + history115 + search36; all420 OP and270 BRANCH, required first/held triggers, zero legal false alarms, misses or critical unknown; all-property preservation guard.',
        maximum_calls=4,maximum_calls_per_arm=2,seeds=[10807,10808],temperature=0.2,output_token_cap=1024,
        maximum_reserved_tokens_per_call=45000,total_token_budget=180000,timeout_seconds=300,max_wall_seconds=2400,
        endpoint=p.prior.transport.DEFAULT_URL,model=p.prior.transport.DEFAULT_MODEL,retries=0,
        order=['C0','E0','C1_if_rejected','E1_if_rejected'],
        stopping='Accepting arm stops; transport failure globally stops; no retries, extra single-field loops, transferred quota, new seed or automatic expansion.',
        terminal='After all arms terminal, if any accepted and no transport failure, freeze both and generate96 fresh words/four configs. Tests never select or refine proposals.',
        adoption_gate='E must produce full native accepted version AND pass new independent test. Otherwise stop alternative route. Even a pass only permits a later separately sealed/authorized mechanism experiment, never automatic expansion.',
        native_budget=dict(maximum_compile_execute_each=28,new_preparation_native=0),created=time.time())
    dump(out/'protocol.json',protocol)
    dump(out/'model_config.json',dict(remote_url=protocol['endpoint'],remote_model=protocol['model'],max_model_calls=4,max_tokens=180000,
        max_wall_seconds=2400,call_timeout=300,options=dict(seed=10807,temperature=0.2,num_predict=1024)))
    dump(out/'reused_bindings.json',{SOURCE.relative_to(ROOT).as_posix()+'/sealed.json':sha(SOURCE/'sealed.json')})
    dump(out/'code_versions.json',{f.relative_to(ROOT).as_posix():sha(f) for f in (ROOT/'scripts').glob('*.py')})
    paths=list(out.glob('*.json'))+list(out.glob('*/*.json'))+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in paths})
    print('PREPARED108 C/E max4 calls; remote0',flush=True)


def verify(prep):
    x.verify(prep);r.verify(SOURCE)
    for n,h in read(prep/'reused_bindings.json').items():assert sha(ROOT/n)==h
    assert protected_failures()==read(prep/'protected_failures.json')


def grant_check(g,prep,out):
    assert g['purpose']=='research108_representation_pilot' and type(g['authorized_calls']) is int and g['authorized_calls']==4
    assert g['endpoint']==p.prior.transport.DEFAULT_URL and g['model']==p.prior.transport.DEFAULT_MODEL
    assert g['prepared_sha256']==sha(prep/'sealed.json') and g['run_output']==out.relative_to(ROOT).as_posix()


class Model(p.Model):
    def save_decoded_output(self,folder,value,current,secret):
        if self.arm=='C':return super().save_decoded_output(folder,value,current,secret)
        candidate,mapping=rep.adapt(value,current,self.fixed)
        dump(folder/'candidate.json',candidate);dump(folder/'edit_mapping.json',mapping)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
        return candidate,'model_selected_atomic_edits_no_predicate_repair'


def run(prep,out,authorization):
    verify(prep);g=read(authorization);grant_check(g,prep,out)
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',g);dump(out/'protocol.json',read(prep/'protocol.json'))
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');base=read(prep/'baseline_full.json')
    active={a:initial for a in ARMS};current={a:proposal for a in ARMS};rec={a:r.records(r.VERSION/'native') for a in ARMS}
    native={a:r.VERSION/'native' for a in ARMS};diag={a:None for a in ARMS}
    seen={a:{x.signature(initial),x.signature(proposal)} for a in ARMS};states={a:dict(calls=0,accepted=False) for a in ARMS}
    model=Model(out/'service',read(prep/'model_config.json'));model.fixed=initial
    budget=[];stopped=False;tests=None
    try:
        for i in range(2):
            for arm in ARMS:
                if stopped or states[arm]['accepted']:continue
                req=rep.request(current[arm],rec[arm],native[arm],arm,i,diag[arm])
                if i==0:assert req==read(prep/arm/'request.preview.json')
                reservation=sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']
                assert reservation<=45000 and len(budget)<4 and states[arm]['calls']<2
                budget.append(dict(arm=arm,iteration=i,reserved_at=time.time(),reservation=reservation,request_sha256=x.old.acceptance.sha(req)))
                dump(out/'budget_ledger.json',budget);model.pending_request=req;model.arm=arm;folder=out/arm/f'v{i}'
                call,candidate=model.call(folder/'model_call',current[arm],'op_bit28_illegal',{},'representation')
                states[arm]['calls']+=1;ev=None;accepted=False;reason=dict(kind='transport_or_interface',actual=call)
                if candidate is not None:
                    if x.signature(candidate) in seen[arm]:reason=dict(kind='repeated_executable_proposal');candidate=None
                    else:
                        seen[arm].add(x.signature(candidate));ev,newrec=x.evaluate(candidate,folder/'native',base)
                        accepted=bool(ev['history']['accepted']);reason=dict(kind='native_measured',decision=ev)
                        current[arm]=candidate;rec[arm]=newrec;native[arm]=folder/'native'
                diag[arm]=None if ev else dict(reason=reason,actual_model_text=read(folder/'model_call/response.assembled.json')['message']['content'])
                active[arm]=x.journal(folder/'transition',active[arm],candidate,accepted,reason)
                states[arm]['accepted']=accepted;dump(out/'states.json',states)
                stopped=call['status']!='response_received';print('REPRESENTATION108',arm,i,reason['kind'],accepted,flush=True)
            if stopped:break
        for a,c in active.items():dump(out/'terminal'/a/'candidate.json',c)
        dump(out/'terminal_versions.json',{a:x.old.acceptance.sha(c) for a,c in active.items()})
        if not stopped and any(s['accepted'] for s in states.values()):
            p.prior.p.independent(prep,out,active);tests=read(out/'independent_summary.json')
        eligible=bool(not stopped and states['E']['accepted'] and tests and tests['E']['passed'])
        dump(out/'pilot_decision.json',dict(alternative_passed=eligible,automatic_expansion=False,
            status='qualified_for_later_sealed_experiment' if eligible else 'stop_alternative_route'))
    finally:
        dump(out/'cost.json',x.costs.native_cost(out));dump(out/'states.json',states)
        dump(out/'outcome.json',dict(actual_calls=len(model.calls),states=states,transport_stopped=stopped,
            unique_new_accepted_versions=len({x.old.acceptance.sha(active[a]) for a in ARMS if states[a]['accepted']}),
            independent={a:v['passed'] for a,v in tests.items()} if tests else None,automatic_expansion=False))
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--prepared',type=Path);ap.add_argument('--authorization',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
