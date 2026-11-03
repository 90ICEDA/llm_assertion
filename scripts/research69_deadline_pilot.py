"""One explicitly approved remaining-slot diagnostic, bounded at300 seconds.

Requires a new purpose-transfer record: research68 transport timeout terminated
its protocol. No automatic retry, no model/schema/evidence changes.
"""
import argparse
import json
from pathlib import Path
import time
import research68_service_pilot as prior
import research69_deadline_transport as transport

ROOT,read,dump=prior.ROOT,prior.read,prior.dump
P68=ROOT/'deliverables/research68_prepare_20261024_r01'
R68=ROOT/'deliverables/research68_pilot_20261024_r01'


class Model(prior.Model):
    def call(self,folder,*args,**kwargs):
        with prior.capture(folder):return transport.RemoteModel.call(self,folder,*args,**kwargs)


def prepare(out):
    prior.verify(P68);out.mkdir(parents=True,exist_ok=False)
    assert read(R68/'outcome.json')['actual_new_calls']==1
    assert read(R68/'outcome.json')['status']=='terminal_transport_timeout'
    origin=(ROOT/'scripts/research20_remote.py').read_text(encoding='utf-8-sig')
    changed=(ROOT/'scripts/research69_deadline_transport.py').read_text(encoding='utf-8-sig')
    assert changed==origin.replace("timeout = min(180, self.config.get('call_timeout', 180), remaining)",
                                  "timeout = min(300, self.config.get('call_timeout', 300), remaining)")
    config=read(P68/'model_config.json');config['max_model_calls']=1
    config['max_tokens']-=read(R68/'core/v0/model_call/transport_result.json')['token_budget_reservation']
    config['call_timeout']=300
    dump(out/'model_config.json',config)
    for name in ('ordinary','search'):dump(out/name/'request.preview.json',read(P68/name/'request.preview.json'))
    dump(out/'protocol.json',dict(action='single_extended_deadline_service_diagnostic_and_pilot',
        maximum_calls=1,previous_actual_pilot_calls=2,total_authorized_pilot_slots=3,timeout_seconds=300,
        retries=0,only_transport_source_change='180 to300 seconds; verified exact source comparison',
        messages_changed=False,model_or_seed_changed=False,
        requires_explicit_transfer=True,reason='Previous protocol stopped on timeout; never silently retry it.',
        acceptance='Same current targets/required trigger and105 history; freeze and fresh independent only after full acceptance.',
        independent_tests_not_sent=True,model_catalog=read(ROOT/'deliverables/research68_service_metadata_20261024_r01/result.json'),
        prepared_at=time.time()))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():prior.base.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json',{p.relative_to(out).as_posix():prior.base.search.digest(p) for p in out.rglob('*.json')})
    print('PREPARED remaining1; same request; only deadline180to300; no call',flush=True)


def verify(prep):
    prior.verify(P68)
    for p,h in read(prep/'sealed.json').items():assert prior.base.search.digest(prep/p)==h,p
    for p,h in read(prep/'code_versions.json').items():assert prior.base.search.digest(ROOT/p)==h,p


def run(prep,out,auth):
    verify(prep);grant=read(auth)
    assert grant['authorized_calls']==1 and grant['purpose']=='research69_deadline_transfer'
    assert grant['protocol_sha256']==prior.base.search.digest(prep/'protocol.json')
    assert grant['run_output']==out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',grant)
    b=prior.base;initial=read(prior.PREP/'shared_initial.json');current=initial
    request=read(prep/'search/request.preview.json');model=Model(out/'model',read(prep/'model_config.json'),request)
    cases=read(prior.PREP/'search/cases.json');history=read(prior.PREP/'history_cases.json')
    before=b.campaign.baseline(prior.PREP,'search');binding=read(prior.PREP/'history_binding.json')
    hp=b.gate.portable(binding['path']);assert b.search.digest(hp)==binding['sha256'];historic=read(hp)
    status='running';accepted=False;passed=False
    try:
        with b.extension.installed():
            folder=out/'core/v0'
            call,proposal=model.call(folder/'model_call',current,'stall_stability',{},'single300s_service_diagnostic')
            if call['status']!='response_received':status='terminal_'+call['status'];return
            edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
            small=b.loop.replay(proposal,folder/'target_native',cases) if proposal else None
            plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=[dict(kind='interface_failure')])
            dump(folder/'target_gate.json',plain)
            full=b.loop.replay(proposal,folder/'history_native',history) if plain['accepted'] else None
            hg=b.gate.decide(historic['group']['ledger'],full['group']['ledger']) if full and full.get('group') else dict(accepted=False,reasons=[])
            accepted=bool(plain['accepted'] and full and full['healthy'] and hg['accepted'])
            reasons=plain['reasons']+hg['reasons']
            if full and not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
            decision=dict(accepted=accepted,reasons=reasons,ordinary_accepted=plain['accepted'],history=hg,call=call)
            dump(folder/'decision.json',decision);current=b.journal(folder,current,proposal,decision)
            print('TARGET',plain['accepted'],'HISTORY',accepted,flush=True)
            if not accepted:status='refinement_unresolved';return
            b.loop.freeze(out/'core',current,'accepted_before_new_independent_generation')
            excluded,sources=prior.previous.exclusions(prior.ORIGIN)
            development=history+read(prior.PREP/'common_cases.json')+read(prior.PREP/'search_cases.json')
            dump(out/'exclusion_manifest.json',dict(input_hashes=sorted(excluded|{b.loop.sha(c['rows']) for c in development}),sources=sources))
            b.holdout(out,current,development,excluded)
            passed=read(out/'independent/summary.json')['all_five_pass_on_first_attributed_evidence']
            status='pilot_passed' if passed else 'independent_failed_no_multiseed'
    except BaseException as exc:
        status='execution_exception';dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)));raise
    finally:
        verify(prep)
        dump(out/'outcome.json',dict(status=status,accepted=accepted,pilot_passed=passed,actual_new_calls=len(model.calls),
            prior_calls=2,total_pilot_cap=3,multiseed_started=False,research63_unchanged=b.protected()==read(prior.ORIGIN/'protected_research63.json')))
        dump(out/'cost.json',b.search.native_cost(out));print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
