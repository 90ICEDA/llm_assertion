"""Local-only continuation of the sealed three-seed protocol after pilot audit.

Never calls a model or reads its credential. Old pilot results are preserved.
The external pilot verdict is bound by content hash, not rerun or synthesized.
"""
import argparse
import json
from pathlib import Path
import time
import research69_deadline_pilot as pilot
import research67_preflight as preflight

b=pilot.prior.base
ROOT,read,dump=b.ROOT,b.read,b.dump
RUN=ROOT/'deliverables/research69_pilot_20261024_r01'
AUDIT=ROOT/'deliverables/research69_audit_20261024_r01'


def seal(out):
    assert not out.exists(),'Use a new continuation directory; preserve all old results.'
    verdict=read(RUN/'outcome.json')
    assert verdict['accepted'] and verdict['pilot_passed']
    assert read(AUDIT/'audit.json')['passed'] and read(AUDIT/'additional_audit.json')['passed']
    pilot.verify(ROOT/'deliverables/research69_prepare_20261024_r01')
    b.seal(out)
    paths=[RUN/'outcome.json',RUN/'core/freeze.json',RUN/'independent/summary.json',
           AUDIT/'audit.json',AUDIT/'additional_audit.json']
    binding=dict(source=str(RUN),sha256={str(p):b.search.digest(p) for p in paths},
                 scope='Actual external pilot acceptance and independent verdict only; no candidate or test values supplied to arms.')
    dump(out/'pilot_binding.json',binding)
    # Adapter to the existing search runner's explicit pilot prerequisite.
    # This is a reference to the real external pilot, never a new run result.
    dump(out/'pilot_run/outcome.json',dict(pilot_passed=True,
        status='external_completed_pilot_reference',actual_new_calls=0,binding=binding))
    dump(out/'continuation_protocol.json',dict(at=time.time(),seeds=list(b.SEEDS),
        original_protocol=b.search.digest(pilot.prior.ORIGIN/'protocol.json'),
        public_helpers='Same research44 AST, component restriction, native gates, compact public projection in all arms.',
        transport='Same Qwen72B, temperature0.2, max output2048, timeout300, retries0; any transport failure stops.',
        paired='6 physical proposals; A/C and B/D share proposal. Decision effect only.',
        independent_policy='Separate calls, 3 seeds x4 arms x at most2 calls =24 cap. Policy effect, not paired single-round effect.',
        model_authorization=False,model_calls=0,
        tests='All versions in each comparison freeze before fresh common tests; pilot test values excluded from feedback.',
        failed_qualification='Retain missing-witness seeds, do not replace seeds or fabricate treatment.'))
    dump(out/'continuation_seal.json',{p.relative_to(out).as_posix():b.search.digest(p)
        for p in (out/'pilot_binding.json',out/'pilot_run/outcome.json',out/'continuation_protocol.json')})
    print('SEALED continuation; no model calls',flush=True)


def verify(out):
    b.verify(out)
    for rel,h in read(out/'continuation_seal.json').items():assert b.search.digest(out/rel)==h
    for path,h in read(out/'pilot_binding.json')['sha256'].items():assert b.search.digest(Path(path))==h


def search(out,seed):
    verify(out)
    b.run_search(out,seed)


def qualify(out,seed):
    verify(out)
    preflight.qualify(out,seed)
    source=out/'prepared_v4'/f's{seed}'
    if not read(source/'qualification.json')['passed']:
        print('UNQUALIFIED',seed,flush=True);return
    dest=out/'ready'/f's{seed}'
    dest.mkdir(parents=True,exist_ok=False)
    for name in ('shared_initial.json','history_cases.json','history_binding.json',
                 'common_cases.json','search_cases.json','selected.json','qualification.json'):
        dump(dest/name,read(source/name))
    bodies={}
    for stream in ('ordinary','search'):
        original=read(source/stream/'request.preview.json')
        request=pilot.prior.compact(original)
        a=json.loads(original['messages'][1]['content'])
        c=json.loads(request['messages'][1]['content'])
        assert all(a[k]==c[k] for k in a if k!='ordinary_observations')
        dump(dest/stream/'request.preview.json',request);bodies[stream]=c
        for name in ('cases.json','baseline_binding.json'):dump(dest/stream/name,read(source/stream/name))
    public=('rtl_and_common_contract','confirmed_obligations','current_assertions',
            'output_schema','temporal_semantics','ordinary_observations')
    assert all(bodies['ordinary'][k]==bodies['search'][k] for k in public)
    cases=read(dest/'search_cases.json')
    assert all(c['id'] not in json.dumps(bodies['ordinary']) for c in cases)
    assert all(c['id'] in json.dumps(bodies['search']['actual_observations']) for c in cases)
    settings=b.campaign.settings(seed,2);settings['call_timeout']=300
    dump(dest/'model_config.json',settings)
    dump(dest/'isolation.json',dict(passed=True,public_fields=list(public),search_witnesses_isolated=True,
        paired_identical_requests='A=C ordinary, B=D search; one shared proposal per pair',
        policy_identical_initial_requests='A=C ordinary, B=D search; independent physical responses',
        model_calls=0,pilot_success_candidate_or_test_in_request=False))
    dump(dest/'sealed.json',{p.relative_to(dest).as_posix():b.search.digest(p) for p in dest.rglob('*.json')})
    print('READY',seed,'two sealed compact requests; no model calls',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('seal','search','qualify'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,choices=b.SEEDS)
    a=p.parse_args();root=a.out.resolve()
    if a.action=='seal':seal(root)
    elif a.action=='search':search(root,a.seed)
    else:qualify(root,a.seed)
