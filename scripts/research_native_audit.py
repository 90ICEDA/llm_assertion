"""Readjudicate legal-prefix false positives without altering any candidate.

Raw execution decisions remain immutable. Independent results never select or
modify the candidate. This reporting audit separates post-violation alarms from
false positives on an independently legal prefix.
"""
import copy
import json
import re
from pathlib import Path
import research_native_runner as native
from research_acceptance_gate import decide


def readjudicate(folder):
    raw=json.loads((folder/'evaluation.json').read_text())
    result=copy.deepcopy(raw)
    result['false_positives']=[]
    legal_cycles={}
    for mode,oracle in raw['oracles'].items():
        trace=json.loads((folder/mode/'trace.json').read_text())
        violation_cycles={v['cycle'] for v in oracle['violations']}
        legality_error_cycles={v['cycle'] for v in oracle['legality_errors']}
        clean=True;legal_cycles[mode]=set()
        for sample in trace:
            cycle=sample['cycle']
            if sample['rst']:
                clean=True
                continue
            if cycle in violation_cycles or cycle in legality_error_cycles:clean=False
            if clean and not oracle['unknown']:legal_cycles[mode].add(cycle)
    for key in raw['false_positives']:
        mode=key.split('/')[1]
        cycle=int(re.search(r'/cycle(\d+)/',key)[1])
        oracle=raw['oracles'][mode]
        if cycle in legal_cycles[mode]:
            result['false_positives'].append(key)
        else:
            result['attribution_unknown'].append(dict(key=key,
                reason='unmatched native alarm at/after independent first violation within reset epoch; prefix not independently legal, cannot call false positive'))
    result['legal_prefix_samples_by_mode']={k:len(v) for k,v in legal_cycles.items()}
    result['false_positives_by_mode']={k:sum(f'/{k}/' in v for v in result['false_positives']) for k in legal_cycles}
    result['adjudication_notes']=[
        'Only independently legal reset-epoch prefixes contribute false positives; reset restarts prefix qualification. After-violation unmatched alarms are attribution_unknown.',
        'Raw model feedback and actual gate decision are unchanged. This is a reporting audit, not post-test model selection.',
        'Diagnostic triggers remain non-native coverage metadata. Initial unconditional property has a mismatched reported trigger.',
        'Counts are replay observation keys; independent gaps require fault-family/obligation deduplication, not one gap per cycle.']
    native.dump(folder/'readjudication.json',result)
    return result


def compact(result):
    return dict(status=result['status'],**{k:len(result[k]) for k in ('false_positives','detections','misses','attribution_unknown')},
        effective_triggers=None,diagnostic_trigger_keys=len(result['effective_triggers']),trigger_semantics='mismatch; actual native effective trigger coverage unavailable',
        legal_prefix_samples_by_mode=result['legal_prefix_samples_by_mode'],false_positives_by_mode=result['false_positives_by_mode'],
        legal_prefix_samples=sum(result['legal_prefix_samples_by_mode'].values()),
        missed_fault_obligation_classes=sorted({'/'.join((k.split('/')[1],k.split('/')[-1])) for k in result['misses']}),
        causal_detection_classes=sorted({'/'.join((k.split('/')[1],k.split('/')[-1])) for k in result['detections']}))


def main():
    out=native.OUT;original=out/'closed_loop';cont=out/'compact_continuation'
    a=readjudicate(original/'v0_development')
    raw_summary=json.loads((cont/'summary.json').read_text())
    if not (cont/'development/evaluation.json').exists():
        native.dump(out/'summary.json',dict(status='native_initial_executed_extra_revision_failed',initial=compact(a),compact_summary=str(cont/'summary.json'),details=raw_summary));return
    b=readjudicate(cont/'development');h=readjudicate(cont/'independent_test')
    target=sorted(a['false_positives'],key=lambda k:int(re.search(r'/cycle(\d+)/',k)[1]))[:1]
    corrected_decision=decide(a,b,target)
    corrected_decision['accepted']=False
    corrected_decision['reasons'].append(dict(kind='trigger_semantics_mismatch',detail='Diagnostic antecedent does not match unconditional actual property.'))
    corrected_decision.update(audit_only=True,actual_decision_unchanged=True,no_candidate_reselection=True)
    native.dump(cont/'corrected_acceptance_audit.json',corrected_decision)
    budget=json.loads((cont/'budget_accounting.json').read_text())
    service=native.ROOT/'deliverables/research_gate_20261014_r01/service/server.log'
    if service.exists():
        excerpt='\n'.join(line for line in service.read_text(errors='replace').splitlines()
            if 'truncating input prompt' in line and '20:00:05' in line or 'task 129' in line or 'id_task = 129' in line or '20:04:19' in line)
        (out/'context_overflow_service_excerpt.log').write_text(excerpt+'\n')
    known=[budget['parent_initial'],budget['extra_continuation']]
    old_runs=[json.loads(p.read_text()) for p in (original/'v0_development').glob('*/result.json')]
    new_cost=raw_summary['native_cost']
    proposal=json.loads((cont/'frozen_proposal.json').read_text())
    signatures=[json.dumps({k:a[k] for k in ('property','trigger','obligations')},sort_keys=True) for a in proposal['assertions']]
    native_cost={
        'compile_calls':new_cost['compile_calls']+sum('compile' in r for r in old_runs),
        'simulation_calls':new_cost['simulation_calls']+sum(r.get('native_simulation_calls',0) for r in old_runs),
        'compile_wall_seconds':new_cost['compile_wall_seconds']+sum(r.get('compile',{}).get('wall_seconds',0) for r in old_runs),
        'simulation_wall_seconds':new_cost['simulation_wall_seconds']+sum(r.get('execute',{}).get('wall_seconds',0) for r in old_runs)}
    qa_runs=[]
    for name in ('probes','probes_r02','engineering_qa'):
        for path in (out/name).rglob('result.json'):
            record=json.loads(path.read_text())
            if record.get('engine')=='Verilator native SVA simulation':qa_runs.append(record)
    qualification_cost=dict(compile_calls=sum('compile' in r for r in qa_runs),
        simulation_calls=sum(r.get('native_simulation_calls',0) for r in qa_runs),
        compile_wall_seconds=sum(r.get('compile',{}).get('wall_seconds',0) for r in qa_runs),
        simulation_wall_seconds=sum(r.get('execute',{}).get('wall_seconds',0) for r in qa_runs))
    summary=dict(status='native_revision_executed_rejected_proposal_diagnostic_holdout',
        original_two_call_budget_succeeded=False,formal_proof=False,
        initial=compact(a),final_development=compact(b),independent_test=compact(h),
        tested_version='frozen rejected proposal, not accepted final set',accepted_version=None,
        proposal_assertion_count=len(signatures),unique_proposal_assertions=len(set(signatures)),
        duplicate_properties=len(signatures)-len(set(signatures)),complementary_coverage_added=False,
        corrected_acceptance_audit=str(cont/'corrected_acceptance_audit.json'),
        frozen_sva_sha256=raw_summary['frozen_sva_sha256'],
        history=[dict(version='initial',accepted=False,reason='confirmed legal false positives and trigger metadata mismatch'),
                 dict(version='original_revision',accepted=False,reason='context overflow cancelled'),
                 dict(version='compact_revision',**raw_summary['decision'])],
        model_cost=dict(actual_attempts=3,completed_calls=2,cancelled_calls=1,retries=0,
            known_prompt_tokens=sum(r.get('prompt_tokens') or 0 for r in known),
            known_completion_tokens=sum(r.get('completion_tokens') or 0 for r in known),
            prompt_tokens=None,completion_tokens=None,unknown_usage_attempts=1,
            completed_wall_seconds=sum(r['wall_seconds'] for r in known),
            cancelled_wall_seconds_upper_bound=budget['parent_aborted']['wall_seconds'],
            cancelled_service_duration_display='4m18s',cancelled_service_seconds_approx=258,
            monetary_cost='unavailable_local_inference'),native_cost=native_cost,
        native_cost_scope='actual model trajectory only; qualification costs listed separately',qualification_cost=qualification_cost,
        formal_cost=dict(calls=0,wall_seconds=0),
        attribution_unknown=dict(initial=len(a['attribution_unknown']),final_development=len(b['attribution_unknown']),independent_test=len(h['attribution_unknown'])),
        unprotected_obligations=sorted({k.split('/')[-1] for k in h['misses']}),
        aborted_attempt=str(original/'model_calls/revision/cancellation.json'),compact_summary=str(cont/'summary.json'),
        adjudication_notes=a['adjudication_notes']+[
            'Compact feedback gave only correct-design legal FP examples, but its raw aggregate FP count included post-violation symptoms. This feedback-label limitation is retained.',
            'Full trigger-preservation gate rejected on unconfirmed/mismatched initial trigger metadata. No accepted final assertion set is claimed.',
            'Independent test ran a frozen rejected proposal only, with no subsequent edits or candidate selection.',
            '3 real model attempts exceed the original 2-call budget; only the continuation used compact feedback.'],
        scope='Native finite simulation of actual axis_fifo with artificial boundary faults. Not historical FIFO defect validation, not four-arm native comparison.')
    native.dump(out/'summary.json',summary)
    native.dump(out/'trigger_audit.json',dict(initial_property='mdata[0] == $past(mdata[0])',
        actual_antecedent='1 (implicit unconditional property evaluation when reset is inactive)',
        reported_diagnostic_trigger='svalid && sready && mvalid && mready',trigger_semantics='mismatch',
        native_execution_evidence='actual native assertion failures prove evaluation on those failure samples',
        prohibition='Do not use diagnostic marker counts as native cover or as proof of trigger preservation.'))
    print(json.dumps({k:summary[k] for k in ['status','initial','final_development','independent_test','model_cost','native_cost']},indent=2))


if __name__=='__main__':main()
