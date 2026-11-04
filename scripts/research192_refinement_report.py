"""Read-only audit and R0-R3 comparison from actual sealed model/native runs."""
import argparse
import json
from pathlib import Path
import research192_temporal_refinement as r


def report(prepared, run, out):
    out.mkdir(parents=True, exist_ok=False)
    protocol = r.s.read(prepared/'protocol.json')
    entries = r.s.read(prepared/'requests.json')
    rows = r.s.read(run/'results.json')
    if len(rows) != len(entries):
        raise ValueError('incomplete_fixed_population')
    checks, audited = [], []
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
        r.s.dump(out/'checks.json',checks)
        if not ok:raise ValueError(name)
    for item in entries:
        seed, strategy = item['seed'], item['strategy']
        folder = run/f'seed{seed}'/strategy
        row = next(v for v in rows if (v['seed'],v['strategy']) == (seed,strategy))
        request = r.s.read(folder/'request.preview.json')
        check(f'{seed}/{strategy} exact sealed request',request==r.s.read(r.ROOT/item['request']))
        initial = r.s.read(folder/'initial.json')
        terminal = r.s.read(folder/'terminal.json')
        freeze = r.s.read(folder/'frozen.json')
        check(f'{seed}/{strategy} freeze',freeze['candidate_sha256']==r.p.digest(terminal))
        model_path = folder/'model_call/result.json'
        model = r.s.read(model_path) if model_path.exists() else {}
        candidate_path = folder/'model_call/candidate.json'
        proposal = r.s.read(candidate_path) if candidate_path.exists() else None
        proposal_unknown = 0
        if proposal is not None:
            edit = r.s.read(folder/'model_call/model_edit.json')
            reconstructed = (r.apply_local_edits(initial,edit,r.s.read(folder/'localization.json'))
                             if strategy=='R3' else r.p.adapt(edit))
            check(f'{seed}/{strategy} model owned exact predicates',proposal==reconstructed)
            measured = r.s.read(folder/'measurement.json')
            proposal_unknown = len(measured['critical_unknown'])
            check(f'{seed}/{strategy} measured candidate binding',measured['candidate_sha256']==r.p.digest(proposal))
            decision = r.s.read(folder/'decision.json')
            check(f'{seed}/{strategy} retained/frozen decision',terminal==(proposal if decision['accepted'] else initial))
        calls = list((folder/'model_call').glob('attempt.json'))
        check(f'{seed}/{strategy} <=1 physical model call',len(calls)<=1 and row['model_calls']==len(calls))
        audited.append(dict(**row,candidate_status=model.get('candidate_status'),
            failure_reason=model.get('candidate_error') or model.get('error'),
            raw_model_output=r.s.rel(folder/'model_call'/('model_edit.json' if (folder/'model_call/model_edit.json').exists() else 'response.assembled.json')),
            initial_properties=len(initial),proposed_properties=len(proposal) if proposal else None,
            terminal_properties=len(terminal),source=r.s.rel(folder),
            necessary_obligation_fully_protected=bool(row['final_detected']==row['final_targets'] and row['final_targets']>0 and row['final_fp']==0 and row['final_unknown']==0)))
        audited[-1]['proposal_unknown'] = proposal_unknown
    check('fixed8 independent requests',sum(v['model_calls'] for v in audited)<=8)
    r.s.dump(out/'rows.json',audited)
    groups=[]
    for strategy in r.STRATEGIES:
        arm=[v for v in audited if v['strategy']==strategy]
        def total(field):return None if any(v.get(field) is None for v in arm) else sum(v[field] for v in arm)
        groups.append(dict(strategy=strategy,seeds=len(arm),
            fully_protected_runs=sum(v['necessary_obligation_fully_protected'] for v in arm),
            accepted=sum(v['accepted'] for v in arm),proposals=sum(v['candidate_generated'] for v in arm),
            fp=total('final_fp'),fn=total('final_fn'),unknown=total('final_unknown'),
            regression_proposals=total('regression_proposals'),accepted_regressions=total('accepted_regressions'),
            effective_rounds=total('effective_rounds'),model_calls=total('model_calls'),
            interface_failures=sum(v['candidate_status']=='interface_rejected' for v in arm),
            transport_failures=sum(v.get('model_status',v['status'])!='response_received' for v in arm),
            native_unknown_arms=sum(bool(v['proposal_unknown']) for v in arm),
            infrastructure_failures=sum(bool(v.get('infrastructure_failure')) for v in arm),
            prompt_tokens=total('prompt_tokens'),completion_tokens=total('completion_tokens'),
            physical_native_compiles=total('physical_native_compiles'),logical_native_compiles=total('logical_native_compiles'),
            proposed_properties=[v['proposed_properties'] for v in arm]))
    r.s.dump(out/'comparison.json',groups)
    pairing=[dict(seed=seed,causal_comparison_eligible=not any(
        v.get('infrastructure_failure') for v in audited if v['seed']==seed),
        interface_failures_remain_outcomes=True)
        for seed in sorted({v['seed'] for v in audited})]
    r.s.dump(out/'paired_eligibility.json',pairing)
    lines=['# R0–R3 same-evidence real-model comparison','',
        'Two paired seeds, one original FIFO parent bug, identical initial SVA and raw observations, one real model call per arm/seed. The shared initial candidate is the archived engineered partial seed from research188, not a newly model-generated initial assertion. These are development-gate results; independent acceptance is separate. Repeated seeds/transactions are not independent parent bugs.','',
        '| Strategy | Full retained-scope protection runs | Accepted / model attempts | FP / FN | Final unknown | Frontend / transport / native-unknown arms | Regression proposed / accepted | Effective rounds | Model calls | Prompt / completion tokens | Proposed properties per seed | Native compiles physical / logical |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for g in groups:
        lines.append(f"|{g['strategy']}|{g['fully_protected_runs']}/{g['seeds']}|{g['accepted']}/{g['model_calls']}|{g['fp']}/{g['fn']}|{g['unknown']}|{g['interface_failures']}/{g['transport_failures']}/{g['native_unknown_arms']}|{g['regression_proposals']}/{g['accepted_regressions']}|{g['effective_rounds']}|{g['model_calls']}|{g['prompt_tokens']}/{g['completion_tokens']}|{g['proposed_properties']}|{g['physical_native_compiles']}/{g['logical_native_compiles']}|")
    if all(g['fully_protected_runs']==g['seeds'] for g in groups):
        lines += ['', 'All strategies protect the complete finite obligation scope in both seeds. This pilot therefore establishes no effectiveness advantage for localization or historical protection. The ready/stalled applicability gap is explicit in the initial predicate and the shared evidence; even free rewriting can solve it. Property count and token use are descriptive costs, not proof of general superiority.']
    for failed in [x for x in audited if x['candidate_status']=='interface_rejected']:
        lines += ['', f"{failed['strategy']} seed {failed['seed']} produced a real response rejected by the frozen interface: {failed['failure_reason']}. Its original response is preserved at `{failed['raw_model_output']}`. It consumed a model attempt and tokens, received no semantic native verdict, and retained the prior candidate. This is an interface failure, not evidence that the historical gate itself harms protection or that temporal reasoning alone improves semantic repair."]
    for interrupted in [x for x in audited if x.get('infrastructure_failure')]:
        lines += ['', f"{interrupted['strategy']} seed {interrupted['seed']} was interrupted by {interrupted['infrastructure_failure']}; {interrupted['proposal_unknown']} native/paired-reference records remain unknown. The original initial candidate was retained. No model or native retry was made. Its retained-candidate misses are NOT algorithm regression, and its lost execution logs make recorded native time a lower bound. Keep this arm in the fixed accounting population but exclude it from claims comparing successful semantic repair rates; the requested fully paired mechanism comparison is incomplete."]
    for failed in [x for x in audited if x['strategy']=='R3' and x['candidate_status']=='interface_rejected']:
        edit_path=r.ROOT/failed['raw_model_output']
        value=r.s.read(edit_path)
        initial=r.s.read(r.ROOT/failed['source']/'initial.json')
        noops=[e for e in value.get('edits',[]) if e.get('op')=='replace_field' and any(
            a['label']==e.get('assertion') and a.get(e.get('field'))==e.get('value') for a in initial)]
        if noops:
            lines += ['', f"R3 seed {failed['seed']} exposes a concrete limitation of the local-edit contract: the model supplied the intended trigger edit plus {len(noops)} unchanged-field echo. The echoed field was outside localization, so the fixed adapter rejected the complete patch. This is over-strict interface handling, not a demonstrated temporal predicate error. No post-hoc no-op removal or rerun was used to convert it into success. A future separately versioned protocol can test whether tolerating byte-identical no-ops improves reliability without broadening the allowed semantic edit scope."]
    lines += ['', 'R3 only permits localized field replacements. A measured failed local attempt is required before obligation-aware composition; the one-call pilot does not exercise this fallback. Timing windows, transaction-matching and exception-localization interfaces have unit checks but no native validation in this FIFO-specific same-sample experiment.',
        'No-exposure Depth8 scenes are tracked outside detection denominators. The actual exposed target unit is one frame, never individual failed cycles. Monetary billing is unavailable and is not inferred from token counts.',
        'The separate handwritten qualification has a representative regression: replacing stalled-first protection with ready-first protection keeps the same total 2/4 detections while losing both previously protected transactions. R2/R3 reject it. That control validates the gate but is not a fresh-model improvement result.']
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    representatives={}
    positive=next((x for x in audited if x['strategy']=='R3' and x['effective_rounds']>0),None)
    paired_failure=(next((x for x in audited if positive and x['seed']==positive['seed']
                         and x['candidate_status']=='interface_rejected'
                         and (x.get('failure_reason') or {}).get('type')=='ValueError'),None)
                    or next((x for x in audited if positive and x['seed']==positive['seed']
                             and x['candidate_status']=='interface_rejected'),None))
    for kind, predicate in [('positive',lambda x:x['strategy']=='R3' and x['effective_rounds']>0),
                             ('failure',lambda x:not x['accepted'] or x['regression_proposals']>0)]:
        core_failure=next((x for x in audited if x['strategy']=='R3' and x['candidate_status']=='interface_rejected'),None)
        found=(core_failure or paired_failure or next((x for x in audited if predicate(x)),None)) if kind=='failure' else next((x for x in audited if predicate(x)),None)
        representatives[kind]=dict(status='observed' if found else 'not_observed_in_fixed_pilot',source=found['source'] if found else None)
        if found:
            folder=r.ROOT/found['source'];target=out/'representatives'/kind
            target.mkdir(parents=True)
            for name in ('initial.json','localization.json','evidence.json','decision.json','measurement.json','frozen.json'):
                if (folder/name).exists():(target/name).write_bytes((folder/name).read_bytes())
            for name in ('model_edit.json','result.json','response.assembled.json'):
                if (folder/'model_call'/name).exists():
                    (target/('model_'+name if name=='result.json' else name)).write_bytes((folder/'model_call'/name).read_bytes())
            initial=r.s.read(folder/'initial.json')
            (target/'initial.sva').write_text('\n'.join(
                f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']}));"
                for a in initial)+'\n')
            if (folder/'model_call/candidate.sva').exists():
                (target/'candidate.sva').write_bytes((folder/'model_call/candidate.sva').read_bytes())
            evidence=r.s.read(folder/'evidence.json')
            r.s.dump(target/'key_transactions.json',[x for x in evidence if x.get('label')=='violation'])
            note = ('This real model proposal was rejected before native execution. No waveform of this proposal exists. The key transactions and VCD links are explicitly BASELINE evidence only. The failure demonstrates interface drift; it does not test the history gate or semantic behavior of the rejected expressions.'
                    if found['candidate_status']=='interface_rejected' else
                    'The model-owned edit is bound to native measurement and the frozen terminal. Initial key transactions describe BASELINE evidence; native_after_waveforms.json contains only traces executed with the modified candidate.')
            (target/'CASE.md').write_text(note+'\n',encoding='utf-8')
            if found['candidate_generated']:
                native_folder=folder/'native'
                if found.get('native_reuse_source'):
                    native_folder=r.ROOT/found['native_reuse_source']
                native_jobs=r.s.read(native_folder/'executions.json')
                excerpts=[]
                for job in native_jobs:
                    if job['depth']!=16 or job['revision']!='before':continue
                    traces=r.s.traces(Path(job['folder']))
                    reference=r.p.q.reference(traces,job['depth'])
                    for event in reference['events']:
                        cycle=event['first']['cycle']
                        excerpts.append(dict(scope='ACTUAL_MODIFIED_CANDIDATE_NATIVE_EXECUTION',
                            scene=job['scene_id'],frame=event['frame'],first_cycle=cycle,
                            accepted_count=len(event['accepted']),output_handshake_count=len(event['outputs']),
                            samples=[v for v in traces if cycle-2<=v['cycle']<=cycle+2],
                            native_result=r.s.rel(Path(job['folder'])/'result.json'),
                            vcd=r.s.rel(Path(job['folder'])/'wave.vcd')))
                r.s.dump(target/'native_after_waveforms.json',excerpts)
    r.s.dump(out/'representatives.json',representatives)
    bindings=[prepared/'seal.json',prepared/'protocol.json',run/'results.json',Path(__file__)]
    r.s.dump(out/'source_bindings.json',{r.s.rel(x):r.s.sha(x) for x in bindings})
    print(json.dumps(groups),flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--prepared',type=Path,required=True)
    cli.add_argument('--run',type=Path,required=True)
    cli.add_argument('--out',type=Path,required=True)
    a=cli.parse_args();report(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
