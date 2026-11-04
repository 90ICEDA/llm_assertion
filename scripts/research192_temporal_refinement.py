"""Opt-in temporal localization and constrained edits on the existing FIFO backend.

The generic localizer consumes independently confirmed observations; it does not
label waveforms or execute SVA. The connected pilot only validates same-sample
FIFO first-presentation predicates. No archived successful model is substituted.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import re
import time

import research188_drop_binding_audit as binding
import research69_deadline_transport as transport

p, s, ROOT = binding.p, binding.s, binding.ROOT
STRATEGIES = ('R0', 'R1', 'R2', 'R3')
SOURCE = ROOT / 'deliverables/research188_drop_binding_prepare_20261102_r01'
MODEL = 'deepseek/deepseek-v3-0324'


def localize(candidate, evidence, enabled=True):
    """Return actionable hypotheses, never promote an ambiguous cause to truth.

Each record needs status=confirmed and label=legal/violation, and assertion-bound
trigger/failure observations. Specialized causal facts (e.g. latency mismatch)
must come from a case adapter's independent obligation/transaction monitor.
"""
    if not enabled:
        return []
    findings = {}
    valid_labels = {a['label'] for a in candidate}
    def add(kind, assertion, field, row, reason):
        key = (kind, assertion, field)
        value = findings.setdefault(key, dict(kind=kind, assertion=assertion,
            field=field, evidence_ids=[], reason=reason,
            status='supported_hypothesis_requires_native_validation'))
        if row['id'] not in value['evidence_ids']:
            value['evidence_ids'].append(row['id'])
    for row in evidence:
        if row.get('status') != 'confirmed' or row.get('label') not in ('legal', 'violation'):
            continue
        for a in row.get('assertions', []):
            label = a.get('assertion')
            if label not in valid_labels:
                continue
            trigger, failure = a.get('trigger'), a.get('failure')
            if row['label'] == 'violation' and trigger is False:
                add('trigger_too_narrow', label, 'antecedent', row,
                    'Confirmed target first presentation is outside the native trigger; broaden applicability or add complementary protection.')
            elif row['label'] == 'violation' and trigger is True and failure is False:
                add('response_missing', label, 'consequent', row,
                    'Native trigger occurs on a confirmed target but consequent permits it.')
            elif row['label'] == 'legal' and failure is True:
                # The alarm alone cannot distinguish a broad trigger from a
                # strict consequent. Preserve both alternatives explicitly.
                add('trigger_too_broad', label, 'antecedent', row,
                    'Legal alarm: trigger applicability is one possible cause; not established by the alarm alone.')
                add('response_too_strict', label, 'consequent', row,
                    'Legal alarm: consequent is another possible cause; native replay must disambiguate.')
            facts = row.get('independent_facts', {})
            for fact, kind, field in (
                ('latency_mismatch', 'latency_window', 'timing'),
                ('transaction_mismatch', 'transaction_matching', 'consequent'),
                ('legal_exception_missed', 'legal_exception', 'antecedent'),
                ('required_trigger_missing', 'insufficient_trigger', 'antecedent')):
                if facts.get(fact) is True:
                    add(kind, label, field, row, 'Independent case adapter confirms ' + fact)
    for assertion in candidate:
        observed = [(row, a) for row in evidence
                    if row.get('status') == 'confirmed' and row.get('label') in ('legal', 'violation')
                    for a in row.get('assertions', []) if a.get('assertion') == assertion['label']]
        targets = [row for row, a in observed if row['label'] == 'violation']
        if targets and all(a.get('trigger') is False for _, a in observed):
            add('vacuity_or_insufficient_trigger', assertion['label'], 'antecedent', targets[0],
                'No trigger in the confirmed finite evidence despite exposed targets; this is finite-suite inactivity, not proof of logical vacuity.')
    return sorted(findings.values(), key=lambda f: (f['assertion'], f['field'], f['kind']))


def apply_local_edits(current, value, findings, validator=p.validate,
                      local_failed=False, uncovered_obligations=()):
    """Apply exact model-owned expressions only at localized fields.

Existing labels/obligation metadata and all untouched fields stay byte-exact.
Composition/regeneration is allowed only after an actual failed local attempt,
and a new assertion must address a still-uncovered, declared obligation.
"""
    if not isinstance(value, dict) or set(value) != {'edits', 'reason'} or not isinstance(value['reason'], str):
        raise ValueError('local_edit_schema')
    edits = value['edits']
    if not isinstance(edits, list) or not 1 <= len(edits) <= 2:
        raise ValueError('local_edit_count')
    result = copy.deepcopy(current)
    allowed = {(f['assertion'], f['field']) for f in findings}
    used = set()
    for edit in edits:
        if edit.get('op') == 'replace_field':
            if set(edit) != {'op', 'assertion', 'field', 'value'}:
                raise ValueError('replace_field_schema')
            key = (edit['assertion'], edit['field'])
            if key not in allowed or key in used:
                raise ValueError('unlocalized_or_duplicate_field')
            target = next((a for a in result if a['label'] == edit['assertion']), None)
            if target is None or edit['field'] not in ('antecedent', 'consequent', 'timing'):
                raise ValueError('unknown_edit_target')
            if target[edit['field']] == edit['value']:
                raise ValueError('no_change')
            target[edit['field']] = edit['value']
            used.add(key)
        elif edit.get('op') == 'add_assertion':
            if set(edit) != {'op', 'assertion'} or not local_failed:
                raise ValueError('composition_before_local_failure')
            a = edit['assertion']
            if not set(a.get('obligations', [])) & set(uncovered_obligations):
                raise ValueError('composition_without_uncovered_obligation')
            result.append(copy.deepcopy(a))
        else:
            raise ValueError('unknown_local_operation')
    return validator(result)


def archived_baseline():
    """Read already-qualified development traces, never independent artifacts."""
    initial = json.loads(s.read(SOURCE / 'request.preview.json')['messages'][1]['content'])['current_assertions']
    jobs = []
    for depth in p.q.DEPTHS:
        for policy in p.q.POLICIES:
            for revision in ('before', 'after'):
                folder = p.ARCHIVE / 'native' / str(depth) / policy / revision
                jobs.append(dict(scene_id=f'{depth}/{policy}', depth=depth,
                    policy=policy, revision=revision, folder=str(folder),
                    rows=p.q.rows(depth, policy), result=s.read(folder / 'result.json')))
    measurement = binding.bound_measure(initial, jobs)
    if measurement['critical_unknown']:
        raise ValueError('baseline_unknown')
    protected = measurement['detected_ids']
    return initial, jobs, protected, evidence_from_jobs(initial, jobs)


def evidence_from_jobs(candidate, jobs):
    """Native marker to independent first-presentation transaction binding."""
    result = []
    for job in jobs:
        native = job['result']
        identity = f"{job['scene_id']}/{job['revision']}"
        if native['compile_status'] != 'passed' or native['execution_status'] != 'completed':
            result.append(dict(id=identity, status='unknown', label='unknown', reason='native_incomplete'))
            continue
        traces = s.traces(Path(job['folder']))
        reference = p.q.reference(traces, job['depth'])
        if reference['unknown']:
            result.append(dict(id=identity, status='unknown', label='unknown', reason=reference['unknown']))
            continue
        violations = {ev['first']['cycle'] for ev in reference['events']}
        legal = set(reference['correct_first_cycles'])
        def markers(key):
            return {(r['id'], int(re.fullmatch(r'cycle=(\d+)', r['detail'].strip())[1]))
                    for r in native[key] if re.fullmatch(r'cycle=(\d+)', r['detail'].strip())}
        triggers, failures = markers('triggers'), markers('failures')
        for row in traces:
            cy = row['cycle']
            if cy not in violations | legal:
                continue
            result.append(dict(id=f"{identity}/frame{row['mid']}", status='confirmed',
                label='violation' if cy in violations else 'legal', obligation=p.OB,
                scene_id=job['scene_id'], policy=job['policy'], revision=job['revision'],
                parent_bug='axis_fifo_oversize_atomic_drop', transaction=row['mid'], cycle=cy,
                observations={k: row[k] for k in ('first','cnt','done','mr','rst')}, depth=job['depth'],
                assertions=[dict(assertion=a['label'], trigger=(a['label'], cy) in triggers,
                    failure=(a['label'], cy) in failures) for a in candidate],
                source_result=s.rel(Path(job['folder']) / 'result.json'),
                source_vcd=s.rel(Path(job['folder']) / 'wave.vcd')))
    return result


def build_request(base_req, strategy, evidence, seed, current=None):
    if strategy not in STRATEGIES:
        raise ValueError('unknown_strategy')
    req = copy.deepcopy(base_req)
    body = json.loads(req['messages'][1]['content'])
    if current is not None:
        body['current_assertions'] = copy.deepcopy(current)
    body.pop('public_development', None)
    body['development_observations'] = copy.deepcopy(evidence)
    body['acceptance'] = 'Native SVA execution and independent transaction monitor; unknown never passes. All arms have identical raw development observations and maximum cost; no independent tests in the request.'
    body['task'] = 'Return a modified assertion set using the supplied RTL, specification, current SVA and observations. Choose expressions yourself.'
    if strategy in ('R1', 'R2', 'R3'):
        body['bidirectional_feedback'] = {
            'missed_target_ids': [e['id'] for e in evidence if e.get('status') == 'confirmed' and e.get('label') == 'violation' and not any(a.get('failure') for a in e.get('assertions', []))],
            'false_alarm_ids': [e['id'] for e in evidence if e.get('status') == 'confirmed' and e.get('label') == 'legal' and any(a.get('failure') for a in e.get('assertions', []))],
            'instructions': 'Reduce both false alarms on legal transactions and missed confirmed violations.'}
    if strategy in ('R2', 'R3'):
        body['history_guard'] = 'Replay all confirmed historical evidence; reject lost detections, new legal alarms, unknown or absent required trigger. A rejected proposal cannot replace the active candidate.'
    findings = localize(body['current_assertions'], evidence, enabled=strategy == 'R3')
    if strategy == 'R3':
        body['localization'] = findings
        body['task'] = 'Perform at most two localized field edits. Every new expression is your choice. Preserve every other field verbatim. A later composition fallback is possible only after a measured local failure; this first call must use replace_field.'
        body['output_schema'] = dict(edits=[dict(op='replace_field', assertion='existing label',
            field='one of the localized fields', value='your SystemVerilog expression or timing')], reason='explain the localized edit')
        req['messages'][0]['content'] = 'Return only JSON with edits and reason, obeying the constrained localized-field interface.'
    req['messages'][1]['content'] = json.dumps(body, separators=(',', ':'))
    req.update(model=MODEL, seed=seed, temperature=0.2, max_tokens=1024)
    return req, findings


class RefinementModel(transport.RemoteModel):
    def _payload(self, *args):
        return copy.deepcopy(self.pending_request)
    def save_decoded_output(self, folder, value, current, secret):
        candidate = (apply_local_edits(current, value, self.findings)
                     if self.strategy == 'R3' else p.adapt(value))
        s.dump(folder / 'candidate.json', candidate)
        (folder / 'candidate.sva').write_text('\n'.join(
            f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']}));"
            for a in candidate) + '\n')
        return candidate, 'model_local_fields_exact' if self.strategy == 'R3' else 'model_full_set_exact'


def evaluate(candidate, folder, protected, descriptors=None, workers=2):
    """Use unchanged native executor/oracle, accepting arbitrary development queries.

Unlike old independent-only evaluate, this adapter accepts a development subset.
This function does not itself create or select independent acceptance tests.
"""
    p.validate(candidate)
    folder.mkdir(parents=True, exist_ok=False)
    if descriptors is None:
        scenes = [(f'{d}/{policy}', d, policy, p.q.rows(d, policy))
                  for d in p.q.DEPTHS for policy in p.q.POLICIES]
    else:
        scenes = [(f'query{i}/{d["depth"]}/{d["policy"]}', d['depth'], d['policy'], p.scene(d))
                  for i, d in enumerate(descriptors)]
    plans = [dict(scene_id=sid, depth=d, policy=policy, rows=rows,
                  revision=rev, folder=str(folder / sid / rev))
             for sid, d, policy, rows in scenes for rev in ('before', 'after')]
    def execute(job):
        try:
            job['result'] = s.n.run_native(p.bench(candidate, job['depth'], job['policy'], job['rows']),
                Path(job['folder']), extra_sources=[p.q.P / 'frame_fifo_drop' / job['revision'] / 'axis_fifo.v'])
        except Exception as exc:
            job['result'] = dict(compile_status='unknown', execution_status='not_completed',
                failures=[], triggers=[], error_type=type(exc).__name__)
            s.dump(Path(job['folder']) / 'result.json', job['result'])
        return job
    with ThreadPoolExecutor(max_workers=workers) as pool:
        jobs = list(pool.map(execute, plans))
    s.dump(folder / 'executions.json', jobs)
    result = binding.bound_measure(candidate, jobs, protected)
    result['expected_scene_count'] = len(scenes)
    result['native_job_count'] = len(jobs)
    result['no_target_exposure_scenes'] = [sid for sid, *_ in scenes if not any(
        eid.startswith(sid + '/') for eid in result['public_targets'] + result['historical_targets'])]
    s.dump(folder / 'measurement.json', result)
    return result


def decide(strategy, measurement, initial_measurement=None):
    """R0/R1 current gate; R2/R3 current + complete history + regression guard."""
    history = strategy in ('R2', 'R3')
    accepted = measurement['historical_accept'] if history else measurement['ordinary_accept']
    old_fps = set()
    if initial_measurement:
        old_fps = {json.dumps(x, sort_keys=True) for x in initial_measurement['false_positives']}
    new_fps = [x for x in measurement['false_positives'] if json.dumps(x, sort_keys=True) not in old_fps]
    regression = bool(measurement['lost'] or new_fps)
    if history and regression:
        accepted = False
    return dict(accepted=bool(accepted and not measurement['critical_unknown']),
                regression=regression, lost=measurement['lost'], new_false_positives=new_fps)


def run_arm(out, strategy, seed, evidence=None, initial=None, protected=None,
            base_request=None, descriptors=None, workers=2, native_cache=None):
    """One actual model request + full native gate. Inject evidence for A0-A3.

descriptors are extra development queries; the full historical six-scene gate
is always retained. native_cache can share identical candidate replay physically,
while reporting the full logical cost per arm and cache provenance separately.
"""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    baseline, jobs, default_protected, default_evidence = archived_baseline()
    initial = baseline if initial is None else initial
    if p.digest(initial) != p.digest(baseline):
        raise ValueError('external_initial_requires_a_separately_bound_baseline')
    protected = default_protected if protected is None else protected
    evidence = default_evidence if evidence is None else evidence
    base_request = s.read(SOURCE / 'request.preview.json') if base_request is None else base_request
    req, findings = build_request(base_request, strategy, evidence, seed, initial)
    s.dump(out / 'request.preview.json', req)
    s.dump(out / 'localization.json', findings)
    s.dump(out / 'initial.json', initial)
    s.dump(out / 'evidence.json', evidence)
    baseline_measurement = binding.bound_measure(initial, jobs, protected)
    s.dump(out / 'baseline_measurement.json', baseline_measurement)
    config = dict(remote_url=p.ENDPOINT, remote_model=MODEL, max_model_calls=1,
        max_tokens=120000, max_wall_seconds=1200, call_timeout=300,
        options=dict(seed=seed, temperature=0.2, num_predict=1024))
    model = RefinementModel(out / 'transport', config)
    model.pending_request, model.strategy, model.findings = req, strategy, findings
    start = time.monotonic()
    proposal = None
    try:
        response, proposal = model.call(out / 'model_call', initial, p.OB, {}, strategy)
    except Exception as exc:
        response = dict(status='not_dispatched_or_budget_failure', error_type=type(exc).__name__,
                        prompt_tokens=None, completion_tokens=None)
    measured, decision, reused = None, None, None
    if proposal is not None:
        key = p.digest(dict(candidate=proposal, protected=sorted(protected)))
        if native_cache is not None and key in native_cache:
            cached = native_cache[key]
            measured = copy.deepcopy(cached['measurement'])
            reused = cached['source']
            s.dump(out / 'native_replay_reuse.json', dict(source=reused, candidate_sha256=p.digest(proposal),
                reason='Identical expression set and protected IDs on identical complete historical gate; physical replay shared, logical cost retained.'))
        else:
            measured = evaluate(proposal, out / 'native', protected, workers=workers)
            if native_cache is not None:
                native_cache[key] = dict(measurement=copy.deepcopy(measured), source=s.rel(out / 'native'))
        decision = decide(strategy, measured)
        if descriptors:
            acquired = evaluate(proposal, out / 'acquired_native', (), descriptors, workers)
            s.dump(out / 'acquired_measurement.json', acquired)
            if acquired['critical_unknown'] or acquired['false_positives'] or set(acquired['public_targets'] + acquired['historical_targets']) - set(acquired['detected_ids']):
                decision['accepted'] = False
        s.dump(out / 'measurement.json', measured)
        s.dump(out / 'decision.json', decision)
    terminal = proposal if decision and decision['accepted'] else initial
    s.dump(out / 'terminal.json', terminal)
    s.dump(out / 'frozen.json', dict(candidate_sha256=p.digest(terminal), seed=seed, strategy=strategy,
        freeze_before_independent=True, independent_results_not_used=True))
    # Final active metrics use the unchanged baseline when a proposal is rejected.
    final_metrics = measured if decision and decision['accepted'] else baseline_measurement
    physical = list(out.rglob('compile.json'))
    native_seconds = sum(s.read(x)['wall_seconds'] for x in physical + list(out.rglob('execute.json')))
    result = dict(strategy=strategy, seed=seed, parent_bug='axis_fifo_oversize_atomic_drop',
        status=response['status'], candidate_generated=proposal is not None,
        accepted=bool(decision and decision['accepted']),
        regression_proposals=int(bool(decision and decision['regression'])),
        accepted_regressions=int(bool(decision and decision['regression'] and decision['accepted'])),
        final_detected=len(final_metrics['detected_ids']),
        final_targets=len(set(final_metrics['public_targets'] + final_metrics['historical_targets'])),
        final_fp=len(final_metrics['false_positives']),
        final_fn=len(set(final_metrics['public_targets'] + final_metrics['historical_targets']) - set(final_metrics['detected_ids'])),
        final_unknown=len(final_metrics['critical_unknown']),
        effective_rounds=int(bool(decision and decision['accepted'] and set(measured['detected_ids']) - set(protected))),
        model_calls=len(model.calls), prompt_tokens=response.get('prompt_tokens'), completion_tokens=response.get('completion_tokens'),
        physical_native_compiles=len(physical), logical_native_compiles=12 if measured else 0,
        native_reuse_source=reused, native_seconds=native_seconds, wall_seconds=time.monotonic()-start,
        independent_acceptance='not_run_in_refinement_pilot',
        scope='One original FIFO parent bug; finite initial-reset, unique-TID, same-sample first-presentation evidence; no general temporal or cross-design claim.')
    s.dump(out / 'result.json', result)
    return result


def campaign(out, seeds=(19207, 19219)):
    out.mkdir(parents=True, exist_ok=False)
    initial, _, protected, evidence = archived_baseline()
    protocol = dict(purpose='research192_paired_temporal_refinement_pilot',
        authorization='Current user explicitly requested real R0-R3 experiments; new bounded protocol, no reuse of historical purpose-bound grants.',
        arms=list(STRATEGIES), seeds=list(seeds), initial_sha256=p.digest(initial),
        evidence_sha256=p.digest(evidence), protected=protected,
        physical_model_call_cap=4*len(seeds), per_arm_calls=1, retries=0,
        model=MODEL, temperature=0.2, max_output_tokens=1024, timeout_per_call=300,
        maximum_native_compiles=48*len(seeds), native_workers=2,
        estimand='Paired one-step refinement on identical raw observations; policy feedback/interface/history-gate differ by predeclared arm.',
        allocation='All arms receive identical raw current and historical observations. R0 free set rewrite, R1 adds bidirectional diagnosis, R2 adds history rejection, R3 localizes and constrains edits. R3 composition is implemented but not activated in one-call pilot.',
        independence='No independent artifacts are read. A later separate frozen evaluation must select unseen transactions.',
        no_exposure='Depth8 has no reachable oversize output in existing scenes; report separately, not as a successful detection.',
        limits='One parent bug; this pilot cannot establish general superiority or benefit of multi-round composition.')
    s.dump(out / 'protocol.json', protocol)
    s.dump(out / 'source_bindings.json', {s.rel(Path(__file__)): s.sha(Path(__file__))})
    rows, cache = [], {}
    for seed in seeds:
        for strategy in STRATEGIES:
            print(f'START {strategy} seed={seed}', flush=True)
            rows.append(run_arm(out / f'seed{seed}' / strategy, strategy, seed,
                evidence=evidence, initial=initial, protected=protected, native_cache=cache))
            s.dump(out / 'results.json', rows)
            print(json.dumps(rows[-1]), flush=True)
    lines = ['# R0–R3 paired refinement pilot', '',
        'Same initial SVA, model, seed pair, raw evidence and one-call cap. One parent bug only. Native results are simulation evidence, not formal proof.', '',
        '| Arm | Seed | Accepted | FP | FN | Protected transactions | Regression proposals | Effective rounds | Model calls | Tokens | Native compiles physical/logical |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        tokens = None if r['prompt_tokens'] is None or r['completion_tokens'] is None else r['prompt_tokens']+r['completion_tokens']
        lines.append(f"|{r['strategy']}|{r['seed']}|{int(r['accepted'])}|{r['final_fp']}|{r['final_fn']}|{r['final_detected']}/{r['final_targets']}|{r['regression_proposals']}|{r['effective_rounds']}|{r['model_calls']}|{tokens}|{r['physical_native_compiles']}/{r['logical_native_compiles']}|")
    lines += ['', 'No independent acceptance or cross-design generalization is inferred from this table. R3 supports multiple localization classes but this connected fixture exercises only same-sample applicability. Composition requires an actual failed local attempt and was not tested by this one-step budget.',
        'Depth8 scenes have no target exposure and are excluded from violation denominators. Parent-bug denominator is 1, not 4 target transactions or repeated output cycles.']
    (out / 'REPORT.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return rows


def prepare(out, seeds=(19207, 19219)):
    """Produce exact reviewable requests with zero credential/network access."""
    out.mkdir(parents=True, exist_ok=False)
    initial, jobs, protected, evidence = archived_baseline()
    baseline = binding.bound_measure(initial, jobs, protected)
    s.dump(out / 'initial.json', initial)
    s.dump(out / 'baseline_measurement.json', baseline)
    s.dump(out / 'evidence.json', evidence)
    base = s.read(SOURCE / 'request.preview.json')
    manifest = []
    for seed in seeds:
        for strategy in STRATEGIES:
            request, findings = build_request(base, strategy, evidence, seed, initial)
            folder = out / f'seed{seed}' / strategy
            s.dump(folder / 'request.preview.json', request)
            s.dump(folder / 'localization.json', findings)
            manifest.append(dict(strategy=strategy, seed=seed,
                request=s.rel(folder / 'request.preview.json'),
                request_sha256=s.sha(folder / 'request.preview.json'),
                utf8_reservation=sum(len(m['content'].encode()) for m in request['messages'])+3072))
    s.dump(out / 'requests.json', manifest)
    s.dump(out / 'protocol.json', dict(status='prepared_external_transfer_permission_blocked',
        endpoint=p.ENDPOINT, model=MODEL, seeds=list(seeds), strategies=list(STRATEGIES),
        max_physical_model_calls=len(manifest), max_calls_per_arm=1, retries=0,
        temperature=0.2, max_output_tokens=1024, call_timeout_seconds=300,
        payload='Original before/after open-source axis_fifo RTL, SVA candidate, specification, independent development observations; no credentials in request artifacts.',
        actual_model_calls=0, historical_independent_results_read=False,
        initial_sha256=p.digest(initial), evidence_sha256=p.digest(evidence),
        native_gate='Unchanged 6 development scene pairs, all historical protection and independent transaction oracle. R0/R1 current acceptance; R2/R3 full history and no regression.',
        R3='Evidence localization and max2 model-chosen field replacements; unsupported fields rejected; composition only after measured failed local attempt, not exercised in one-call protocol.',
        blocked_reason='Automatic approval review rejected transmission of project RTL/SVA/specification and evidence to highwayapi.ai without explicit destination/payload authorization. No alternate transport attempted.',
        limitations='One FIFO parent bug, one local edit round; all arms same raw data. No multi-round, cross-design, temporal-window or composition benefit inferred.'))
    sources = [Path(__file__), Path(binding.__file__), Path(p.__file__), Path(p.q.__file__),
               Path(s.__file__), Path(transport.__file__), SOURCE / 'request.preview.json']
    sources += [p.q.P / 'frame_fifo_drop' / rev / 'axis_fifo.v' for rev in ('before','after')]
    sources += [Path(j['folder']) / 'result.json' for j in jobs]
    s.dump(out / 'source_bindings.json', {s.rel(path):s.sha(path) for path in sources})
    s.dump(out / 'seal.json', {s.rel(path):s.sha(path) for path in out.rglob('*') if path.is_file()})
    print('PREPARED requests=' + str(len(manifest)) + ' model_calls=0', flush=True)
    return manifest


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out', required=True, type=Path)
    cli.add_argument('--seeds', nargs='+', type=int, default=[19207, 19219])
    cli.add_argument('--prepare-only', action='store_true')
    args = cli.parse_args()
    (prepare if args.prepare_only else campaign)(args.out.resolve(), tuple(args.seeds))
