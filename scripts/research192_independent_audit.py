"""Read-only audit of the 16 frozen-arm, 8-distinct-version independent run."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode=True
import research192_independent as run


def normalized(value):
    if isinstance(value,dict):return {str(k):normalized(v) for k,v in value.items()}
    if isinstance(value,list):return sorted((normalized(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value


def audit(out,manifest):
    started=time.perf_counter();checks=[]
    def ck(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system'):
            raise RuntimeError('read_only_audit_no_network_or_execution')
        if event=='open' and isinstance(args[0],(str,bytes)):
            mode=args[1];writing=isinstance(mode,str) and any(c in mode for c in 'wax+')
            if writing and Path(args[0]).resolve()!=out/'audit.json':
                raise RuntimeError('audit_may_only_write_its_own_record')
    sys.addaudithook(guard)
    read,sha,p,s=run.read,run.file_hash,run.p,run.s
    before={name:sha(out/name) for name in ('executions.json','grades.json','measurements.json','results.json',
        'selection.json','selection_seal.json','frozen_bindings.json','arm_versions.json','renamed_properties.json','cost.json','outcome.json','protocol.json')}
    ck('completed run',read(out/'outcome.json')['status']=='completed')
    bindings=read(out/'frozen_bindings.json')
    for name,digest in bindings.items():ck('bound source '+name,sha(run.ROOT/name)==digest)
    seal=read(out/'selection_seal.json')
    ck('original manifest hash',sha(manifest)==seal['manifest'])
    ck('selection hash',sha(out/'selection.json')==seal['selection'])
    ck('frozen bindings hash',sha(out/'frozen_bindings.json')==seal['frozen_bindings'])
    entries=read(out/'arm_versions.json');original=read(manifest);versions=read(out/'renamed_properties.json')
    ck('16 manifest entries and 8 physical versions',len(entries)==len(original)==16 and len(versions)==8)
    expected_entries=copy.deepcopy(original);assignments={};expected_versions={};freeze_times=[]
    for item in expected_entries:
        candidate=p.validate(read(run.ROOT/item['path']));freeze=read(run.ROOT/item['freeze_path'])
        ck('candidate file bound '+item['path'],sha(run.ROOT/item['path'])==item['sha256'])
        ck('freeze file bound '+item['freeze_path'],sha(run.ROOT/item['freeze_path'])==item['freeze_sha256'])
        ck('candidate digest and prefreeze flag '+item['path'],freeze['candidate_sha256']==p.digest(candidate) and freeze['freeze_before_independent'] is True)
        freeze_times.append((run.ROOT/item['freeze_path']).stat().st_mtime_ns)
        sig=p.digest(candidate)
        if sig not in assignments:
            key='v'+str(len(assignments));assignments[sig]=key;renamed=copy.deepcopy(candidate)
            for i,a in enumerate(renamed):a['label']=f'{key}_a{i}'
            expected_versions[key]=p.validate(renamed)
        item['physical_version']=assignments[sig]
    ck('version assignment exact',entries==expected_entries)
    ck('properties unchanged except unique label rename',versions==expected_versions)
    labels=[a['label'] for c in versions.values() for a in c]
    ck('globally unique assertion labels',len(labels)==len(set(labels)))
    scenes=read(out/'selection.json');descriptors=run.test_population()
    ck('fixed 16 descriptors unchanged',[x['descriptor'] for x in scenes]==descriptors and len(scenes)==16)
    selected={tuple(d['semantic_key']) for d in descriptors}
    ck('16 distinct semantic inputs',len(selected)==16)
    blocked=set();exclusion_sources=[]
    for name in ('reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json'):
        path=run.ROOT/'deliverables/research188_drop_binding_prepare_20261102_r01'/name
        blocked.update(tuple(d['semantic_key']) for d in read(path));exclusion_sources.append(str(path.relative_to(run.ROOT)))
    for item in entries:
        if item.get('development_descriptors'):
            path=run.ROOT/item['development_descriptors']
            ck('arm actual development descriptor hash '+item['development_descriptors'],sha(path)==item['development_descriptors_sha256'])
            blocked.update(tuple(d['semantic_key']) for d in read(path));exclusion_sources.append(item['development_descriptors'])
    ck('all reserved and actual development inputs excluded',not(selected&blocked))
    ck('freeze mtime before selection supplemental check',max(freeze_times)<(out/'selection.json').stat().st_mtime_ns)
    for scene in scenes:
        ck('stimulus and semantic identity '+scene['scene_id'],p.scene(scene['descriptor'])==scene['rows'] and p.semantic_key(scene['rows'],scene['depth'])==tuple(scene['descriptor']['semantic_key']))
    jobs=read(out/'executions.json')
    ck('32 jobs unique complete pairs',len(jobs)==32 and len({(j['scene_id'],j['revision']) for j in jobs})==32 and
        {(j['scene_id'],j['revision']) for j in jobs}=={(c['scene_id'],r) for c in scenes for r in ('before','after')})
    marker_count=0
    for job in jobs:
        folder=Path(job['folder']);result=read(folder/'result.json');log=(folder/'execute.log').read_text()
        ck('job equals physical result '+str(folder),result==job['result'])
        ck('completed physical commands '+str(folder),result['compile_status']=='passed' and result['execution_status']=='completed' and
            read(folder/'compile.json')['exit_code']==0 and read(folder/'execute.json')['exit_code']==0 and 'NATIVE_RUN_COMPLETE' in log)
        scene=next(c for c in scenes if c['scene_id']==job['scene_id'])
        ck('shared bench exact '+str(folder),(folder/'tb.sv').read_text()==run.combined_bench(versions,job['depth'],job['policy'],scene['rows']))
        ck('native source hash '+str(folder),sha(folder/'tb.sv')==result['source_sha256'])
        ck('correct original RTL revision '+str(folder),str(p.q.P/'frame_fifo_drop'/job['revision']/'axis_fifo.v') in read(folder/'compile.json')['argv'])
        for field,marker in (('failures','ASSERT_FAIL'),('triggers','TRIGGER')):
            actual={(label,int(cy)) for label,cy in re.findall(r'^'+marker+r' (\S+) cycle=(\d+)',log,re.M)}
            stored={(v['id'],int(v['detail'].strip().removeprefix('cycle='))) for v in result[field]}
            ck('raw native '+field+' '+str(folder),actual==stored and all(label in labels for label,_ in actual));marker_count+=len(actual)
    measurements=read(out/'measurements.json');grades=read(out/'grades.json');summary=[];missing_sets=[]
    for key,candidate in versions.items():
        measured=run.b.bound_measure(candidate,jobs)
        ck('measurement replay '+key,normalized(measured)==normalized(measurements[key]))
        candidate_labels={a['label'] for a in candidate};filtered=copy.deepcopy(jobs)
        for job in filtered:
            for field in ('triggers','failures'):job['result'][field]=[r for r in job['result'][field] if r['id'] in candidate_labels]
        ck('other-version markers cannot change verdict '+key,normalized(p.measure(candidate,jobs))==normalized(p.measure(candidate,filtered)))
        per_scene=[]
        for scene in scenes:
            pair=[j for j in jobs if j['scene_id']==scene['scene_id']];m=run.b.bound_measure(candidate,pair)
            legal=sum(len(r['correct_first_cycles']) for r in m['reference'].values())
            release=all(ev['first']['ready']==int(scene['policy']=='ready_first') and bool(ev['outputs']) for r in m['reference'].values() for ev in r['events'])
            grade=run.scope_grade(m,{scene['scene_id']+'/frame2'},pair,legal,release)
            exposed=set(m['public_targets'])|set(m['historical_targets'])
            ck('FN uses exposed targets only '+key+'/'+scene['scene_id'],set(grade['false_negative_ids'])==exposed-set(m['detected_ids']))
            if not exposed:ck('unexposed never pass or FN '+key+'/'+scene['scene_id'],not grade['passed'] and not grade['false_negative_ids'] and len(grade['missing_exposure_ids'])==1)
            per_scene.append(dict(scene_id=scene['scene_id'],**grade))
        ck('all16 per-scene grades replay '+key,normalized(per_scene)==normalized(grades[key]['per_scene']))
        expected=dict(scenarios=len(per_scene),passed=sum(g['passed'] for g in per_scene),exposed=sum(g['exposed_targets'] for g in per_scene),
            misses=sum(len(g['false_negative_ids']) for g in per_scene),false_positives=sum(len(g['false_positive_records']) for g in per_scene),
            missing_exposure=sum(len(g['missing_exposure_ids']) for g in per_scene),unknown=sum(len(g['critical_unknown']) for g in per_scene),
            untriggered=sum(len(g['untriggered_target_ids']) for g in per_scene),native_failures=sum(len(g['native_failed']) for g in per_scene),
            incomplete_scenes=sum(g['native_population_incomplete'] for g in per_scene),
            legal_observation_failures=sum(g['legal_frame_observations']!=g['expected_legal_frame_observations'] for g in per_scene),
            readiness_or_handshake_failures=sum(not g['required_readiness_and_handshake_exposed'] for g in per_scene),whole_scope_pass=all(g['passed'] for g in per_scene))
        ck('summary exact '+key,expected=={k:v for k,v in grades[key].items() if k!='per_scene'})
        summary.append(dict(physical_version=key,**expected))
        missing_sets.append({g['scene_id'] for g in per_scene if g['missing_exposure_ids']})
        print('AUDITED independent',key,expected['passed'],expected['misses'],expected['missing_exposure'],flush=True)
    ck('same four no-exposure scenes for all versions',all(len(ms)==4 and ms==missing_sets[0] for ms in missing_sets))
    expected_results=[dict(**item,**{k:v for k,v in grades[item['physical_version']].items() if k!='per_scene'}) for item in entries]
    ck('16 logical result rows exact',expected_results==read(out/'results.json'))
    cost=read(out/'cost.json');physical=run.actual_cost(out)
    ck('physical cost ledger exact',all(cost[k]==v for k,v in physical.items()) and cost['logical_versions']==16 and cost['distinct_versions']==8)
    ck('32 physical compiles and executions',physical['physical_compiles']==physical['physical_executions']==32)
    ck('no model/formal cost',cost['model_calls']==cost['tokens']==cost['formal_calls']==0)
    ck('all preexisting audited artifacts unchanged',all(sha(out/name)==digest for name,digest in before.items()))
    answer=dict(passed=True,checks=checks,check_count=len(checks),source_bindings_verified=len(bindings),logical_versions=16,distinct_versions=8,
        native_jobs_replayed=32,raw_native_markers_reparsed=marker_count,version_measurement_replays=8,per_scene_grade_replays=128,
        label_isolation_replays=8,semantic_test_inputs=16,blocked_semantic_inputs=len(blocked),exclusion_sources=sorted(set(exclusion_sources)),
        no_exposure_scenes=sorted(missing_sets[0]),no_exposure_is_pass=False,no_exposure_is_false_negative=False,
        incorrect_pass_or_fn_count_found=0,distinct_version_results=summary,all_whole_scope_passes_false=all(not g['whole_scope_pass'] for g in grades.values()),
        new_native_executions=0,model_calls=0,formal_calls=0,audit_wall_seconds=time.perf_counter()-started,
        selection_sequence_evidence='Verified bound execute source freezes all versions before test_population/scene construction; selection hash and all candidate/freeze/source hashes match. Filesystem mtime order is a supplemental check, not a standalone cryptographic chronology proof.',
        limitations=['One historical axis_fifo atomic oversize-drop parent, same original before/after revisions; no unseen fault implementation or cross-design generalization.',
            '16 logical arms share 8 distinct frozen versions and 32 physical executions; duplicated arms, seeds and failure cycles are not independent bugs.',
            'Only12 of16 inputs expose the historical target; four remain no-exposure, so zero full-scope passes. No replacement or resampling.',
            'Depth16/32, KEEP0, unique transaction IDs, first presentation and initial reset only; not full FIFO functionality or dynamic reset/flush proof.',
            'Triggers are procedural antecedent diagnostics emitted beside native SVA, not formal native cover proofs.'])
    s.dump(out/'audit.json',answer)
    print(json.dumps({k:v for k,v in answer.items() if k not in ('checks','distinct_version_results','exclusion_sources')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--manifest',type=Path,required=True)
    a=ap.parse_args();audit(a.out.resolve(),a.manifest.resolve())
