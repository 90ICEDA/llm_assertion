"""Continue from a real accepted event plan with numeric regression feedback.

prepare never calls a model. run requires a fresh two-SVA-call authorization.
All generation is real; gates, original candidate and holdout are unchanged.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import research17_loop as loop
import research31_gate as gate
import research32_runtime as extension
from research20_remote import RemoteModel
from research32_model import assemble
from research34_campaign import snapshot, digest
from research34_applicability import native_target_gate
from research35_campaign import holdout
from research36_applicability import validate_events
from research37_local import LocalModel, feedback, assemble_replacement, PREP, OLD
from research17_report import artifacts, cost_audit

read, dump = loop.read, loop.dump


def complete_feedback(result, verdict, call):
    """Preserve actual interface/transport errors, including a complete no-SVA failure.

    Never call an interface rejection a native compilation error. Do not replace
    model expressions or supply an expression in this diagnostic.
    """
    diagnostic = feedback(result, verdict)
    diagnostic['interface_diagnostic'] = {k:copy.deepcopy(call[k]) for k in (
        'status', 'candidate_status', 'candidate_error', 'error', 'proposal_rejection',
        'done_reason', 'partial_response_characters', 'requested_obligation') if k in call}
    diagnostic['native_replay_performed'] = result is not None
    diagnostic['diagnostic_scope'] = 'Actual prior call and native result only. Interface validation is distinct from native compilation/execution. Clock and reset wrapping is supplied by the native harness; expressions may use only declared property signals.'
    return diagnostic


def payload(initial, diagnostic, plan, settings):
    # Presentation is shared with the actual local continuation; constructor is
    # deliberately not run here (no service/model loading or model request).
    presenter = object.__new__(LocalModel)
    presenter.plan = plan
    request = presenter.transform_request({}, initial, 'stall_stability', diagnostic, 'numeric_history_feedback')
    return dict(model=settings['remote_model'], messages=request['messages'], stream=True,
                stream_options={'include_usage': True}, response_format={'type':'json_object'},
                temperature=settings['options']['temperature'], seed=settings['options']['seed'], max_tokens=1024)


class Model(RemoteModel):
    def __init__(self, out, settings, plan):
        super().__init__(out, settings)
        self.assemble = assemble_replacement
        self.plan = plan

    def _payload(self, current, target, diagnostic, phase):
        return payload(current, diagnostic, self.plan, self.config)


def prepare(out):
    plan = read(OLD / 'plan/v1/model_call/applicability_plan.json')
    verdict = validate_events(plan, read(PREP / 'expected.private.json'))
    assert verdict['accepted']
    loop.prepare(out)
    snapshot(out)
    initial = read(PREP / 'shared_initial.json')
    diagnostic = complete_feedback(read(OLD / 'core/v1/target_native/result.json'), read(OLD / 'core/v1/decision.json'), read(OLD / 'core/v1/model_call/result.json'))
    # Prospectively reuse the latest actual interface failure too. Keep the
    # numeric regressions above: the interface failure has no native samples.
    prior_interface = loop.ROOT/'deliverables/research38_real_20261022_r01/core/v1/model_call/result.json'
    if prior_interface.exists():
        prior_call = read(prior_interface)
        diagnostic['latest_interface_failure'] = {k:copy.deepcopy(prior_call[k]) for k in (
            'status','candidate_status','candidate_error','requested_obligation') if k in prior_call}
        diagnostic['latest_interface_failure_source'] = dict(path=str(prior_interface),sha256=digest(prior_interface))
    settings = read(PREP / 'model_config.json')
    settings['max_model_calls'] = 2
    dump(out / 'model_config.json', settings)
    dump(out / 'verified_plan.json', plan)
    dump(out / 'verified_plan_gate.json', verdict)
    dump(out / 'development_diagnostics.json', diagnostic)
    dump(out / 'request.preview.json', payload(initial, diagnostic, plan, settings))
    for name in ('shared_initial','target_cases','target_baseline','full_cases','full_baseline','expected.private'):
        shutil.copy2(PREP / (name+'.json'), out / (name+'.json'))
    dump(out / 'provenance.json', dict(plan_source=str(OLD / 'plan/v1/model_call'),
         native_feedback_source=str(OLD / 'core/v1'), original_prepared=str(PREP),
         feedback_result_sha256=digest(OLD / 'core/v1/target_native/result.json'),
         feedback_decision_sha256=digest(OLD / 'core/v1/decision.json'), native_reexecutions=0, model_calls=0))
    dump(out / 'protocol.json', dict(maximum_calls=2, plan_calls=0, sva_calls=2, retries=0, feedback_version=2,
         endpoint=settings['remote_url'], model=settings['remote_model'],
         prior_plan='Reused actual accepted research36 model event plan. No new plan or initial-SVA generation claim.',
         feedback='Actual sampled histories for false alarms and unknowns, besides paired missing evidence. Not merely rejection IDs. Full expected table and independent tests excluded.',
         gates='Exact native edited-property target gate, complete113-scenario history, freeze accepted version, then56-scenario fresh holdout.',
         budget='Research36 four-call budget exhausted. New explicit authorization required before run.'))
    dump(out / 'prepared_hashes.json', {p.relative_to(out).as_posix():digest(p) for p in out.glob('*.json')})
    print('PREPARED_NUMERIC_HISTORY_FEEDBACK', dict(model_calls=0, event_plan_passed=True), flush=True)


def run(prep, out, auth_path, model_type=Model, feedback_fn=None,
        holdout_fn=holdout, history_feedback=False):
    auth = read(auth_path)
    settings = read(prep / 'model_config.json')
    assert auth['authorized_calls'] == 2 and auth['run_output'] == out.relative_to(loop.ROOT).as_posix()
    assert auth['endpoint'] == settings['remote_url'] and auth['model'] == settings['remote_model']
    for n,h in read(prep / 'prepared_hashes.json').items(): assert digest(prep/n) == h,n
    for n,h in read(prep / 'source_snapshot/hashes.json').items(): assert digest(loop.ROOT/'scripts'/n) == h,n
    plan = read(prep / 'verified_plan.json')
    assert validate_events(plan, read(prep / 'expected.private.json'))['accepted']
    loop.prepare(out)
    snapshot(out)
    shutil.copy2(auth_path,out/'authorization.json')
    shutil.copy2(prep/'protocol.json',out/'protocol.json')
    dump(out/'prepared_source.json',dict(path=str(prep)))
    dump(out/'verified_plan.json',plan)
    model = None
    current = initial = read(prep/'shared_initial.json')
    status = 'not_started'
    try:
        model = model_type(out/'model', settings, plan)
        diagnostic = read(prep/'development_diagnostics.json')
        assert model._payload(current,None,diagnostic,None) == read(prep/'request.preview.json')
        before = read(prep/'full_baseline.json')
        with extension.installed():
            for i in range(2):
                version = out/'core'/f'v{i}'
                call,candidate = model.call(version/'model_call',current,'stall_stability',diagnostic,'numeric_history_feedback')
                verdict = dict(accepted=False,reasons=[dict(kind='model_output_unusable',status=call['status'])])
                small = None
                full = None
                if candidate:
                    edit = read(version/'model_call/model_edit.json')
                    small = loop.replay(candidate,version/'target_native',read(prep/'target_cases.json'))
                    verdict = native_target_gate(read(prep/'target_baseline.json'),small,edit['assertion_id'])
                    dump(version/'target_gate.json',verdict)
                    if verdict['accepted']:
                        full = loop.replay(candidate,version/'history_native',read(prep/'full_cases.json'))
                        verdict = gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
                        verdict['accepted'] = bool(verdict['accepted'] and full['healthy'])
                        dump(version/'historical_gate.json',verdict)
                dump(version/'decision.json',verdict)
                print('SVA',i,'accepted',verdict['accepted'],'reasons',len(verdict['reasons']),flush=True)
                if verdict['accepted']:
                    current=candidate
                    break
                feedback_result=full if history_feedback and full is not None else small
                diagnostic=(feedback_fn(feedback_result,verdict,call,diagnostic) if feedback_fn
                            else complete_feedback(feedback_result,verdict,call))
            loop.freeze(out/'core',current,'terminal_before_fresh_inputs')
            if current == initial:
                status='sva_refinement_unresolved'
                return
            completed=holdout_fn(out,current,read(prep/'full_cases.json'))
            status=('accepted_frozen_independent_deferred' if completed is False
                    else 'accepted_and_independent_completed')
    except BaseException:
        status='execution_exception'
        raise
    finally:
        if not (out/'core/freeze.json').exists(): loop.freeze(out/'core',current,'retained_after_trial')
        calls=model.calls if model else []
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls)))
        dump(out/'outcome.json',dict(status=status,calls=len(calls),accepted=current!=initial,frozen_hash=loop.sha(current)))
        dump(out/'cost.json',cost_audit(out,artifacts(out)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--prepared',type=Path)
    p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    assert loop.ROOT in a.out.resolve().parents
    if a.action=='prepare': prepare(a.out.resolve())
    else: run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
