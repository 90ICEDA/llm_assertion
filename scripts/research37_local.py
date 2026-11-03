"""Bounded LOCAL continuation after research36 remote budget, no remote calls.

Reuse the accepted real event plan, exact native gates and post-freeze holdout.
Model switch is an exploratory continuation, not a controlled comparison.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import research17_loop as loop
import research17_model as base
import research31_gate as gate
import research32_runtime as extension
from research32_model import assemble
from research34_campaign import snapshot
from research34_applicability import native_target_gate, portable
from research35_campaign import holdout
from research36_applicability import validate_events
from research17_report import artifacts, cost_audit

read, dump = loop.read, loop.dump
PREP = loop.ROOT / 'deliverables/research36_prepare_20261022_r01'
OLD = loop.ROOT / 'deliverables/research36_real_20261022_r01'


def assemble_replacement(value, current):
    # This continuation requests a replacement in an existing target slot.
    # A keep/add response must not reach native_target_gate with an empty ID.
    assert isinstance(value,dict) and value.get('operation') == 'replace_one', 'replacement_required_for_target_gate'
    assert value.get('assertion_id') in [a['id'] for a in current['assertions'] if 'stall_stability' in a['obligations']], 'replacement_requires_stall_slot'
    return assemble(value,current)


def observed_cards(result, keys, limit=4):
    info = loop.inspect(result['group']['ledger'])
    cards = []
    for key in sorted(keys)[:limit]:
        row = info['rows'][key]
        record = read(portable(row['source_directory']) / 'replay.json')
        cycle = row['cycle']
        cards.append(dict(evidence_id=key, scenario=row['scenario_id'], obligation=row['obligation'],
            oracle=row['oracle'], native=row['native'],
            samples=[r for r in record['reference_trace'] if r['cycle'] in (cycle-1,cycle)],
            provenance=row['source_directory']))
    return cards


class LocalModel(base.Model):
    def __init__(self, out, settings, plan):
        super().__init__(out, settings)
        self.assemble = assemble_replacement
        self.plan = plan

    def transform_request(self, request, current, target, feedback, phase):
        template = read(OLD / 'core/v0/model_call/request.json')
        body = json.loads(template['messages'][1]['content'])
        schema = body['output_schema']
        schema['properties']['assertions']['minItems'] = 1
        # Lossless projection of the observed paired samples; remove duplicate
        # equal/different maps, paths and narrative copies, not signal values.
        cards = []
        for card in body['counterexample_first']['contrasts']:
            event = card['target_evidence']
            cards.append(dict(evidence_id=card['evidence_id'], scenario=card['scenario'], cycle=card['cycle'],
                independent_oracle=event['oracle'], assertion_observation=event['gap_observation'],
                faulty=card['buggy_adjacent_samples'], correct=card['fixed_adjacent_samples']))
        brief = dict(specification=body['counterexample_first']['specification'],
                     clock_reset=body['counterexample_first']['clock_and_reset'], contrasts=cards)
        content = dict(rtl_and_common_contract=body['rtl_and_common_contract'],
            task='Generate one replacement native property for stall_stability. Determine both Boolean operands and temporal timing from the obligation and actual evidence.',
            obligation=brief, actual_verified_plan=self.plan,
            eligible_slots=body['retained_set']['eligible_slots'], retained_hash=loop.sha(current),
            previous_native_diagnostics=feedback,
            reference_semantics='ref_expected is the oldest outstanding accepted input payload, meaningful only for nonempty reference queue. It is NOT the previous output payload. Output hold is an obligation of a pending output; an input request or input-side handshake is not a prerequisite. Different obligations remain covered by the other unchanged assertions.',
            validation='Edited assertion must trigger and detect all eight new targets in paired native RTL; legal history, old fault detection and applicable triggers must be preserved; unknown rejects. Correct Boolean expressions and timing yourself. No text will be repaired by the harness.',
            output_schema=schema)
        request['format'] = schema
        request['messages'] = [dict(role='system', content='Derive an SVA edit from hardware semantics and numeric evidence. Return only the exact JSON schema. Every Boolean operand and timing is yours; no successful property is provided. Clock/reset wrappers are supplied.'),
                               dict(role='user', content=json.dumps(content))]
        return request


def feedback(result, verdict):
    info = loop.inspect(result['group']['ledger']) if result and result.get('group') else None
    kinds = [dict(kind=r['kind'], count=len(r.get('evidence_keys', []))) for r in verdict['reasons']]
    return dict(actual_rejection=kinds,
        legal_false_alarms=observed_cards(result, info['false_positives']) if info else [],
        missed_obligations=observed_cards(result, info['misses']) if info else [],
        unknown=observed_cards(result, info['unknown'], 2) if info else [],
        scope='Observed development evidence only; no independent inputs and no property answer.')


def run(out, iterations=2, timeout=900):
    assert 1 <= iterations <= 2 and 900 <= timeout <= 1800
    plan = read(OLD / 'plan/v1/model_call/applicability_plan.json')
    assert validate_events(plan, read(PREP / 'expected.private.json'))['accepted']
    loop.prepare(out)
    snapshot(out)
    dump(out / 'verified_plan.json', plan)
    settings = dict(model='qwen2.5-coder:7b-instruct', options=dict(seed=3603,temperature=0,num_predict=512,num_ctx=24576,num_gpu=0,num_thread=8),
                    max_model_calls=iterations,max_tokens=60000,max_wall_seconds=timeout*iterations+600,call_timeout=timeout,preflight_tokens=True)
    dump(out / 'model_config.json', settings)
    dump(out / 'protocol.json', dict(backend='local_ollama', maximum_calls=iterations, remote_calls=0, timeout_seconds=timeout,
         plan_source=str(OLD / 'plan/v1/model_call'), prepared=str(PREP),
         scope='Model changed to locally cached Qwen 7B. Exploratory continuation, not controlled 72B comparison. Same independent/native/history acceptance.',
         freeze='Fresh holdout only after accepted candidate; no selection or modification from holdout.'))
    current = initial = read(PREP / 'shared_initial.json')
    model = None
    process = None
    status = 'not_started'
    try:
        try:
            urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=3).close()
        except Exception:
            env = os.environ.copy()
            env.update(OLLAMA_HOST='127.0.0.1:11434', OLLAMA_FLASH_ATTENTION='true', OLLAMA_KV_CACHE_TYPE='q8_0', OLLAMA_NUM_PARALLEL='1')
            (out / 'service').mkdir()
            with (out / 'service/server.log').open('w') as log:
                process = subprocess.Popen(['ollama','serve'], stdout=log, stderr=log, start_new_session=True, env=env)
            dump(out / 'service/process.json', dict(pid=process.pid))
            for _ in range(30):
                try:
                    urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2).close()
                    break
                except Exception: time.sleep(.5)
            else: raise RuntimeError('local_service_unavailable')
        model = LocalModel(out / 'model', settings, plan)
        before = read(PREP / 'full_baseline.json')
        diagnostic = feedback(read(OLD / 'core/v1/target_native/result.json'), read(OLD / 'core/v1/decision.json'))
        interface_failure = loop.ROOT/'deliverables/research38_real_20261022_r01/core/v1/model_call/result.json'
        if interface_failure.exists():
            previous = read(interface_failure)
            diagnostic['actual_prior_interface_failure'] = {k:copy.deepcopy(previous[k]) for k in (
                'candidate_status','candidate_error','requested_obligation') if k in previous}
            diagnostic['interface_source'] = str(interface_failure)
        with extension.installed():
            for i in range(iterations):
                version = out / 'core' / f'v{i}'
                call, candidate = model.call(version / 'model_call', current, 'stall_stability', diagnostic, 'local_event_verified_refinement')
                verdict = dict(accepted=False, reasons=[dict(kind='local_model_output_unusable', status=call['status'])])
                small = None
                if candidate:
                    edit = read(version / 'model_call/model_edit.json')
                    small = loop.replay(candidate, version / 'target_native', read(PREP / 'target_cases.json'))
                    verdict = native_target_gate(read(PREP / 'target_baseline.json'), small, edit['assertion_id'])
                    dump(version / 'target_gate.json', verdict)
                    if verdict['accepted']:
                        full = loop.replay(candidate, version / 'history_native', read(PREP / 'full_cases.json'))
                        verdict = gate.decide(before['group']['ledger'], full['group']['ledger'], sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False, reasons=[dict(kind='native_unavailable')])
                        verdict['accepted'] = bool(verdict['accepted'] and full['healthy'])
                        dump(version / 'historical_gate.json', verdict)
                dump(version / 'decision.json', verdict)
                print('LOCAL_SVA', i, 'accepted', verdict['accepted'], 'reasons', len(verdict['reasons']), flush=True)
                if verdict['accepted']:
                    current = candidate
                    break
                diagnostic = feedback(small, verdict)
                # Preserve interface errors as well as numeric native evidence;
                # a response can arrive successfully yet fail SVA assembly.
                diagnostic['interface_diagnostic'] = {k:copy.deepcopy(call[k]) for k in (
                    'status','candidate_status','candidate_error','error','proposal_rejection',
                    'done_reason','partial_response_characters','requested_obligation') if k in call}
                diagnostic['native_replay_performed'] = small is not None
                if call['status'] != 'response_received':
                    status = 'local_transport_or_context_blocked'
                    break
            loop.freeze(out / 'core', current, 'terminal_before_fresh_inputs')
            if loop.sha(current) == loop.sha(initial):
                if status == 'not_started': status = 'local_refinement_unresolved'
                return
            holdout(out, current, read(PREP / 'full_cases.json'))
            status = 'accepted_and_independent_completed'
    except Exception as exc:
        status = 'execution_exception'
        dump(out / 'exception.json', dict(type=type(exc).__name__, detail=str(exc)))
        raise
    finally:
        if process is not None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: pass
            dump(out / 'service_shutdown.json', dict(pid=process.pid, owned=True, returncode=process.poll()))
        if not (out / 'core/freeze.json').exists(): loop.freeze(out / 'core', current, 'retained_after_local_trial')
        calls = model.calls if model else []
        dump(out / 'model_cost.json', dict(calls=len(calls), prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
             completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
             usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls)))
        dump(out / 'outcome.json', dict(status=status,calls=len(calls),remote_calls=0,accepted=loop.sha(current)!=loop.sha(initial),frozen_hash=loop.sha(current)))
        dump(out / 'cost.json', cost_audit(out, artifacts(out)))
        print('TERMINAL', status, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--iterations',type=int,choices=(1,2),default=2)
    p.add_argument('--timeout',type=int,choices=(900,1800),default=900)
    a = p.parse_args()
    assert loop.ROOT in a.out.resolve().parents
    run(a.out.resolve(),a.iterations,a.timeout)
