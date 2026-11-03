"""Terminal-only audit of FIFO stall-release and post-reset output refinement.

Runs on Windows Python or WSL. Writes only RUN/report; never generates models,
executes RTL, changes candidates, or feeds independent results to a model.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import re
import shutil

import research20_report as previous
import research18_report as dedup_tools
import research17_report as base
from research15_acceptance import inspect

ROOT = base.ROOT
read, dump, digest = base.read, base.dump, base.digest
portable = dedup_tools.portable_path
TARGETS = ('stall_stability', 'no_unsolicited_output', 'reset_cancellation')


def terminal(run):
    outcome = read(run / 'outcome.json', {})
    if outcome.get('status') in (None, 'running'):
        raise ValueError('Terminal outcome required; independent results were not read')
    return outcome


def core_summary(run):
    """Retain completed history and unaccepted physical attempts after a stop."""
    summary = read(run / 'core/summary.json')
    if summary is not None:
        return summary
    history = read(run / 'core/history.json', [])
    completed = {item['iteration'] for item in history}
    result = dict(history=list(history), stages=[], resolved=False,
        summary_status='not_written_before_termination',
        history_origin='Archived core/history.json; pending attempt entries below are report-only observations.')
    for folder in sorted((run / 'core').glob('v*'), key=lambda p:int(p.name[1:])):
        iteration = int(folder.name[1:])
        if iteration in completed or not (folder/'model_call/attempt.json').is_file():
            continue
        call = read(folder/'model_call/result.json', {})
        result['history'].append(dict(iteration=iteration,
            requested_obligations=[call.get('requested_obligation')], coverage_only=False, call=call,
            decision=dict(accepted=None, gate_enforced=None,
                reasons=[dict(kind='no_completed_acceptance_decision_before_termination')]),
            before=None, after=None, target_keys=[], report_only_incomplete_attempt=True,
            native_partial_directory=(folder/'native').is_dir()))
    result['history'].sort(key=lambda item:item['iteration'])
    return result


def trace_audit(run, summary, current_run=False):
    """Reuse replay audit, additionally check the actual research21 assembler."""
    result = previous.model_trace_audit(run, summary)
    if current_run:
        protocol = read(run / 'protocol.json', {})
        compact = bool(protocol.get('compact_feedback'))
        if protocol.get('boundary_replace'):
            from research26_model import replace_one as assemble
            assembler_module = 'research26_model.replace_one (model-owned single-property replacement)'
        elif compact:
            # The compact adapter changes requests only; RemoteModel.call uses
            # the unchanged research20_model assembler.
            from research20_model import assemble
            assembler_module = 'research20_model (compact/structured-local presentation adapter)'
        else:
            from research21_model import assemble
            assembler_module = 'research21_model'
        current = read(run / 'shared_initial.json')
        checks = []
        for item in result['records']:
            exact, error = None, None
            if item['edit'] is not None and item['candidate'] is not None:
                try:
                    exact = assemble(item['edit'], current) == item['candidate']
                except Exception as exc:
                    exact, error = False, repr(exc)
            checks.append(dict(version=item['version'], exact=exact, error=error,
                accepted=item['accepted']))
            if item['accepted']:
                item['accepted_integrity_passed'] = bool(item['accepted_integrity_passed'] and exact)
                current = item['candidate']
        result['research21_assembler'] = dict(checks=checks,
            module=assembler_module,
            passed=all(c['exact'] is True for c in checks if c['accepted'])
                if any(c['accepted'] for c in checks) else None,
            scope='Exact generic assembly of the saved real edit; no semantic rewriting.')
        accepted = [i for i in result['records'] if i['accepted']]
        result['accepted_integrity_passed'] = all(i['accepted_integrity_passed'] for i in accepted) if accepted else None
    return result


def lineage(run, seen=()):
    """Audit arbitrarily nested accepted-core sources using development only."""
    run = run.resolve()
    if run in seen or len(seen) >= 20 or ROOT not in run.parents:
        raise ValueError('Unsafe/cyclic accepted-core provenance')
    outcome = terminal(run)
    archive = read(run / 'reused_core_source.json')
    if archive is None:
        initial = previous.audit19.initial_audit(run)
        expression = previous.initial_expression_audit(run)
        return dict(run=run.relative_to(ROOT).as_posix(), passed=bool(initial['passed'] and expression['passed']),
            generation_origin='real_initial_generation', initial=initial, expression=expression,
            linked_source=None, source_independent_read=False, source_file_checks=[])
    source = portable(archive['source']).resolve()
    if ROOT not in source.parents or source == run or not source.is_dir():
        raise ValueError('Invalid accepted-core source')
    terminal(source)
    checks = []
    for rel, expected in archive.get('files', {}).items():
        path = (source / rel).resolve()
        if source not in path.parents or any(p in ('core_independent', 'report') for p in path.relative_to(source).parts):
            raise ValueError('Independent/report data cannot be a model continuation input')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=path.relative_to(ROOT).as_posix(), expected=expected, actual=actual, passed=actual == expected))
    frozen = read(source / 'core/frozen_candidate.json')
    freeze = read(source / 'core/freeze.json', {})
    stamp = read(run / 'shared_initial_freeze.json', {})
    sha = base.candidate_sha(frozen) if frozen is not None else None
    identities = dict(files=bool(checks) and all(c['passed'] for c in checks),
        source_freeze=archive.get('source_freeze') == freeze,
        source_initial_freeze=archive.get('source_initial_freeze') == read(source / 'shared_initial_freeze.json'),
        frozen_hash=sha is not None and sha == freeze.get('candidate_sha256'),
        current_start=read(run / 'shared_initial.json') == frozen,
        current_hash=sha is not None and stamp.get('hash') == sha,
        current_origin=portable(stamp.get('origin', '')).resolve() == source / 'core',
        explicitly_reused=stamp.get('reused_accepted_set') is True)
    parent = lineage(source, (*seen, run))
    source_trace = trace_audit(source, read(source / 'core/summary.json', {}),
        current_run=(source / 'source_snapshot/research21_model.py').is_file()
            or (source / 'source_snapshot/scripts/research21_model.py').is_file())
    trace_ok = source_trace['accepted_integrity_passed'] is not False and source_trace['final_candidate_equals_last_accepted']
    return dict(run=run.relative_to(ROOT).as_posix(), outcome=outcome,
        passed=bool(all(identities.values()) and parent['passed'] and trace_ok),
        generation_origin='reused_accepted_source_core', source=source.relative_to(ROOT).as_posix(),
        identity_checks=identities, source_file_checks=checks, source_model_trace=source_trace,
        linked_source=parent, source_independent_read=False,
        scope='Recursively verified genuine initial/edit lineage from hashed development records. Explicitly promoted public tests are tracked separately in development provenance. No new initial call credit.')


def source_checks(record):
    result = list(record.get('source_file_checks', []))
    if record.get('linked_source'):
        result.extend(source_checks(record['linked_source']))
    return result


def development_provenance(run):
    """Validate explicit public-test promotion and payload-only perturbation."""
    records, file_checks = [], []
    for case in read(run / 'development_plan.json', []):
        origin = case.get('provenance')
        if not origin:
            continue
        identities = {}
        for field, digest_field in (('source_case', 'source_sha256'), ('source_oracle', 'source_oracle_sha256')):
            if field not in origin:
                continue
            path = portable(origin[field]).resolve()
            if ROOT not in path.parents:
                raise ValueError('Unsafe development provenance path')
            expected = origin.get(digest_field)
            actual = digest(path) if path.is_file() else None
            record = dict(path=path.relative_to(ROOT).as_posix(), expected=expected, actual=actual, passed=actual == expected)
            identities[field] = record['passed']; file_checks.append(record)
        source = read(portable(origin.get('source_case', '')), {})
        reconstructed = json.loads(json.dumps(source.get('rows', [])))
        changes_valid = True
        for change in origin.get('row_changes', []):
            rows = [row for row in reconstructed if row.get('cycle') == change.get('cycle')]
            if len(rows) != 1 or rows[0].get(change.get('field')) != change.get('before'):
                changes_valid = False; continue
            rows[0][change['field']] = change.get('after')
        identities['declared_changes_exact'] = bool(changes_valid and reconstructed == case.get('rows'))
        identities['parameters_unchanged'] = all(case.get(k) == source.get(k) for k in ('depth','pipeline','mode'))
        records.append(dict(case=case['id'], source=case.get('source'), provenance=origin,
            passed=bool(identities) and all(identities.values()), checks=identities))
    return dict(passed=bool(records) and all(r['passed'] for r in records), records=records, file_checks=file_checks,
        scope='Public research20 tests are explicitly development now; changed zero-payload input is re-executed, not reclassified as independent.')


def prompt_evidence_audit(run):
    """Read development requests only, checking supplied values against source.

    Safe during an active run: no independent paths are traversed, no generation
    or candidate changes occur. A null window is retained as missing evidence,
    even when a complete archived development trace could supply that sample.
    """
    requests, replay_cache = [], {}
    for request_path in sorted((run / 'core').glob('v*/model_call/request.json')):
        request = read(request_path, {})
        response_format = request.get('format', request.get('response_format'))
        property_schema = ((response_format.get('properties',{}).get('assertions',{}).get('items',{})
            .get('properties',{}).get('property',{})) if isinstance(response_format,dict) else {})
        lexical_pattern_match = False
        lexical_shape = None
        lexical_names = []
        if 'pattern' in property_schema:
            import research17_model as model_interface
            lexical_names = list(model_interface.SIGNALS) + ['$past','$stable','$rose','$fell',
                '$changed','$isunknown','$unsigned','$signed']
            expected_pattern = '^('+'|'.join(re.escape(n) for n in lexical_names)+r'|[0-9]+|[ ()!<>=&|,+*/%?:.\-\[\]])+$'
            expression = '('+'|'.join(re.escape(n) for n in lexical_names)+r'|[0-9]+|&&|\|\||==|!=|<=|>=|[ ()!<>,+*/%?:.\-\[\]])+'
            implication_pattern = '^'+expression+r'(\|->|\|=>)'+expression+'$'
            backend_expression = '('+'|'.join(re.escape(n) for n in lexical_names)+r'|[0-9]+|&&|\|\||==|!=|<=|>=|-|[ ()!<>,+*/%?:.])+'
            backend_pattern = '^'+backend_expression+r'(\|->|\|=>)'+backend_expression+'$'
            actual_pattern = property_schema['pattern']
            lexical_pattern_match = actual_pattern in (expected_pattern, implication_pattern, backend_pattern)
            lexical_shape = ('exactly_one_native_implication_no_escaped_character_class' if actual_pattern==backend_pattern else
                'exactly_one_native_implication_between_token_expressions' if actual_pattern==implication_pattern
                else 'token_sequence' if actual_pattern==expected_pattern else 'unclassified')
        constraint_kind = ('fixed_string_choices' if any(k in property_schema for k in ('enum','const')) else
            'lexical_token_allowlist' if lexical_pattern_match else
            'other_string_pattern_not_classified' if 'pattern' in property_schema else
            'free_property_string' if property_schema.get('type')=='string' else 'not_recorded')
        schema_observation = dict(format=response_format,
            schema_constrains_structure=isinstance(response_format,dict) and response_format.get('type')=='object',
            property_is_free_string=(property_schema.get('type')=='string'
                and not any(k in property_schema for k in ('enum','const','pattern'))) if property_schema else None,
            property_constraint_kind=constraint_kind,
            lexical_token_pattern_verified=lexical_pattern_match,
            lexical_expression_shape=lexical_shape,
            lexical_allowed_identifiers=lexical_names if lexical_pattern_match else [],
            lexical_other_tokens='Decimal constants and syntactic operator/punctuation characters' if lexical_pattern_match else None,
            concrete_predicate_or_timing_supplied_by_schema=constraint_kind=='fixed_string_choices'
                if constraint_kind!='other_string_pattern_not_classified' else None,
            backend_execution='Not established by inspecting a Python/JSON regex; service grammar parsing must be audited separately.',
            note='A verified token allowlist constrains names/functions/constants/punctuation, not an assertion answer. Predicate, implication and applicability remain model choices; native compiler and evidence gate still decide validity. An unclassified pattern remains unknown.')
        messages = request.get('messages', [])
        payloads = []
        for index, message in enumerate(messages):
            try:
                value = json.loads(message.get('content', ''))
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict):
                payloads.append((index,value))
        contexts = [(index,payload) for index,payload in payloads if 'rtl_and_common_contract' in payload]
        if not contexts:
            continue
        if len(contexts) != 1:
            raise ValueError('Exactly one RTL/context payload required')
        context_index, payload = contexts[0]
        compact_tasks = [(index,value['boundary_repair']) for index,value in payloads if 'boundary_repair' in value]
        fresh_tasks = [(index,value['fresh_obligation_synthesis']) for index,value in payloads if 'fresh_obligation_synthesis' in value]
        if fresh_tasks:
            if len(fresh_tasks) != 1:
                raise ValueError('Exactly one fresh synthesis task required')
            task_index, task = fresh_tasks[0]
            feedback = dict(selection='First actual unresolved development event per empty/nonempty current queue boundary.')
            pairs = [dict(scenario=p['scenario'],cycle=p['event']['cycle'],target_evidence=p['event'],
                mutant=dict(adjacent_samples=p['faulty_samples'],full_trace_provenance=p['source']),
                fixed=dict(adjacent_samples=p['correct_samples'],full_trace_provenance=p['control_source']))
                for p in task.get('observations',[])]
            schema = 'fresh_obligation_synthesis'
        elif compact_tasks:
            if len(compact_tasks) != 1:
                raise ValueError('Exactly one compact boundary task required')
            task_index, task = compact_tasks[0]
            feedback = dict(selection=task.get('projection'))
            pairs = task.get('actual_observations', [])
            schema = 'compact_boundary_repair'
        else:
            task_index = context_index
            feedback = payload.get('requested_work', {}).get('actual_feedback', {})
            pairs = feedback.get('paired_target_samples', [])
            schema = 'full_requested_work'
            task = payload.get('requested_work',{})
        labels = ((response_format.get('properties',{}).get('assertions',{}).get('items',{})
            .get('properties',{}).get('obligation',{})) if isinstance(response_format,dict) else {})
        requested = list(task.get('requested_obligations', []))
        schema_observation['obligation_labels'] = dict(schema=labels,requested=requested,
            fixed_to_requested_task_set=bool(requested and labels.get('type')=='array'
                and labels.get('minItems')==len(requested) and labels.get('maxItems')==len(requested)
                and labels.get('uniqueItems') is True and set(labels.get('items',{}).get('enum',[]))==set(requested)),
            scope='Task labels can be fixed by the schema, not independently generated protection claims. Only native triggers and detections establish observed coverage.')
        reviews = [(index,payload) for index,payload in payloads if 'observed_examples' in payload]
        expected_review = [dict(scenario=p['scenario'],violation_cycle=p['cycle'],
            independent_judgment=p['target_evidence'],faulty_samples=p['mutant']['adjacent_samples'],
            correct_samples=p['fixed']['adjacent_samples'],native_markers=p['mutant'].get('adjacent_native_markers')) for p in pairs]
        review_checks = [dict(message_index=index,precedes_rtl=index<context_index,
            exactly_projects_context=value['observed_examples']==expected_review) for index,value in reviews]
        checks, ranks = [], []
        for pair in pairs:
            cycle = pair['cycle']; target = pair['target_evidence']['obligation']
            sample = pair.get('mutant', {}).get('sample') or next((s for s in pair.get('mutant',{}).get('adjacent_samples',[])
                if s is not None and s.get('cycle')==cycle), {})
            ranks.append((pair['target_evidence'].get('gap_observation') == 'detected',
                not (sample.get('mready') == 1 if target == 'stall_stability' else sample.get('mdata') == 0)))
            for side in ('fixed', 'mutant'):
                card = pair[side]; origin = card.get('source', {})
                full_provenance = card.get('full_trace_provenance')
                trace_path = portable(origin.get('reference_trace') or (full_provenance or {}).get('path','')).resolve()
                folder = portable(origin['directory']).resolve() if origin.get('directory') else trace_path.parent
                if (run / 'core').resolve() not in folder.parents or trace_path != folder / 'reference_trace.json':
                    raise ValueError('Prompt sample source must be exact current-run development trace')
                replay_folder = folder.parent.parent
                if replay_folder not in replay_cache:
                    replay_cache[replay_folder] = read(replay_folder / 'result.json', {})
                original_entry = next((e for e in replay_cache[replay_folder].get('feedback', [])
                    if e.get('scenario') == pair['scenario']), {})
                original_targets = original_entry.get('diagnostic', {}).get('target_evidence', [])
                target_faithful = pair['target_evidence'] in original_targets
                trace = {s['cycle']:s for s in read(trace_path, [])}
                full_provenance_match = None if full_provenance is None else bool(
                    full_provenance.get('status') == 'actual_development_trace'
                    and portable(full_provenance.get('path','')).resolve() == trace_path
                    and full_provenance.get('sha256') == digest(trace_path))
                native = read(folder / 'result.json', {})
                observed = {}
                for field in ('triggers','failures'):
                    observed[field] = {(item.get('id'), int(match.group(1))) for item in native.get(field, [])
                        if (match := re.search(r'cycle=(\d+)', item.get('detail', '')))}
                marker_checks = []
                for marker in card.get('adjacent_native_markers', []):
                    for prop in marker.get('properties', []):
                        for field, native_field in (('triggered','triggers'),('failed','failures')):
                            value = prop.get(field)
                            marker_checks.append(value is None or value == ((prop.get('id'), marker['cycle']) in observed[native_field]))
                samples = card.get('adjacent_samples', [])
                end_cycle = cycle+1 if schema=='fresh_obligation_synthesis' else cycle+2
                expected = [trace.get(c) for c in range(cycle-1, end_cycle)]
                provided = [s is not None for s in samples]
                matches = [s is None or s == e for s,e in zip(samples,expected)]
                checks.append(dict(scenario=pair['scenario'],cycle=cycle,side=side,
                    gap=pair['target_evidence'].get('gap_observation'),
                    source_trace=trace_path.relative_to(ROOT).as_posix(),source_sha256=digest(trace_path),
                    native_result_sha256=digest(folder/'result.json'),
                    full_trace_provenance=full_provenance, full_trace_provenance_matches=full_provenance_match,
                    target_evidence_matches_diagnostic=target_faithful,
                    adjacent_cycles=list(range(cycle-1,end_cycle)),provided=provided,
                    raw_samples_available=[s is not None for s in expected],
                    omitted_but_in_raw=sum(s is None and e is not None for s,e in zip(samples,expected)),
                    supplied_samples_match_raw=bool(len(samples)==len(expected) and all(matches)),
                    center_sample_match=card.get('sample') is None or card['sample']==trace.get(cycle),
                    native_markers_present='adjacent_native_markers' in card,
                    native_marker_values_match=all(marker_checks) if 'adjacent_native_markers' in card else None,
                    omitted_native_markers='Not sent in compact prompt; source result remains separately available' if schema=='compact_boundary_repair' else None,
                    limitation='Null is unavailable in the prompt, never an invented pass. Raw availability does not make an omitted sample visible to the model.'))
        requests.append(dict(path=request_path.relative_to(run).as_posix(),request_sha256=digest(request_path),
            response_format_audit=schema_observation,
            schema=schema,context_message_index=context_index,task_message_index=task_index,boundary_review_checks=review_checks,
            selection=feedback.get('selection'),rank_keys=ranks,
            ordering_matches_policy=(len({
                next(s for s in p['mutant']['adjacent_samples'] if s and s['cycle']==p['cycle'])['ref_count']>0
                for p in pairs})==len(pairs) if schema=='fresh_obligation_synthesis' else ranks==sorted(ranks)),
            cards=checks,provided_values_faithful=all(c['supplied_samples_match_raw'] and c['center_sample_match']
                and c['native_marker_values_match'] is not False and c['target_evidence_matches_diagnostic']
                and c['full_trace_provenance_matches'] is not False for c in checks)
                and all(c['precedes_rtl'] and c['exactly_projects_context'] for c in review_checks),
            omitted_raw_sample_count=sum(c['omitted_but_in_raw'] for c in checks)))
    return dict(requests=requests, independent_data_read=False,
        faithful=bool(requests) and all(r['provided_values_faithful'] and r['ordering_matches_policy'] for r in requests),
        scope='Actual request content and current-run development trace/native markers only; no retrospective prompt completion.')


def inherited_feedback_audit(run):
    records, checks = [], []
    for archive_path in sorted((run / 'feedback_inheritance').glob('*.json')):
        archive = read(archive_path)
        source = portable(archive['source']).resolve()
        if ROOT not in source.parents or 'core_independent' in source.parts or source.parent.name != 'core':
            raise ValueError('Only prior development proposals may be inherited')
        terminal(source.parent.parent)
        local_checks = []
        for rel, expected in archive.get('files', {}).items():
            path = (source / rel).resolve()
            if source not in path.parents:
                raise ValueError('Unsafe inherited feedback path')
            actual = digest(path) if path.is_file() else None
            item = dict(path=path.relative_to(ROOT).as_posix(),expected=expected,actual=actual,passed=actual==expected)
            local_checks.append(item); checks.append(item)
        folder = source / 'model_call'
        raw, provenance = previous.response_artifact(folder)
        try:
            parsed = json.loads(raw)
        except (ValueError,TypeError):
            parsed = None
        decision = read(source/'decision.json', {})
        call = read(folder/'result.json', {})
        passed = bool(local_checks and all(c['passed'] for c in local_checks)
            and (folder/'attempt.json').is_file() and call.get('status')=='response_received'
            and provenance['integrity_passed'] and parsed is not None and parsed==read(folder/'model_edit.json')
            and decision.get('accepted') is False)
        records.append(dict(archive=archive_path.relative_to(run).as_posix(),source=source.relative_to(ROOT).as_posix(),
            passed=passed,source_decision=decision,source_call=call,response_provenance=provenance,
            current_generation_calls=0,scope='Prior rejected proposal retained only as diagnostic; no acceptance or new generation credit.'))
    return dict(passed=all(r['passed'] for r in records),records=records,file_checks=checks)


def backend_support_audit(run):
    """Separate received service text from actual grammar support evidence."""
    calls = []
    for path in sorted((run/'core').glob('v*/model_call/attempt.json')):
        call = path.parent
        result = read(call/'result.json',{})
        audit = read(call/'backend_audit.json')
        log = call/'backend.log'
        raw, provenance = previous.response_artifact(call)
        local_raw = read(call/'response.raw.json',{})
        complete = bool(provenance.get('terminal_marker_observed')) if provenance.get('remote_reconstruction') else bool(
            local_raw.get('done',(local_raw.get('service_done') or {}).get('done')))
        actual_errors, valid = [], None
        if audit is not None:
            if log.is_file():
                content = log.read_bytes()
                actual_errors = [line for line in content.decode(errors='replace').splitlines()
                    if 'error parsing grammar' in line or 'failed to parse grammar' in line]
                valid = bool(digest(log)==audit.get('sha256') and len(content)==audit.get('bytes')
                    and actual_errors==audit.get('errors'))
            else:
                valid = False
        calls.append(dict(path=call.relative_to(run).as_posix(),recorded_status=result.get('status'),
            candidate_status=result.get('candidate_status'),service_response_complete=complete,
            response_characters=len(raw) if isinstance(raw,str) else None,
            backend_status=(audit or {}).get('status','not_recorded_per_call'),
            backend_audit=audit,backend_audit_integrity=valid,backend_errors=actual_errors,
            accepted_support_permitted=bool(audit and valid and audit.get('status')=='no_backend_grammar_error_observed')
                if audit is not None else None))
    diagnosis = read(run/'backend_grammar_diagnosis.json')
    linked = []
    diagnosis_checks=[]
    if diagnosis:
        value = diagnosis.get('source_log',diagnosis.get('log'))
        if value:
            path = portable(value).resolve()
            if ROOT not in path.parents or not path.is_file():
                raise ValueError('Existing workspace backend diagnostic log required')
            linked.append(dict(path=path.relative_to(ROOT).as_posix(),expected=digest(path),
                scope='Whole log hash captured at report generation after owning service shutdown.'))
            import hashlib
            log_bytes=path.read_bytes()
            if 'source_prefix_bytes' in diagnosis:
                diagnosis_checks.append(dict(kind='log_prefix',passed=hashlib.sha256(log_bytes[:diagnosis['source_prefix_bytes']]).hexdigest()==diagnosis['source_prefix_sha256']))
            for item in diagnosis.get('calls',[]):
                segment=log_bytes[item['source_byte_start']:item['source_byte_end']]
                diagnosis_checks.append(dict(kind='call_segment',call=item['path'],
                    passed=hashlib.sha256(segment).hexdigest()==item['segment_sha256']
                        and segment.decode(errors='replace')==item['segment_text']))
                source=(run/item['path']).resolve()
                if run not in source.parents:
                    raise ValueError('Unsafe historical call source')
                diagnosis_checks.extend(dict(kind='unchanged_original',call=item['path'],file=name,
                    passed=(source/name).is_file() and digest(source/name)==expected)
                    for name,expected in item.get('original_record_hashes',{}).items())
    return dict(calls=calls,posthoc_diagnosis=diagnosis,linked_log_checks=linked,
        posthoc_diagnosis_checks=diagnosis_checks,
        posthoc_diagnosis_integrity=all(c['passed'] for c in diagnosis_checks) if diagnosis else None,
        service_complete_responses=sum(c['service_response_complete'] for c in calls),
        backend_failures=sum(c['backend_status']=='unsupported' for c in calls),
        scope='Offline pattern/schema inspection does not establish backend grammar execution. Grammar failure plus returned text is a backend limitation, not solely a model reasoning failure. No-error observation is finite diagnostic evidence, not a proof of all schema support.')


def diagnose_historical_backend(run, log_path):
    """Append a posthoc diagnosis, preserving original responses and results.

    Match each rejected JSON response to the service's ordered failed-grammar
    segment using completion second, prompt tokens and generated tokens. Log
    timestamps are explicitly Asia/Shanghai; returned timestamps are UTC.
    Only the immutable prefix ending at the matched completion is hashed, as
    the owned service may still be appending unrelated later requests.
    """
    terminal(run)
    target = run/'backend_grammar_diagnosis.json'
    if target.exists():
        raise ValueError('Diagnosis already exists; preserve the historical record')
    raw = log_path.read_bytes(); lines = raw.splitlines(keepends=True)
    starts = [i for i,line in enumerate(lines) if b'error parsing grammar' in line]
    offsets=[0]
    for line in lines: offsets.append(offsets[-1]+len(line))
    segments=[]
    for start in starts:
        end=next((i for i in range(start,len(lines)) if b'[GIN]' in lines[i] and b'"/api/chat"' in lines[i]),None)
        if end is None: continue
        segment=b''.join(lines[start:end+1]); text=segment.decode(errors='replace')
        timestamp=re.search(r'\[GIN\] (\d{4}/\d\d/\d\d - \d\d:\d\d:\d\d)',lines[end].decode(errors='replace'))
        if not timestamp: continue
        completed=datetime.datetime.strptime(timestamp.group(1),'%Y/%m/%d - %H:%M:%S').replace(
            tzinfo=datetime.timezone(datetime.timedelta(hours=8))).astimezone(datetime.timezone.utc)
        prompt=re.search(r'new prompt, .*task.n_tokens = (\d+)',text)
        generated=re.search(r'\|\s+eval time =\s+[\d.]+ ms /\s+(\d+) tokens',text)
        segments.append(dict(start=start,end=end,bytes=segment,text=text,completed=completed,
            prompt=int(prompt.group(1)) if prompt else None,completion=int(generated.group(1)) if generated else None))
    import hashlib
    calls=[]
    for attempt in sorted((run/'core').glob('v*/model_call/attempt.json')):
        call=attempt.parent;result=read(call/'result.json',{});response=read(call/'response.raw.json',{})
        done=response.get('service_done',response)
        value=done.get('created_at')
        if not value: continue
        completed=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
        candidates=[s for s in segments if abs((s['completed']-completed).total_seconds())<1.1
            and s['prompt']==result.get('prompt_tokens') and s['completion']==result.get('completion_tokens')]
        if len(candidates)!=1:
            raise ValueError('Backend segment not uniquely matched to '+str(call))
        s=candidates[0];request=read(call/'request.json',{});pattern=request['format']['properties']['assertions']['items']['properties']['property']['pattern']
        errors=[dict(line=i+1,text=lines[i].decode(errors='replace').rstrip('\r\n')) for i in range(s['start'],s['end']+1)
            if b'error parsing grammar' in lines[i] or b'failed to parse grammar' in lines[i]]
        checks=dict(completion_second_matches=abs((s['completed']-completed).total_seconds())<1.1,
            prompt_tokens_match=s['prompt']==result.get('prompt_tokens'),
            completion_tokens_match=s['completion']==result.get('completion_tokens'),
            failed_to_parse_grammar=any('failed to parse grammar' in e['text'] for e in errors),
            request_contains_unsupported_escape=all(token in pattern for token in (r'\-',r'\[',r'\]')),
            response_received=result.get('status')=='response_received',
            original_json_interface_rejected=result.get('candidate_status')=='interface_rejected')
        calls.append(dict(path=call.relative_to(run).as_posix(),association_passed=all(checks.values()),checks=checks,
            started_utc=read(attempt).get('started_utc'),response_created_at=value,
            service_completion_local=lines[s['end']].decode(errors='replace').rstrip('\r\n'),
            service_completion_utc=s['completed'].isoformat(),
            logged_prompt_tokens=s['prompt'],logged_completion_tokens=s['completion'],
            source_line_start=s['start']+1,source_line_end=s['end']+1,
            source_byte_start=offsets[s['start']],source_byte_end=offsets[s['end']+1],
            segment_sha256=hashlib.sha256(s['bytes']).hexdigest(),segment_text=s['text'],errors=errors,
            request_property_pattern=pattern,original_result=result,
            original_record_hashes={p.name:digest(p) for p in (attempt,call/'request.json',call/'result.json',call/'response.raw.json')},
            retrospective_backend_status='unsupported_grammar_parse_failure'))
    if not calls or not all(c['association_passed'] for c in calls):
        raise ValueError('Failed backend association; diagnosis not written')
    end=max(c['source_byte_end'] for c in calls)
    diagnosis=dict(created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_log=log_path.relative_to(ROOT).as_posix(),source_timezone='Asia/Shanghai UTC+08:00',
        source_prefix_bytes=end,source_prefix_sha256=hashlib.sha256(raw[:end]).hexdigest(),calls=calls,
        status='backend_grammar_rejected_but_service_returned_text',
        original_results_unchanged=True,independent_data_read=False,new_model_calls=0,new_native_calls=0,
        conclusion='The requested lexical grammar was not parsed. Returned non-JSON text cannot be attributed solely to model instruction-following; original interface rejection remains unchanged. Unconstrained fallback is an inference from grammar errors, subsequent sampler execution and returned text.',
        scope='Supplementary posthoc diagnostic only. Source records, candidates, acceptance and old costs are not rewritten.')
    dump(target,diagnosis)
    return diagnosis


def replay_projection(folder, independent=False):
    record = read(folder / ('independent_ledger.json' if independent else 'result.json'), {})
    group = record if independent else record.get('group', {})
    if not group.get('ledger'):
        return dict(status='not_executed', counts=None, boundaries=None)
    counts = dedup_tools.deduplicated_counts(group, folder)
    return dict(status='executed', counts=counts, boundaries=boundary_projection(group, folder),
        healthy=record.get('healthy'), directory=str(folder))


def independent_separation_audit(run):
    split_path=run/'core_independent/split.json'
    split=read(split_path)
    freeze=read(run/'core/freeze.json',{})
    if split is None:
        return dict(status='not_executed',passed=False)
    fingerprint=lambda case:base.candidate_sha({k:case[k] for k in ('depth','pipeline','rows')})
    dev_hashes={fingerprint(c) for c in read(run/'development_plan.json',[])}
    cases=split.get('cases',[])
    duplicate=[c['id'] for c in cases if fingerprint(c) in dev_hashes]
    references=[];last_model_complete=None
    for request in (run/'core').glob('v*/model_call/request.json'):
        text=request.read_text(encoding='utf-8')
        matches=[c['id'] for c in cases if c['id'] in text]
        if 'core_independent' in text or matches:
            references.append(dict(request=request.relative_to(run).as_posix(),test_ids=matches,independent_path='core_independent' in text))
        raw=read(request.parent/'response.raw.json',{})
        created=(raw.get('service_done') or raw).get('created_at')
        if created:
            value=datetime.datetime.fromisoformat(created.replace('Z','+00:00'))
            last_model_complete=max(last_model_complete,value) if last_model_complete else value
    frozen=datetime.datetime.fromisoformat(freeze['utc'].replace('Z','+00:00')) if freeze.get('utc') else None
    split_mtime=datetime.datetime.fromtimestamp(split_path.stat().st_mtime,tz=datetime.timezone.utc)
    checks=dict(declared_post_freeze=split.get('created_after_freeze') is True,
        no_exact_development_inputs=bool(cases) and not duplicate,no_independent_references_in_requests=not references,
        split_file_not_before_freeze=bool(frozen and split_mtime>=frozen),
        final_model_response_before_freeze=(last_model_complete<=frozen) if last_model_complete and frozen else None)
    return dict(status='checked',passed=all(v is not False and v is not None for k,v in checks.items()
        if k!='final_model_response_before_freeze') and checks['final_model_response_before_freeze'] is not False,
        checks=checks,freeze_utc=freeze.get('utc'),split_file_mtime_utc=split_mtime.isoformat(),
        last_local_response_utc=last_model_complete.isoformat() if last_model_complete else None,
        new_case_count=len(cases),new_unique_input_count=len({fingerprint(c) for c in cases}),
        duplicated_development_case_ids=duplicate,forbidden_request_references=references,
        seeds=split.get('seeds'),parameters=split.get('parameters'),
        limits='Saved freeze, local file chronology and actual request/input comparison. Filesystem times are not external trusted timestamps; unavailable remote completion timestamps remain unavailable.')


def boundary_projection(group, folder):
    """Reconstruct real release-edge rows; never infer correctness from SVA."""
    info = inspect(group.get('ledger', []))
    cases = {c['id']: c for p in folder.glob('case_*/case.json') if (c := read(p))}
    traces, seen, rows = {}, set(), []
    resolved_folder = folder.resolve()
    resolved_sources = {}
    for eid, row in info['rows'].items():
        if row.get('obligation') not in TARGETS:
            continue
        source_directory = row.get('source_directory', '')
        if source_directory not in resolved_sources:
            resolved_sources[source_directory] = portable(source_directory).resolve()
        path = resolved_sources[source_directory]
        if resolved_folder not in path.parents:
            continue
        if path not in traces:
            traces[path] = {s['cycle']: s for s in read(path / 'reference_trace.json', [])}
        cycle = row.get('cycle'); samples = traces[path]
        now, prev = samples.get(cycle), samples.get(cycle - 1)
        boundary = None
        if row['obligation'] == 'stall_stability' and prev and now and prev.get('mvalid') and not prev.get('mready'):
            boundary = 'stall_release' if now.get('mready') else 'continued_stall'
        elif row['obligation'] in ('no_unsolicited_output', 'reset_cancellation'):
            boundary = 'post_reset_output' if row.get('variant') == 'reset_residue' else 'other_unsolicited'
        if boundary is None:
            continue
        case = cases.get(row.get('scenario_id'))
        stimulus = base.candidate_sha({k: case[k] for k in ('depth', 'pipeline', 'rows')}) if case else row.get('stimulus_sha256')
        key = (stimulus, row.get('variant'), row.get('epoch'), cycle, row['obligation'])
        if key in seen:
            continue
        seen.add(key)
        fields = {k: eid in info[k] for k in ('detections', 'misses', 'false_positives', 'unknown', 'triggers')}
        rows.append(dict(evidence_id=eid, boundary=boundary, obligation=row['obligation'],
            scenario=row.get('scenario_id'), cycle=cycle, epoch=row.get('epoch'), variant=row.get('variant'),
            oracle=row.get('oracle'), independent_violation=row.get('oracle_violation'),
            native=row.get('native'), status=fields, samples=[s for s in (prev, now) if s],
            parameters={k: case[k] for k in ('depth', 'pipeline')} if case else None))
    by = {}
    for label in ('stall_release', 'continued_stall', 'post_reset_output', 'other_unsolicited'):
        selected = [r for r in rows if r['boundary'] == label]
        by[label] = dict(rows=len(selected), target_rows=sum(r['oracle'].get('verdict') == 'violated' for r in selected),
            **{k: sum(r['status'][k] for r in selected) for k in ('detections', 'misses', 'false_positives', 'unknown', 'triggers')})
    return dict(by_boundary=by, target_examples=[r for r in rows if r['oracle'].get('verdict') == 'violated'],
        note='Diagnostic projection of recorded samples. Full counts use strict duplicate-conflict handling; reset labels may share an event.')


def table(lines, label, projection):
    lines += ['', label, '']
    if projection['status'] != 'executed':
        lines += ['未执行；不作零误报或通过结论。']; return
    c = projection['counts']
    lines += ['| 义务 | 目标违例行 | 检出 | 漏报 | 误报 | unknown | 触发 |', '|---|---:|---:|---:|---:|---:|---:|']
    for ob, vals in c['by_obligation'].items():
        lines += [f'| {ob} | ' + ' | '.join(str(vals[k]) for k in ('target_oracle_rows', 'detections', 'misses', 'false_positives', 'unknown', 'triggers')) + ' |']
    lines += ['', f"原始 {c['raw_rows']} 行；实际输入去重后 {c['unique_rows']} 行；后续归因 unknown {c['later_attribution_unknown_raw']} 条单列。", '',
        '| 具体边界 | 目标行 | 检出 | 漏报 | 误报 | unknown |', '|---|---:|---:|---:|---:|---:|']
    for label, vals in projection['boundaries']['by_boundary'].items():
        lines += [f'| {label} | ' + ' | '.join(str(vals[k]) for k in ('target_rows', 'detections', 'misses', 'false_positives', 'unknown')) + ' |']
    lines += ['', '边界表是采样诊断投影；无目标分母不能视为保护完成，复位同一事件可关联两项义务。']


def render(run, data):
    lines = ['# 背压解除边界与复位后输出：终态实验证据', '',
        f"运行终态 `{data['status']}`；本轮新目标链通过 `{data['target_chain']['passed']}`；完整父案例通过 **未建立**。", '',
        '初始集合继承已冻结真实模型产物，本轮没有重新生成初始 SVA。只将本轮实际新请求、原生执行及接受编辑记作本轮成果。'
        '真实 axis_fifo RTL 上注入明确工程输出故障；不追认为原始 FIFO presented 历史修复。', '',
        '本轮只针对背压解除当拍稳定性及复位后无请求输出。记录范围通过不等于规范等价、完整五义务保护、形式证明或全局无退化；'
        'stat 与原始 FIFO presented 仍 unknown；没有新增四组消融结论。', '',
        '背压新增性质只检查下一拍数据保持时，不自动保护 valid 必须保持；复位性质若使用 $past(ref_count > 0)，'
        '只获得实际回放范围支持，不等于当前拍存在未取消事务的规范等价表达。独立漏报如实保留。', '',
        'research20 已公开独立测试从本轮起作为开发数据；被选中的旧解除背压输入已明确转入开发集。'
        '它们不再算本轮独立结果。零 payload 开发扰动保留原来源与准确字段差异，按新原生执行确认功能含义。', '',
        f"递归来源核验 `{data['lineage']['passed']}`；模型原文/组装核验 `{data['trace']['accepted_integrity_passed']}`；"
        f"最终集合等于最后接受版本 `{data['trace']['final_candidate_equals_last_accepted']}`。", '',
        f"开发来源、公开旧测试转入及声明输入改动核验 `{data['development_provenance']['passed']}`。", '',
        f"实际提示词样本及原生marker忠实性核验 `{data['prompt_evidence']['faithful']}`。"
        '未提供的控制样本仍按缺失记录；原始轨迹存在不代表模型当时看到了。', '',
        '实际请求中的性质约束类型：`' + str(sorted({r.get('response_format_audit',{}).get('property_constraint_kind','not_recorded')
            for r in data['prompt_evidence']['requests']})) + '`。'
        'free_property_string 表示结构 schema 内自由表达式；lexical_token_allowlist 仅限制真实接口名、函数、数字及运算符。'
        '有些真实请求另外要求表达式之间恰一处 |-> 或 |=>，模型仍选择其一及两侧谓词；不等于编译通过。'
        '若义务标签被 schema 固定为任务集合，明确不把标签视为模型自主选择或保护证据。', '',
        '离线正则/结构检查通过不表示服务执行了该约束。后端 grammar 错误、完整响应、接口解析和原生 SVA 状态分别报告；'
        '约束解析失败后的非 JSON 文本不能仅归因于模型推理失败。', '',
        f"继承失败提案的来源核验 `{data['inherited_feedback']['passed']}`，共 {len(data['inherited_feedback']['records'])} 条；"
        '旧拒绝仍为拒绝，引用它不增加本轮生成次数，也不替代本轮重新执行。', '',
        '## 初始与冻结集合', '', '初始（来源已接受集合）：', '```systemverilog']
    lines += [a['property'] for a in (data['initial_candidate'] or {}).get('assertions', [])] + ['```', '', '最终冻结：']
    if data['final_candidate']:
        lines += ['```systemverilog'] + [a['property'] for a in data['final_candidate']['assertions']] + ['```']
    else:
        lines += ['未生成最终冻结集合。已停止的部分原生回放不能作为验收通过或独立结果。']
    lines += ['',
        '冻结与测试使用哈希：', '```json', json.dumps(data['freeze_checks'], ensure_ascii=False, indent=2), '```', '',
        '## 真实模型修改轨迹']
    for item in data['trace']['records']:
        h = item['history']; call = item['call']
        lines += ['', f"### {item['version']}", '',
            f"实际请求 `{item['generation_attempt_present']}`；服务状态 `{call.get('status')}`；接口状态 `{call.get('candidate_status')}`；"
            f"完整原生汇总 `{item['native_result_present']}`；接受 `{h.get('decision',{}).get('accepted')}`。", '',
            '原始模型 JSON（拒绝提案也原样保留）：', '```json', json.dumps(item['edit'], ensure_ascii=False, indent=2), '```']
        if item['candidate']:
            lines += ['', '实际组装的候选集合：', '```systemverilog'] + [a['property'] for a in item['candidate']['assertions']] + ['```']
        else:
            lines += ['', '未形成可执行候选；不人工修正或代写表达式。']
        if h.get('report_only_incomplete_attempt'):
            lines += ['', '真实模型响应和 usage 已落盘，但原生回放/接受决策未完成；本条来自物理 attempt，'
                '不是补造的历史验收。全部已发生成本照计，候选不计接受。']
        lines += ['', '接受／拒绝记录：', '```json', json.dumps(h.get('decision'), ensure_ascii=False, indent=2), '```',
            f"接口诊断：`{call.get('candidate_error')}`。历史回放前 `{h.get('before')}`；后 `{h.get('after')}`。",
            f"原始 SSE/响应来源核验 `{item['response_provenance']['integrity_passed']}`，模型 JSON 等于编辑 `{item['raw_json_matches_saved_edit']}`；"
            f"仅语法组装一致 `{item['candidate_equals_model_edit_assembly']}`。"]
    lines += ['', '## 模型服务约束执行状态', '',
        '| 调用 | 收到完整服务响应 | 后端 grammar 状态 | 后端日志核验 | 接口状态 |',
        '|---|---|---|---|---|']
    for call in data['backend_support']['calls']:
        lines += [f"| {call['path']} | {call['service_response_complete']} | {call['backend_status']} | "
            f"{call['backend_audit_integrity']} | {call['candidate_status']} |"]
        if call['backend_errors']:
            lines += ['', '后端错误原文：', '```text', '\n'.join(call['backend_errors']), '```', '']
    if data['backend_support']['posthoc_diagnosis']:
        lines += ['', '历史后端诊断（补充证据，不改原调用结果）：', '```json',
            json.dumps(data['backend_support']['posthoc_diagnosis'],ensure_ascii=False,indent=2), '```', '']
    lines += ['', '## 开发历史回放']
    table(lines, '修改前', data['development']['before'])
    table(lines, '最后接受版本', data['development']['after'])
    lines += ['', '有效缺口类（按故障和义务去重）：`' + str(data['missing_evidence']['unique_gap_classes']) + '`。', '',
        '## 冻结后新独立回放', '',
        '本批仅在最终集合冻结后执行；没有反馈给模型或用于候选选择。若以后据此修改，这批须转开发数据。'
        'initial 与 core 是同批输入比较；旧 research20 独立结果不是本轮测试结果。', '',
        '独立划分核验：', '```json',json.dumps(data['independent_separation'],ensure_ascii=False,indent=2),'```']
    for name, projection in data['independent_projections'].items():
        table(lines, name, projection)
    lines += ['', '## 具体边界实例', '']
    for phase, projection in [('开发修改前', data['development']['before']), ('独立冻结后', data['independent_projections'].get('core', {'status':'not_executed'}))]:
        if projection['status'] != 'executed':
            continue
        examples = projection['boundaries']['target_examples']
        for boundary in ('stall_release', 'post_reset_output'):
            selected = [e for e in examples if e['boundary'] == boundary]
            # Show the actual zero-payload counterexample when present; zero
            # is legal input data and cannot justify an unsolicited response.
            selected.sort(key=lambda e: (not e['status'].get('misses'), boundary == 'post_reset_output'
                and not any(s.get('mvalid') and s.get('mready') and s.get('mdata') == 0 for s in e['samples']),
                e['obligation'] != 'reset_cancellation', e['scenario']))
            example = selected[0] if selected else None
            if example:
                lines += [f'{phase} / {boundary}：', '```json', json.dumps(example, ensure_ascii=False, indent=2), '```', '']
            else:
                lines += [f'{phase} / {boundary}：未记录目标见证，不按成功处理。', '']
    cost = data['cost']['total']
    lines += ['## 实际成本与复查', '',
        f"本轮实际请求 {cost['model_calls']} 次；输入 tokens 已知小计 {cost['prompt_tokens_known_subtotal']}，输出 {cost['completion_tokens_known_subtotal']}；"
        f"usage 缺失 {cost['usage_unavailable_calls']} 次。原生编译 {cost['native_compile_calls']} 次、执行 {cost['native_execute_calls']} 次"
        f"（含 smoke {cost['compile_smoke_execute_calls']}）；形式化 {cost['formal_calls']} 次。",
        '旧来源调用不加到本轮成本；失败请求照计。缺失费用与模型 digest 不伪造。', '', '```powershell',
        (data.get('execution_command') or {}).get('command', '启动命令记录不可用'),
        f'wsl -- python3 scripts/research21_report.py --run {run.relative_to(ROOT).as_posix()}',
        f'wsl -- python3 scripts/research21_report.py --run {run.relative_to(ROOT).as_posix()} --verify', '```', '',
        '重跑实验须换新的输出目录。--verify 仅确认产物与冻结哈希完整性，不代表功能成功。', '']
    linked = data.get('preceding_costs', {})
    if linked.get('preceding_attempts'):
        lines += ['## 此前中止运行成本（单列）', '',
            '| 运行 | 终态 | 实际请求 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | 用量未知 | 编译 | 执行 |',
            '|---|---|---:|---:|---:|---:|---:|---:|']
        for item in linked['preceding_attempts']:
            c = item['cost']['total']
            lines += [f"| {item['path']} | {(item.get('outcome') or {}).get('status')} | " + ' | '.join(str(c[k]) for k in (
                'model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal','usage_unavailable_calls','native_compile_calls','native_execute_calls')) + ' |']
        lines += ['', '中止前的已发生请求和执行均计入旧运行；不能将未完成的原生回放计作接受。'
            '这些成本不加到本轮新调用数；汇总时每个物理运行仅计算一次。']
    return '\n'.join(lines)


def verify(run, out):
    manifest = read(out / 'manifest.json', {})
    checks = []
    for rel, expected in manifest.items():
        path = (run / rel).resolve()
        if run not in path.parents:
            raise ValueError('Unsafe manifest path')
        actual = digest(path) if path.is_file() else None
        checks.append(dict(path=rel, passed=actual == expected, expected=expected, actual=actual))
    extra = sorted(p.relative_to(run).as_posix() for p in base.artifacts(run) if p.relative_to(run).as_posix() not in manifest)
    result = read(out / 'results.json', {})
    linked = []
    for record in (source_checks(result.get('lineage', {}))
            + result.get('development_provenance', {}).get('file_checks', [])
            + result.get('inherited_feedback', {}).get('file_checks', [])
            + result.get('backend_support', {}).get('linked_log_checks', [])):
        path = portable(record['path']).resolve()
        if ROOT not in path.parents:
            raise ValueError('Unsafe source manifest path')
        actual = digest(path) if path.is_file() else None
        linked.append(dict(path=record['path'], passed=actual == record['expected']))
    for category in ('preceding_attempts','backend_probes'):
        for item in result.get('preceding_costs', {}).get(category, []):
            folder = portable(item['path']).resolve()
            if ROOT not in folder.parents:
                raise ValueError('Unsafe preceding-cost source')
            for rel, expected in item.get('record_hashes', {}).items():
                path = (folder / rel).resolve()
                if folder not in path.parents:
                    raise ValueError('Unsafe preceding-cost artifact')
                actual = digest(path) if path.is_file() else None
                linked.append(dict(path=path.relative_to(ROOT).as_posix(),passed=actual==expected))
    freezes = base.freeze_audit(run)
    snapshot = previous.source_audit(run)
    independent = previous.independent_audit(run, freezes)
    passed = bool(manifest and not extra and all(c['passed'] for c in checks + linked)
        and snapshot['passed'] and all(c['passed'] for c in freezes)
        and (independent['status'] != 'completed' or independent['all_frozen_hashes_match']))
    result = dict(passed=passed, checked=len(checks), checks=checks, source_checks=linked,
        unmanifested_files=extra, freezes=freezes, snapshot=snapshot,
        scope='Artifact and frozen identity integrity, not functional success.')
    dump(out / 'verification.json', result)
    print(json.dumps(dict(passed=passed, checked=len(checks), linked=len(linked), extra=extra)))
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    run = portable(args.run).resolve()
    if ROOT not in run.parents or not run.is_dir():
        raise ValueError('Existing workspace run required')
    outcome = terminal(run)
    out = run / 'report'; out.mkdir(exist_ok=True)
    if args.verify:
        return verify(run, out)
    files = base.artifacts(run)
    protocol = read(run / 'protocol.json', {})
    core = core_summary(run)
    trace = trace_audit(run, core, current_run=True)
    source = lineage(run)
    development_origin = development_provenance(run)
    inherited_feedback = inherited_feedback_audit(run)
    backend_support = backend_support_audit(run)
    blocked_backend = {c['path'] for c in backend_support['calls'] if c['accepted_support_permitted'] is False}
    accepted_backend_valid = not any(t['accepted'] and t['version']+'/model_call' in blocked_backend for t in trace['records'])
    freezes = base.freeze_audit(run)
    independent = previous.independent_audit(run, freezes)
    projections = {name: replay_projection(run / 'core_independent' / name, True)
        for name in independent.get('summary') or {}}
    deduplicated = {name: p['counts'] for name, p in projections.items() if p['counts'] is not None}
    chosen = run / 'core/before'
    for h in core.get('history', []):
        if h.get('decision', {}).get('accepted'):
            chosen = run / 'core' / f"v{h['iteration']}" / 'native'
    development = dict(before=replay_projection(run / 'core/before'), after=replay_projection(chosen))
    target_scope = previous.scope(independent, deduplicated, 'core', TARGETS)
    separation=independent_separation_audit(run)
    missing = previous.missing_evidence_audit(run)
    snapshot = previous.source_audit(run)
    boundary = (projections.get('core', {}).get('boundaries') or {}).get('by_boundary', {})
    release = boundary.get('stall_release', {})
    boundary_pass = bool(release.get('target_rows') and release.get('detections') and all(release.get(k) == 0 for k in ('misses', 'unknown', 'false_positives')))
    chain = bool(source['passed'] and development_origin['passed'] and inherited_feedback['passed'] and accepted_backend_valid
        and trace['accepted_integrity_passed'] and trace['accepted_new_target_edits']
        and trace['final_candidate_equals_last_accepted'] and target_scope['passed'] and boundary_pass and separation['passed']
        and missing['confirmed_missing_rows'] and missing['archived_missing_rows_match'] and snapshot['passed'])
    data = dict(status=outcome['status'], generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        outcome=outcome, protocol=protocol, execution_command=read(run / 'execution.command.json'),
        diagnosis=read(run / 'diagnosis.json'), lineage=source, trace=trace, core=core,
        initial_candidate=read(run / 'shared_initial.json'), final_candidate=read(run / 'core/frozen_candidate.json'),
        development=development, development_provenance=development_origin, missing_evidence=missing, independent=independent,
        prompt_evidence=prompt_evidence_audit(run), inherited_feedback=inherited_feedback,backend_support=backend_support,
        independent_projections=projections, independent_deduplicated=deduplicated,
        independent_separation=separation,
        target_chain=dict(passed=chain, target_obligations=list(TARGETS), scope=target_scope,
            stall_release_observed_pass=boundary_pass, new_accepted_target_edits=trace['accepted_new_target_edits'],
            limitation='Finite observed boundary protection only, not full semantic coverage.'),
        whole_parent_case=dict(passed=False, status='not_established', original_historical_fifo_bug='unknown', stat='unknown'),
        cost=previous.extended_cost_audit(run, files), context_preflight_audit=dedup_tools.context_audit(run, files),
        preceding_costs=dedup_tools.linked_cost_audit(protocol),
        accepted_obligation_mapping=base.accepted_mapping(run, 'core', core),
        freeze_checks=freezes, source_snapshot=snapshot,
        accounting='Only this run physical costs; inherited source costs remain in their own run reports.')
    dump(out / 'results.json', data)
    dump(out / 'cost/results.json', data['cost'])
    dump(out / 'freeze_checks.json', freezes)
    (out / 'REPORT.md').write_text(render(run, data), encoding='utf-8')
    shutil.copy2(__file__, out / 'report_script_snapshot.py')
    manifest = {p.relative_to(run).as_posix(): digest(p) for p in files}
    dump(out / 'manifest.json', manifest)
    dump(out / 'source_and_rtl_hashes.json', {k:v for k,v in manifest.items() if Path(k).suffix in ('.py','.v','.sv')})
    print(json.dumps(dict(status=data['status'], target_chain=chain, whole_parent_case=False,
        cost=data['cost']['total'], report=str(out / 'REPORT.md'))))


if __name__ == '__main__':
    main()
