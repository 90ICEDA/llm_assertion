"""Offline audit and actionable diagnostics for the failed research54 run.

No model calls, property rewriting, native executions, or acceptance changes.
This audit intentionally requires frontend rejection; native candidates need a
native-evidence audit instead of being silently accepted by this audit.
"""
import argparse
import ast
import json
import re
from pathlib import Path
import research54_complementary_sva as g


def diagnose(value, current):
    """Explain interface errors without unwrapping or correcting a proposal."""
    errors = []
    expected = {'operation', 'reason', 'assertions'}
    if not isinstance(value, dict) or set(value) != expected:
        errors.append(dict(kind='top_level_schema', expected_keys=sorted(expected),
                           actual_keys=sorted(value) if isinstance(value, dict) else None))
    # A wrapped payload is inspected for diagnostics only, never accepted.
    obj = value.get('output', value) if isinstance(value, dict) else {}
    warnings = []
    if isinstance(obj, dict):
        for i, item in enumerate(obj.get('assertions', [])):
            if not isinstance(item, dict):
                continue
            for field in ('antecedent', 'consequent'):
                expr = item.get(field)
                if not isinstance(expr, str):
                    continue
                stripped = re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+", '0', expr)
                names = set(re.findall(r'\$?[A-Za-z_][A-Za-z_0-9]*', stripped))
                unknown = names - {'instr', 'instr_new', 'illegal_insn', 'rv32m', 'rv32e',
                                   '$past', '$stable', '$rose', '$fell'}
                if unknown:
                    errors.append(dict(kind='undeclared_identifier', assertion=i,
                                       field=field, identifiers=sorted(unknown)))
            antecedent = item.get('antecedent', '')
            if isinstance(antecedent, str) and re.search(r'instr\s*\[\s*31\s*\]', antecedent):
                warnings.append(dict(kind='bit31_reference', assertion=i,
                    scope='Text observation only; not a native semantic judgment or general equivalence check.'))
    try:
        candidate = g.assemble(value, current)
    except (AssertionError, KeyError, TypeError, ValueError) as exc:
        accepted = False
        errors.append(dict(kind='sealed_assembler_rejection', exception=type(exc).__name__, detail=str(exc)))
    else:
        duplicate = g.common.duplicates(candidate, current, 'replace')
        accepted = duplicate['accepted']
        if not accepted:
            errors.append(dict(kind='duplicate_proposal', details=duplicate))
    return dict(interface_accepted=accepted, errors=errors, observations=warnings,
                native_status='not_run', semantic_status='not_determined_by_this_diagnostic',
                model_output_modified=False)


def run(prep, root, out):
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
        assert ok, name
    for name, sha in g.read(prep/'sealed.json').items():
        check('sealed/'+name, g.old.digest(prep/name) == sha)
    for name, sha in g.read(prep/'source_hashes.json').items():
        check('run_source/'+name, g.old.digest(root/'source_snapshot'/name) == sha)
        check('current_source/'+name, g.old.digest(g.ROOT/'scripts'/name) == sha)
    certificate = g.components(prep)
    check('component_certificate', certificate == g.read(prep/'component_certificate.json'))
    check('whole_old_plan_remains_rejected', not certificate['original_plan_verdict']['accepted'])
    auth = g.read(root/'authorization.json')
    protocol = g.read(prep/'protocol.json')
    check('authorization_scope', auth['scope'] == protocol['scope'])
    check('authorization_payload', auth['request_sha256'] == g.old.digest(prep/'request.preview.json'))
    check('authorization_endpoint', auth['endpoint'] == protocol['endpoint'])
    check('authorization_budget', auth['authorized_calls'] == 2 and auth['new_calls'] == 0)
    check('authorization_output', auth['run_output'] == root.relative_to(g.ROOT).as_posix())
    current = g.read(prep/'shared_initial.json')
    feedback = g.read(prep/'initial_feedback.json')
    versions = []
    calls = []
    decisions = []
    folders = sorted(root.glob('v[0-9]*'))
    check('two_versions', len(folders) == 2)
    for folder in folders:
        base = folder/'model_call'
        prefix = folder.name+'/'
        call = g.read(base/'result.json')
        calls.append(call)
        check(prefix+'exact_request', g.read(base/'request.json') == g.payload(prep, current, feedback))
        events = [json.loads(line) for line in (base/'response.events.jsonl').read_text().splitlines()]
        raw_events = []
        terminal = False
        for line in (base/'response.stream.raw').read_text().splitlines():
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]':
                terminal = True
            elif data:
                raw_events.append(json.loads(data))
        check(prefix+'events_from_raw_stream', raw_events == events and terminal)
        content = ''.join(c.get('delta', {}).get('content') or '' for e in events
                          for c in e.get('choices', []) if c.get('index', 0) == 0)
        check(prefix+'assembled_from_raw_stream', content == g.read(base/'response.assembled.json')['message']['content'])
        value = json.loads(content)
        check(prefix+'model_edit_exact', value == g.read(base/'model_edit.json'))
        check(prefix+'provider_usage', any(e.get('usage', {}).get('prompt_tokens') == call['prompt_tokens']
              and e.get('usage', {}).get('completion_tokens') == call['completion_tokens'] for e in events if e.get('usage')))
        check(prefix+'transport_no_retry', call['retries'] == 0 and call['stream_terminal_received'])
        check(prefix+'actual_model', call['actual_server_model'] == protocol['model'])
        diagnosis = diagnose(value, current)
        check(prefix+'sealed_frontend_rejects', not diagnosis['interface_accepted'])
        check(prefix+'reported_interface_rejection', call['candidate_status'] == 'interface_rejected')
        check(prefix+'no_executable_substitution', not (base/'candidate.json').exists())
        check(prefix+'no_native_execution', not (folder/'history').exists() and not (folder/'search').exists())
        decision = dict(accepted=False, reasons=[dict(kind='unusable_or_duplicate_proposal')])
        check(prefix+'decision', decision == g.read(folder/'decision.json'))
        original_error = next(e for e in diagnosis['errors'] if e['kind'] == 'sealed_assembler_rejection')
        saved_error = call['candidate_error']
        saved_detail, replay_detail = saved_error['detail'], original_error['detail']
        # Old assembler formats a Python set; element order varies by process.
        # Compare set contents, retaining the original text in the raw record.
        if saved_detail.startswith('{') and replay_detail.startswith('{'):
            saved_detail, replay_detail = ast.literal_eval(saved_detail), ast.literal_eval(replay_detail)
        check(prefix+'same_exception_and_identifiers', saved_error['type'] == original_error['exception'] and saved_detail == replay_detail)
        versions.append(dict(version=folder.name, accepted=False, model_edit=value, diagnosis=diagnosis,
                             native_replay='not_run', historical_protection='not_remeasured'))
        decisions.append(dict(version=int(folder.name[1:]), accepted=False))
        feedback = dict(previous_native_feedback=feedback, call=call, decision=decision)
    outcome = g.read(root/'outcome.json')
    check('final_status', outcome['status'] == 'no_accepted_sva' and outcome['decisions'] == decisions)
    check('calls', outcome['calls'] == len(calls) == auth['authorized_calls'])
    check('no_accepted_candidate', outcome['accepted_candidate_sha256'] is None and not (root/'accepted_candidate.json').exists())
    check('no_independent_test', outcome['independent_test'] == 'not_run' and not (root/'independent').exists())
    costs = g.old.cost_audit(root, [p for p in root.rglob('*') if p.is_file()])
    check('cost_recomputed', costs == g.read(root/'cost.json'))
    check('no_native_or_formal', all(costs['total'][k] == 0 for k in ('native_compile_calls', 'native_execute_calls', 'formal_calls')))
    # These are local interface controls, not real model or native evidence.
    valid = dict(operation='replace_op', reason='local interface control', assertions=[dict(
        antecedent='instr_new', consequent='illegal_insn', timing='same_sample', obligations=['op_bit28_illegal'])])
    check('local_valid_schema_accepted_not_semantically_validated', diagnose(valid, current)['interface_accepted'])
    check('local_wrapper_rejected_not_unwrapped', not diagnose({'output': valid}, current)['interface_accepted'])
    check('local_missing_field_rejected', not diagnose({'operation': 'replace_op'}, current)['interface_accepted'])
    check('local_wrong_type_rejected', not diagnose([], current)['interface_accepted'])
    bad = json.loads(json.dumps(valid)); bad['assertions'][0]['antecedent'] = 'instr_new_i'
    check('local_unknown_name_identified', any(e['kind'] == 'undeclared_identifier' for e in diagnose(bad, current)['errors']))
    g.dump(out/'audit.json', dict(passed=True, checks=checks, new_model_calls=0, new_native_calls=0))
    g.dump(out/'versions.json', versions)
    g.dump(out/'component_certificate.json', certificate)
    g.dump(out/'cost_roles.json', dict(model_calls=len(calls), prompt_tokens=sum(c['prompt_tokens'] for c in calls),
        completion_tokens=sum(c['completion_tokens'] for c in calls), model_wall_seconds=sum(c['wall_seconds'] for c in calls),
        native_compile_calls=0, native_full_execute_calls=0, formal_calls=0, remaining_calls=0, monetary_cost=None,
        baseline_evidence='Reused by hash; not rerun or charged as new native execution.'))
    g.dump(out/'status.json', dict(parent_bug='Ibex #166 / #163', status='no_accepted_sva',
        newly_validated_obligations=0, declared_obligations=2, independent_test='not_run',
        historical_baseline_only=dict(branch_detected=270, op_missed=420),
        scope='Original decoder module, finite development evidence, not full core or formal proof.'))
    print('RESULT_AUDIT', len(checks), outcome['status'], flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    run(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
