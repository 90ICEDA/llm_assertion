"""Qualify real initial-rejection feedback; no service or model calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

from research17_model import ROOT, dump, read
from research20_model import project_feedback, assemble
from research20_remote import RemoteModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    assert ROOT in source.parents and ROOT in out.parents
    out.mkdir(parents=True, exist_ok=False)
    config = dict(direct_property=True,
        options=dict(seed=20261018, temperature=0, num_predict=1024, num_ctx=16384),
        max_model_calls=2, max_tokens=240000, max_wall_seconds=900, call_timeout=180)
    model = RemoteModel(out, config)  # Constructor does not read keys or connect.
    checks, sources = [], []

    def check(name, passed, detail=None):
        checks.append(dict(name=name, passed=bool(passed), detail=detail))

    for name in ('v0', 'v1'):
        folder = source / 'initial' / name / 'model_call'
        result_path, edit_path = folder / 'result.json', folder / 'model_edit.json'
        result, edit = read(result_path), read(edit_path)
        sources.extend([result_path, edit_path])
        untouched = copy.deepcopy(edit)
        # This is the actual envelope produced by loop.initial after an
        # interface rejection, not the differently named refinement envelope.
        feedback = dict(call=result, native=None)
        projected = project_feedback(feedback, 'order_payload')
        check(name + ':original_rejection_confirmed', result['candidate_status'] == 'interface_rejected' and result['candidate_error']['detail'] == 'non_property_input')
        check(name + ':original_model_response_arrived', result['status'] == 'response_received' and result['model_calls'] == 1)
        check(name + ':diagnostic_exact', projected['interface_diagnostic'] == {k:result[k] for k in ('status','candidate_status','candidate_error')})
        check(name + ':no_native_evidence_invented', projected['paired_target_samples'] == [] and projected['legal_control_failure_samples'] == [])
        payload = model._payload(None, 'order_payload', feedback, 'initial_generation')
        body = json.loads(payload['messages'][1]['content'])
        check(name + ':diagnostic_survives_final_request', body['requested_work']['actual_feedback']['interface_diagnostic'] == projected['interface_diagnostic'])
        check(name + ':direct_schema_enabled', set(body['rtl_and_common_contract']['response_schema']['assertions'][0]) == {'property','obligation'})
        check(name + ':format_instruction_has_no_example_predicate', 'No example assertion is supplied.' in body['requested_work']['task'] and 'mvalid && mready' not in body['requested_work']['task'])
        try:
            assemble(edit, None)
        except AssertionError as exc:
            check(name + ':wrapped_proposal_remains_rejected', str(exc) == 'non_property_input', str(exc))
        else:
            check(name + ':wrapped_proposal_remains_rejected', False)
        check(name + ':rejected_expression_not_repaired_or_changed', edit == untouched)
        dump(out / (name + '_projected_feedback.json'), projected)
        dump(out / (name + '_request_qualification.json'), payload)

    # A previously generated REAL valid expression is supplied through the new
    # direct-property field only to test preservation. It is not a newly issued
    # model proposal, and the malformed r04 response is never stripped/fixed.
    valid_source = ROOT / 'deliverables/research19_closed_loop_20261016_r03/shared_initial.json'
    valid = read(valid_source)['assertions'][0]
    sources.append(valid_source)
    direct_edit = dict(operation='replace', assertions=[dict(property=valid['property'], obligation=valid['obligations'])],
                       reason='Qualification fixture using an unmodified archived real-model expression; not new generation.')
    unchanged = copy.deepcopy(direct_edit)
    candidate = assemble(direct_edit, None)
    check('direct_property_exact_text_preserved', candidate['assertions'][0]['property'] == valid['property'])
    check('direct_property_labels_preserved', candidate['assertions'][0]['obligations'] == valid['obligations'])
    check('direct_input_unmodified', direct_edit == unchanged)
    check('no_model_requests', model.calls == [])
    dump(out / 'direct_property_qualification.json', dict(source=str(valid_source), fixture=direct_edit, assembled=candidate))
    prior_request = source / 'initial/v1/model_call/request.json'
    prior_body = json.loads(read(prior_request)['messages'][1]['content'])
    sources.append(prior_request)
    old_diagnostic = prior_body['requested_work']['actual_feedback']['interface_diagnostic']
    check('archived_initial_retry_demonstrates_prior_loss', old_diagnostic == {}, old_diagnostic)
    report = dict(passed=all(c['passed'] for c in checks), checks=checks,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        implementation_sha256=hashlib.sha256((ROOT/'scripts/research20_model.py').read_bytes()).hexdigest(),
        model_calls=0, network_calls=0, credential_content_reads=0, native_executions=0,
        scope='Initial rejection-envelope regression and direct-expression fidelity only. Archived real proposals are qualification inputs, not new model success. No malformed expression was corrected. No independent-test files were read.')
    dump(out / 'qualification.json', report)
    print(json.dumps(dict(passed=report['passed'], checks=len(checks)), indent=2))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
