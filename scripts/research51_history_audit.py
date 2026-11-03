"""Read-only source, raw native trace, model lineage and outcome audit for Ibex166.

No model calls or simulations. Outputs are separate from immutable run records.
"""
import argparse
import collections
import json
import re
from pathlib import Path
import research51_history_loop as loop


def audit(prep, run, out):
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
    for name, sha in loop.read(prep/'sealed.json').items():
        check('sealed/'+name, loop.digest(prep/name) == sha)
    for name, sha in loop.read(prep/'source_hashes.json').items():
        check('snapshot/'+name, loop.digest(run/'source_snapshot'/name) == sha)
        check('executed_source/'+name, loop.digest(loop.ROOT/'scripts'/name) == sha)
    binding = loop.read(prep/'source_binding.json')
    for name, sha in binding['source_sha256'].items():
        check('original_rtl/'+name, loop.digest(prep/name) == sha == loop.digest(loop.UPSTREAM/name))
    commit = loop.read(loop.UPSTREAM/'fix_commit.json')
    check('upstream_parent', commit['sha'] == binding['after_commit'] and binding['before_commit'] in [p['sha'] for p in commit['parents']])
    history = loop.read(prep/'history_cases.json')
    search = loop.read(prep/'search_cases.json')
    check('history_search_disjoint', not ({t['instruction'] for t in history} & {t['instruction'] for t in search}))
    current = previous = accepted = feedback = None
    decisions = []; calls = []; versions = []; examples = []
    all_native = []
    for folder in sorted(run.glob('v[0-9]*')):
        index = int(folder.name[1:]); model = folder/'model_call'
        call = loop.read(model/'result.json'); calls.append(call)
        phase = 'refinement' if current is not None else 'initial_generation'
        expected_payload = loop.payload(prep, current, feedback, phase)
        request = loop.read(model/'request.json')
        check(f'v{index}/exact_allowed_payload', request == expected_payload)
        if index == 0:
            check('initial_sealed_request', request == loop.read(prep/'request.preview.json'))
        response = loop.read(model/'response.assembled.json')
        value = json.loads(response['message']['content'])
        check(f'v{index}/raw_model_edit', value == loop.read(model/'model_edit.json'))
        events = [json.loads(line) for line in (model/'response.events.jsonl').read_text().splitlines()]
        content = ''.join(c.get('delta', {}).get('content') or '' for e in events for c in e.get('choices', []) if c.get('index', 0) == 0)
        check(f'v{index}/stream_lineage', content == response['message']['content'])
        check(f'v{index}/actual_usage', any(e.get('usage', {}).get('prompt_tokens') == call['prompt_tokens'] and e.get('usage', {}).get('completion_tokens') == call['completion_tokens'] for e in events if e.get('usage')))
        check(f'v{index}/terminal_no_retry', call['stream_terminal_received'] and call['retries'] == 0)
        try:
            candidate = loop.assemble(value, current)
        except (AssertionError, KeyError, TypeError):
            check(f'v{index}/interface_rejection', call['candidate_status'] == 'interface_rejected' and not (model/'candidate.json').exists())
            feedback = dict(last_actual_native_feedback=feedback, latest_interface_or_transport_failure=call)
            decisions.append(dict(version=index, accepted=False, reason='no_executable_model_candidate'))
            versions.append(dict(version=index, status='interface_rejected', error=call.get('candidate_error')))
            continue
        check(f'v{index}/exact_model_candidate', candidate == loop.read(model/'candidate.json'))
        datasets = []
        for cohort, txns in [('history', history), ('search', search)]:
            base = folder/cohort; result = loop.read(base/'result.json'); datasets.append(result)
            rows = loop.samples(txns, cohort)
            check(f'v{index}/{cohort}/inputs', rows == loop.read(base/'samples.json') and txns == loop.read(base/'transactions.json'))
            raw = {}; markers = {}; configs = loop.CONFIGS
            for rev in ('before', 'after'):
                nr = loop.read(base/rev/'result.json'); all_native.append(nr)
                check(f'v{index}/{cohort}/{rev}/compiled_executed', nr['compile_status']=='passed' and nr['execution_status']=='completed')
                check(f'v{index}/{cohort}/{rev}/model_in_testbench', (base/rev/'tb.sv').read_text() == loop.bench(candidate, rows, configs, base/'stimulus.txt'))
                check(f'v{index}/{cohort}/{rev}/source_command', all(str(prep/rev/n) in nr['compile']['argv'] for n in ('ibex_decoder.sv','ibex_defines.sv')))
                check(f'v{index}/{cohort}/{rev}/wave', (base/rev/'wave.vcd').stat().st_size > 0)
                log = (base/rev/'execute.log').read_text()
                trace = {}; mm = {'TRIGGER':set(), 'ASSERT_FAIL':set()}
                for line in log.splitlines():
                    if line.startswith('TRACE '):
                        f = dict(x.split('=') for x in line.split()[1:]); sid = int(f['sample'])
                        if sid in trace: raise AssertionError('duplicate native sample')
                        trace[sid] = f
                    m = re.fullmatch(r'(TRIGGER|ASSERT_FAIL) (\w+) cycle=(-?\d+)', line)
                    if m: mm[m[1]].add((m[2], int(m[3])))
                check(f'v{index}/{cohort}/{rev}/complete_samples', set(trace)==set(range(len(rows))) and 'NATIVE_RUN_COMPLETE' in log)
                check(f'v{index}/{cohort}/{rev}/trace_alignment', all(int(trace[r['sample_id']]['instr'],16)==r['instruction'] and int(trace[r['sample_id']]['new'])==r['instr_new'] and int(trace[r['sample_id']]['txn'])==r['transaction_id'] and int(trace[r['sample_id']]['phase'])==r['phase'] for r in rows))
                raw[rev] = trace; markers[rev] = mm
            oracle_errors = []; trigger_errors = []
            for row in result['ledger']:
                s = row['sample']; sid = s['sample_id']; cfg = row['configuration']; ci = configs.index(cfg); rev = row['revision']
                expected = loop.historical.oracle(s['instruction'],s['instr_new'],cfg)
                observed = {v:(int(raw[v][sid]['observed'],2)>>ci)&1 for v in raw}
                fixed_ok = observed['after'] == expected
                if row['expected'] != expected or row['observed'] != observed[rev] or row['oracle']['verdict'] != ('violated' if observed[rev]!=expected else 'satisfied') or not fixed_ok:
                    oracle_errors.append(row['evidence_id'])
                for a in row['native']['assertions']:
                    prop = next(p for p in candidate['assertions'] if p['id']==a['id'])
                    name = a['id']+f'_c{ci}'
                    trigger = (name,sid-prop['delay']) in markers[rev]['TRIGGER']
                    failed = (name,sid) in markers[rev]['ASSERT_FAIL']
                    detected = rev=='before' and observed[rev]!=expected and fixed_ok and trigger and failed and (name,sid) not in markers['after']['ASSERT_FAIL']
                    if (trigger,failed,detected)!=(a['trigger'],a['failed'],a['causal_detection']):
                        trigger_errors.append(row['evidence_id'])
            info = loop.acceptance.inspect(result['ledger'])
            check(f'v{index}/{cohort}/raw_oracle_agreement', not oracle_errors)
            check(f'v{index}/{cohort}/raw_cover_and_failure_agreement', not trigger_errors)
            check(f'v{index}/{cohort}/counts_mapping', result['counts']=={k:len(info[k]) for k in result['counts']} and result['mapping']==info['mapping'] and not info['errors'])
            check(f'v{index}/{cohort}/all_rows_present', len(result['ledger']) == len(rows)*len(configs)*2)
            check(f'v{index}/{cohort}/required_triggers', sorted(result['required_untriggered'])==sorted(k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']))
            check(f'v{index}/{cohort}/feedback', loop.evidence(result)==loop.read(folder/f'{cohort}_evidence.json'))
            per_ob = {}
            for ob in sorted(result['mapping']):
                subset=[r for r in result['ledger'] if r['obligation']==ob]; sub=loop.acceptance.inspect(subset)
                per_ob[ob]=dict(rows=len(subset),violations=sum(r['oracle']['verdict']=='violated' for r in subset),
                    detections=len(sub['detections']),misses=len(sub['misses']),false_positives=len(sub['false_positives']),
                    unknown=len(sub['unknown']),triggers=len(sub['triggers']),
                    missing_required=sum(r['required'] and r['evidence_id'] not in sub['triggers'] for r in subset))
            if index==1 and cohort=='search':
                for finding in loop.evidence(result)['independent_findings']:
                    row=finding['row']; word=row['sample']['instruction']
                    examples.append(dict(finding=finding,instruction_hex=f'0x{word:08x}',bit28=(word>>28)&1,bit31=(word>>31)&1,
                        fixed_observed=next(r['observed'] for r in result['ledger'] if r['sample']==row['sample'] and r['configuration']==row['configuration'] and r['revision']=='after')))
            versions.append(dict(version=index,cohort=cohort,counts=result['counts'],per_obligation=per_ob,
                sample_count=len(rows),transaction_count=len(txns),configuration_count=len(configs),
                missing_required=len(result['required_untriggered']),query_mechanism_count=len(loop.evidence(result)['independent_findings'])))
        h,s=datasets
        full=dict(healthy=h['healthy'] and s['healthy'],ledger=h['ledger']+s['ledger'],
            counts={k:h['counts'][k]+s['counts'][k] for k in h['counts']},required_untriggered=h['required_untriggered']+s['required_untriggered'])
        verdict=loop.decide(previous,full) if previous is not None else dict(accepted=loop.admissible(full),reasons=[] if loop.admissible(full) else [dict(kind='initial_target_or_legal_or_trigger_failure')])
        check(f'v{index}/decision_recomputed', verdict==loop.read(folder/'decision.json'))
        decisions.append(dict(version=index,accepted=verdict['accepted'],phase=phase))
        feedback=dict(actual_proposed_assertions=candidate,search=loop.evidence(s),history=loop.evidence(h),decision=verdict)
        if current is None: current=candidate; previous=full
        if verdict['accepted']: accepted=candidate; current=candidate; previous=full
    outcome=loop.read(run/'outcome.json')
    check('bounded_calls', len(calls)==outcome['calls']<=3)
    check('decisions', decisions==outcome['decisions'])
    check('actual_terminal_no_accepted_version', accepted is None and outcome['status']=='no_accepted_version' and outcome['accepted_candidate_sha256'] is None)
    check('no_premature_freeze_or_test', not any((run/n).exists() for n in ('freeze.json','frozen_candidate.json','independent_split.json','independent')))
    first=loop.read(run/'v1/model_call/candidate.json');last=loop.read(run/'v2/model_call/candidate.json')
    signature=lambda a:(re.sub(r'\s+','',a['antecedent']),re.sub(r'\s+','',a['consequent']),a['timing'],tuple(sorted(a['obligations'])))
    old_signatures={signature(a) for a in first['assertions']}
    repeated=[a['id'] for a in last['assertions'][len(first['assertions']):] if signature(a) in old_signatures]
    check('observed_duplicate_addition', repeated==['a2'])
    search_findings=loop.read(run/'v1/search_evidence.json')['independent_findings']
    history_findings=loop.read(run/'v1/history_evidence.json')['independent_findings']
    key=lambda f:(f['kind'],f['mechanism'],f['row']['revision'])
    extra={key(f) for f in search_findings}-{key(f) for f in history_findings}
    check('no_extra_search_mechanism_over_history', not extra)
    cost=dict(model_calls=len(calls),prompt_tokens=sum(c['prompt_tokens'] for c in calls),completion_tokens=sum(c['completion_tokens'] for c in calls),
        model_wall_seconds=sum(c['wall_seconds'] for c in calls),native_compile_calls=len(all_native),native_full_execute_calls=len(all_native),dedicated_smoke_calls=0,
        native_compile_seconds=sum(n['compile']['wall_seconds'] for n in all_native),native_execute_seconds=sum(n['execute']['wall_seconds'] for n in all_native),
        formal_calls=0,monetary_cost=None,usage_unavailable_calls=sum(not c['usage_available'] for c in calls),
        accounting_note='Generic cost.json compile_smoke_execute_calls are full test replays here; not extra executions.')
    loop.dump(out/'audit.json',dict(passed=all(c['passed'] for c in checks),checks=checks,failed=[c for c in checks if not c['passed']],model_calls=0,native_calls=0))
    loop.dump(out/'metrics.json',versions);loop.dump(out/'examples.json',examples);loop.dump(out/'cost_roles.json',cost)
    loop.dump(out/'diagnosis.json',dict(duplicate_added_properties=repeated,
        actual_native_feedback_reached_model=True,new_gap_mechanisms_beyond_history=len(extra),
        failing_mechanism='Model checks instr[31] rather than required instr[28]; cover remains zero on independently required OP samples.',
        evidence=examples,not_a_tool_failure=True,manual_sva_repair_performed=False,
        next_step='A separate development-only bitfield/applicability gate should first require the model to identify the relevant bit and classify observed OP/control samples against an independent decoder. Do not generate another SVA until that gate passes. Reject duplicate added predicates before spending native compile budget. Any new SVA must still pass original native target/history checks before freezing.',
        next_step_status='Not implemented or model-validated in this sealed run; no extra calls authorized.'))
    loop.dump(out/'parent_result.json',dict(parent_bug='lowRISC/ibex#166',provenance='unmodified original historical decoder',
        confirmed_obligations=2,development_protected_obligations=1,accepted_new_versions=0,complete_case_passed=False,
        independent_test='not_started_no_accepted_version',search_extra_mechanism_beyond_history=0,
        model_refinement_attempted=True,model_refinement_successful=False,stat='unknown',original_fifo_presented='unknown',
        scope='Finite module simulation. No full-core retirement/trap reproduction or formal proof. Search pool finds the same OP gap already present in history.'))
    print(json.dumps(dict(passed=all(c['passed'] for c in checks),checks=len(checks),failed=[c['name'] for c in checks if not c['passed']],cost=cost)))
    assert all(c['passed'] for c in checks)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
