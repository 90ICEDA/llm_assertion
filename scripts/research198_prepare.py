"""Prepare a fixed-development-evidence paired automatic-controller experiment."""
import argparse
import ast
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash,ENDPOINT
from research194_refinement import digest
from research198_refinement import runtime
import research197_cases as cases


def sources(previous):
    bindings=dict(previous['source_bindings'])
    pending=list((ROOT/'scripts').glob('research198_*.py'))
    while pending:
        path=pending.pop().resolve();name=str(path)
        if name in bindings:continue
        bindings[name]=file_hash(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else []
            for m in modules:
                if m and m.startswith('research') and path.with_name(m+'.py').is_file():pending.append(path.with_name(m+'.py'))
    return bindings


def prepare(out,qualification):
    out=Path(out).resolve();qualification=Path(qualification).resolve()
    if read(qualification/'outcome.json')['status']!='qualified':raise ValueError('native_qualification_required')
    previous=ROOT/'deliverables/research197_refinement_prepare_20261104_r01'
    from research197_prepare import verify as old_verify
    p=old_verify(previous)
    out.mkdir(parents=True,exist_ok=False);entries=[]
    for e in p['entries']:
        if e['arm'] is not None or e['strategy']!='R3':continue
        state=read(e['state'])
        for policy in ('feedback','legacy','local_first'):
            strategy='R1' if policy=='feedback' else 'R3'
            identity=f"{e['case_id']}/{e['seed']}/{e['search']}_{policy}"
            core,runner=runtime(policy);adapter=cases.CaseAdapter(e['case_id'])
            prep=runner.prepare_first(adapter,strategy,e['seed'],state['baseline'],state['queries'],state['first_acquisition'],out/'requests'/identity,
                max_rounds=5,current_measurement=state['first_measurement'])
            m=state['first_measurement'];blocked=bool(m['critical_unknown'] or not m['native_complete'] or not m['reference_complete'])
            request=read(prep['request']);import json
            context=json.loads(request['messages'][-1]['content'])
            entries.append(dict(id=identity,case_id=e['case_id'],seed=e['seed'],search=e['search'],strategy=strategy,policy=policy,
                mode='blocked_unknown' if blocked else 'ready',max_rounds=5,source_state=e['state'],source_state_sha256=file_hash(e['state']),
                first_stage='free' if strategy=='R1' else ('local' if 'operations_allowed' in context['output_contract'] or isinstance(context['output_contract'].get('operations'),dict) else 'compose'),**prep))
    protocol=dict(version='research198',endpoint=ENDPOINT,model=p['model'],temperature=.2,max_output_tokens=2048,timeout_seconds=300,workers=2,retries=0,
        maximum_model_calls=sum(e['max_rounds'] for e in entries if e['mode']=='ready'),population=len(entries),entries=entries,
        case_ids=p['case_ids'],seeds=p['seeds'],qualification=str(qualification),source_bindings=sources(p),
        previous_protocol=str(previous/'protocol.json'),previous_protocol_sha256=file_hash(previous/'protocol.json'),
        authorization='NOT AUTHORIZED. Prior grants were for different sealed requests and cannot be reused.',
        experiment='3 parents x 2 seeds x S0/S3 previously acquired development evidence x feedback/legacy/local-first automatic controller; every arm has five-call ceiling.',
        primary_contrasts=['local_first versus legacy at same search evidence','S0/S3 crossed with feedback/local_first: fixed-acquisition 2x2, not online adaptive-search ablation'],
        cost_plan='Report equal three-call and five-call ceilings, common completed-prefix tokens and service-time sections. Historical acquisition is reused, separately reported; no new search cost is fabricated.',
        fallback_plan='Observe honest model choices. Unknown and unchanged/schema-invalid outputs cannot authorize escalation. Do not request deliberately ineffective proposals to manufacture three-stage coverage. Report every unavailable branch separately.',
        external_payload='Previously approved historical before/after RTL and ID Queue RTL, specification, SVA, fixed development observations and real prior-round feedback. Independent inputs, fault definitions and results never sent.',
        acceptance_plan='Freeze all 36 versions, then native-grading original faults and preregistered new fault instances/new input seeds. Historical R197 faults are not claimed as fresh unseen evidence.',
        limits=p['limits']+['Routing and typed-only contract are a bundled new policy; old F/P/T remains the separate edit-permission isolation study.'])
    from research198_independent import register
    register(out,protocol)
    protocol['source_bindings'][str(out/'acceptance_registration.json')]=file_hash(out/'acceptance_registration.json')
    dump(out/'protocol.json',protocol);dump(out/'seal.json',dict(protocol_sha256=file_hash(out/'protocol.json')))
    review=dict(population=len(entries),first_requests=sum(e['mode']=='ready' for e in entries),maximum_model_calls=protocol['maximum_model_calls'],
        model_calls=0,first_request_bytes=sum(Path(e['request']).stat().st_size for e in entries),
        first_stages={policy:{stage:sum(e['policy']==policy and e['first_stage']==stage for e in entries) for stage in ('free','local','compose')} for policy in ('feedback','legacy','local_first')},
        requests=[{k:e[k] for k in ('id','policy','mode','first_stage','request','request_sha256','max_rounds')} for e in entries])
    dump(out/'review.json',review);verify(out);print({k:v for k,v in review.items() if k!='requests'},flush=True)


def verify(out):
    out=Path(out);p=read(out/'protocol.json')
    if p['version']!='research198' or len(p['entries'])!=36 or p['maximum_model_calls']>180:raise ValueError('population')
    if file_hash(out/'protocol.json')!=read(out/'seal.json')['protocol_sha256']:raise ValueError('protocol_changed')
    for path,h in p['source_bindings'].items():
        if file_hash(path)!=h:raise ValueError('source_changed:'+path)
    blocks={}
    for e in p['entries']:
        if file_hash(e['state'])!=e['state_sha256'] or file_hash(e['source_state'])!=e['source_state_sha256']:raise ValueError('state_changed')
        s=read(e['state']);core,r=runtime(e['policy']);a=cases.CaseAdapter(e['case_id'])
        c=r.controller_from(a,e['strategy'],s['baseline'],5);c.consider_empty_domain(s['first_measurement'])
        request=core.build_request(a.case,c,s['public_evidence'],e['seed'],0)
        if request!=read(e['request']) or digest(request)!=e['request_sha256']:raise ValueError('request_reconstruction:'+e['id'])
        key=(e['case_id'],e['seed'],e['search'])
        value=digest({k:s[k] for k in ('initial','baseline','queries','first_measurement','public_evidence')})
        if key in blocks and blocks[key]!=value:raise ValueError('unpaired_initial_information')
        blocks[key]=value
        for path,h in s['first_measurement']['native_bindings'].items():
            if file_hash(path)!=h:raise ValueError('native_binding_changed')
    return p

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify']);p.add_argument('--out',type=Path,required=True);p.add_argument('--qualification',type=Path)
    a=p.parse_args();prepare(a.out,a.qualification) if a.action=='prepare' else print(verify(a.out)['maximum_model_calls'])
