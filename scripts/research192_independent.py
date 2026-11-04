"""Frozen multi-arm native validation using the existing FIFO bench and oracle.

All versions freeze before input construction. Identical versions share physical
execution; distinct properties share a bench without sharing acceptance decisions.
This is a new-input test of ONE historical fault, not unseen-mutant generalization.
"""
import argparse
import copy
import hashlib
import itertools
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import research188_drop_binding_audit as b
from research190_fifo_independent import scope_grade

p, s, ROOT = b.p, b.s, b.ROOT


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_population():
    # New release-gap positions, fixed without consulting validation outcomes.
    return [p.descriptor(d, policy, excess, offset)
            for d, policy, excess, offset in itertools.product(
                (16, 32), p.q.POLICIES, (5, 9), (-1, 2))]


def combined_bench(versions, depth, policy, rows):
    """Concatenate exact independently validated properties with unique labels."""
    rendered = [p.bench(c, depth, policy, rows) for c in versions.values()]
    blocks = []
    for source in rendered:
        lo = source.index(': assert property')
        lo = source.rfind('\n', 0, lo) + 1
        hi = source.index('initial begin $dumpfile', lo)
        blocks.append(source[lo:hi])
    first = rendered[0]
    lo = first.rfind('\n', 0, first.index(': assert property')) + 1
    hi = first.index('initial begin $dumpfile', lo)
    return first[:lo] + ''.join(blocks) + first[hi:]


def safe_measure(candidate, jobs):
    try:
        return b.bound_measure(candidate,jobs)
    except Exception as exc:
        return dict(ordinary_accept=False,historical_accept=False,detected_ids=[],triggered_ids=[],
            public_targets=[],historical_targets=[],lost=[],false_positives=[],
            critical_unknown=['reference_or_binding_error:'+type(exc).__name__],
            obligation_assertion_evidence=[],reference={},candidate_sha256=p.digest(candidate))


def actual_cost(out):
    compiles=list((out/'native').rglob('compile.json'))
    executions=list((out/'native').rglob('execute.json'))
    return dict(model_calls=0,tokens=0,physical_compiles=len(compiles),physical_executions=len(executions),
        compile_seconds=sum(read(f)['wall_seconds'] for f in compiles),
        execution_seconds=sum(read(f)['wall_seconds'] for f in executions),formal_calls=0)


def execute(manifest, out):
    started = time.monotonic()
    entries = read(manifest)
    if not entries:
        raise ValueError('no_frozen_versions')
    out.mkdir(parents=True, exist_ok=False)
    versions, assignments, bindings = {}, {}, {}
    # Bind the actually imported backend/oracle closure, both original revisions,
    # simulator executable and version BEFORE selecting or constructing inputs.
    files={Path(__file__).resolve()}
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and Path(name).suffix=='.py' and Path(name).resolve().is_relative_to(ROOT/'scripts'):
            files.add(Path(name).resolve())
    files.update(p.q.P/'frame_fifo_drop'/revision/'axis_fifo.v' for revision in ('before','after'))
    binary,env=s.n.native_environment()
    files.add(Path(binary).resolve())
    for path in files:
        key=s.rel(path) if path.is_relative_to(ROOT) else str(path)
        bindings[key]=file_hash(path)
    version,_=s.n.command([binary,'--version'],out,'tool_version',15,env)
    if version.get('exit_code')!=0:raise ValueError('native_tool_version_unavailable')
    bindings[s.rel(out/'tool_version.log')]=file_hash(out/'tool_version.log')
    for item in entries:
        path = ROOT / item['path']
        if file_hash(path) != item['sha256']:
            raise ValueError('frozen_candidate_changed')
        candidate = p.validate(read(path))
        freeze_path = ROOT / item['freeze_path']
        freeze = read(freeze_path)
        if (file_hash(freeze_path) != item['freeze_sha256'] or
                freeze.get('candidate_sha256') != p.digest(candidate) or
                freeze.get('freeze_before_independent') is not True):
            raise ValueError('missing_or_invalid_freeze')
        bindings[s.rel(freeze_path)] = file_hash(freeze_path)
        signature = p.digest(candidate)
        if signature not in assignments:
            key = 'v' + str(len(versions))
            renamed = copy.deepcopy(candidate)
            for i, a in enumerate(renamed):
                a['label'] = f'{key}_a{i}'
            versions[key] = p.validate(renamed)
            assignments[signature] = key
        item['physical_version'] = assignments[signature]
        bindings[s.rel(path)] = file_hash(path)
    s.dump(out/'frozen_bindings.json', bindings)
    s.dump(out/'arm_versions.json', entries)
    s.dump(out/'renamed_properties.json', versions)
    protocol = dict(scope='one original axis_fifo atomic oversize drop historical parent',
        population='16 fixed semantic descriptors: depths16/32, ready/stalled, excess5/9, gap offsets-1/2',
        independent_unit='one frame transaction; all descriptors remain one parent Bug',
        distinction='new input and release-gap combinations, NOT independent fault implementations',
        selection='all versions hash-frozen before construction; no replacement on no-exposure or failure',
        budget=dict(compiles=32, executions=32, workers=2, model_calls=0, retries=0),
        physical_sharing='compile all frozen properties in one bench; alarms filtered by unique per-version labels',
        no_exposure='separate from false negatives, never a pass', source=file_hash(__file__))
    s.dump(out/'protocol.json', protocol)
    descriptors = test_population()
    # Conservatively exclude the entire old reserved population, not just tested inputs.
    prior = ROOT/'deliverables/research188_drop_binding_prepare_20261102_r01'
    excluded=[]
    for name in ('reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json'):
        path=prior/name
        bindings[s.rel(path)]=file_hash(path)
        excluded.extend(read(path))
    blocked = {tuple(v['semantic_key']) for v in excluded}
    # Each manifest row may bind the exact development query list used by its arm.
    for item in entries:
        if item.get('development_descriptors'):
            source = ROOT / item['development_descriptors']
            if file_hash(source) != item['development_descriptors_sha256']:
                raise ValueError('development_descriptor_binding_changed')
            blocked.update(tuple(d['semantic_key']) for d in read(source))
            bindings[s.rel(source)] = file_hash(source)
    s.dump(out/'frozen_bindings.json', bindings)
    if blocked & {tuple(v['semantic_key']) for v in descriptors}:
        raise ValueError('semantic_test_development_overlap')
    scenes = [dict(scene_id=f'test{i}/{d["depth"]}/{d["policy"]}', descriptor=d,
                   depth=d['depth'], policy=d['policy'], rows=p.scene(d)) for i,d in enumerate(descriptors)]
    s.dump(out/'selection.json', scenes)
    s.dump(out/'selection_seal.json', {'manifest': file_hash(manifest), 'selection':file_hash(out/'selection.json'),
        'frozen_bindings':file_hash(out/'frozen_bindings.json'), 'selected_after_all_versions_frozen':True})
    def native(scene, revision):
        folder = out/'native'/scene['scene_id']/revision
        source = combined_bench(versions, scene['depth'], scene['policy'], scene['rows'])
        try:
            result = s.n.run_native(source, folder, extra_sources=[p.q.P/'frame_fifo_drop'/revision/'axis_fifo.v'])
        except Exception as exc:
            result = dict(compile_status='unknown',execution_status='not_completed',
                          failures=[],triggers=[],error_type=type(exc).__name__)
            s.dump(folder/'result.json',result)
        return dict(scene_id=scene['scene_id'], depth=scene['depth'], policy=scene['policy'],
                    rows=scene['rows'], revision=revision, folder=str(folder), result=result)
    jobs = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = [executor.submit(native, scene, rev) for scene in scenes for rev in ('before','after')]
        for future in as_completed(pending):
            jobs.append(future.result())
            s.dump(out/'executions.json', sorted(jobs, key=lambda j:(j['scene_id'],j['revision'])))
            print('INDEPENDENT', len(jobs), '/32', flush=True)
    measurements, grades = {}, {}
    for key, candidate in versions.items():
        measurement = safe_measure(candidate, jobs)
        measurements[key] = measurement
        per_scene = []
        for scene in scenes:
            pair = [j for j in jobs if j['scene_id']==scene['scene_id']]
            m = safe_measure(candidate, pair)
            legal = sum(len(r['correct_first_cycles']) for r in m['reference'].values())
            release = all(ev['first']['ready']==int(scene['policy']=='ready_first') and bool(ev['outputs'])
                          for r in m['reference'].values() for ev in r['events'])
            grade = scope_grade(m, {scene['scene_id']+'/frame2'}, pair, legal, release)
            per_scene.append(dict(scene_id=scene['scene_id'], **grade))
        grades[key] = dict(scenarios=len(per_scene), passed=sum(x['passed'] for x in per_scene),
            exposed=sum(x['exposed_targets'] for x in per_scene),
            misses=sum(len(x['false_negative_ids']) for x in per_scene),
            false_positives=sum(len(x['false_positive_records']) for x in per_scene),
            missing_exposure=sum(len(x['missing_exposure_ids']) for x in per_scene),
            unknown=sum(len(x['critical_unknown']) for x in per_scene),
            untriggered=sum(len(x['untriggered_target_ids']) for x in per_scene),
            native_failures=sum(len(x['native_failed']) for x in per_scene),
            incomplete_scenes=sum(x['native_population_incomplete'] for x in per_scene),
            legal_observation_failures=sum(x['legal_frame_observations']!=x['expected_legal_frame_observations'] for x in per_scene),
            readiness_or_handshake_failures=sum(not x['required_readiness_and_handshake_exposed'] for x in per_scene),
            whole_scope_pass=all(x['passed'] for x in per_scene), per_scene=per_scene)
    for name, digest in bindings.items():
        if file_hash(ROOT/name)!=digest:
            raise ValueError('candidate_changed_during_test')
    s.dump(out/'measurements.json', measurements)
    s.dump(out/'grades.json', grades)
    s.dump(out/'results.json', [dict(**item, **{k:v for k,v in grades[item['physical_version']].items() if k!='per_scene'}) for item in entries])
    s.dump(out/'cost.json',dict(**actual_cost(out),
        wall_seconds=time.monotonic()-started, logical_versions=len(entries), distinct_versions=len(versions)))
    s.dump(out/'outcome.json',dict(status='completed',all_frozen_unchanged=True,new_fault_generalization=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        execute(args.manifest.resolve(),args.out.resolve())
    except Exception as exc:
        if args.out.exists():
            s.dump(args.out/'cost_on_error.json',actual_cost(args.out))
            s.dump(args.out/'outcome.json',dict(status='error',reason=type(exc).__name__,not_passed=True))
        raise
