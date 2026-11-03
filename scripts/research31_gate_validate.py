"""Validate gate v1 on archived development and fresh native replay; no LLM."""
import argparse
import copy
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research28_valid_runtime as extension
import research31_gate as gate
from research15_evidence import merge_ledgers
from research26_model import replace_one

ROOT = loop.ROOT
read, dump = loop.read, loop.dump
PREP = ROOT/'deliverables/research30_ablation_prepare_20261020_r02'
RUN = ROOT/'deliverables/research30_ablation_20261020_r01'


def check(out, name, before, after, targets, expected):
    verdict = gate.decide(before, after, targets)
    dump(out/f'{name}.json', verdict)
    assert verdict['accepted'] == expected, (name, verdict['reasons'])
    return dict(name=name, expected=expected, accepted=verdict['accepted'],
                reasons=[r['kind'] for r in verdict['reasons']],
                exempt_trigger_losses=len(verdict['exempt_nonapplicable_trigger_losses']))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();out=args.out.resolve();assert ROOT in out.parents
    loop.prepare(out)
    for src in (Path(__file__), Path(gate.__file__)):
        shutil.copy2(src,out/'source_snapshot'/src.name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (out/'source_snapshot').glob('*.py')})
    dump(out/'protocol.json',dict(gate=gate.VERSION,model_calls=0,
        scope='Development-only algorithm validation; archived research30 independent batch excluded. Hand-weakened property is an explicit negative control, never called a model output.',
        old_results_immutable=True))
    baseline=merge_ledgers([read(PREP/'core/history/result.json')['group'],
                           read(PREP/'core/acquired/result.json')['group']])['ledger']
    targets=sorted(loop.inspect(baseline)['misses'])
    b=read(RUN/'historical_audit/B/result.json')['group']['ledger']
    checks=[check(out/'archived','valid_B',baseline,b,targets,True)]
    d=read(RUN/'arms/D/proposed/result.json')['group']['ledger']
    checks.append(check(out/'archived','unrepaired_D',baseline,d,targets,False))
    c_before=read(RUN/'arms/C/before/result.json')['group']['ledger']
    c_after=read(RUN/'arms/C/proposed/result.json')['group']['ledger']
    checks.append(check(out/'archived','data_only_C_no_search_target',c_before,c_after,[],True))
    # Fault injection at the gate boundary, not simulated RTL outcomes.
    # These prove unknown/missing replay cannot become passes through exemption.
    old=loop.inspect(baseline);new=loop.inspect(b)
    key=next(iter(old['triggers']-new['triggers']))
    for name, mutate in [
        ('missing_native_source',lambda row:row.update(source_directory=str(out/'absent_source'))),
        ('unknown_native_execution',lambda row:row['native'].update(execution='unknown')),
        ('changed_evidence_identity',lambda row:row.update(stimulus_sha256='invalid')),
    ]:
        altered=copy.deepcopy(b)
        mutate(next(r for r in altered if r['evidence_id']==key))
        checks.append(check(out/'gate_boundary_negative_controls',name,baseline,altered,targets,False))
    checks.append(check(out/'gate_boundary_negative_controls','missing_historical_row',
        baseline,[r for r in b if r['evidence_id']!=key],targets,False))
    history=read(PREP/'history_cases.json')
    reset_ids={old['rows'][k]['scenario_id'] for k in old['triggers']-new['triggers']}
    cases=[history[0]]+[c for c in history if c['id'] in reset_ids]+read(PREP/'acquired_cases.json')
    dump(out/'native_cases.json',cases)
    initial=read(RUN/'shared_initial.json');valid=read(RUN/'arms/B/frozen_candidate.json')
    weakened=replace_one(dict(operation='replace_one',assertion_id='a2',
        assertions=[dict(obligation=['stall_stability'],
            property="1'b0 |=> mvalid && mdata == $past(mdata)")],
        reason='Explicit developer negative control: antecedent suppression, not a model-generated repair.'),valid)
    dump(out/'negative_control.json',weakened)
    with extension.installed():
        before=loop.replay(initial,out/'native/initial',cases)
        after=loop.replay(valid,out/'native/valid_B',cases)
        bad=loop.replay(weakened,out/'native/suppressed_antecedent',cases)
    assert all(r['healthy'] for r in (before,after,bad))
    before_ledger=before['group']['ledger'];after_ledger=after['group']['ledger']
    target_native=sorted(loop.inspect(before_ledger)['misses'])
    checks.append(check(out/'native_gates','valid_B',before_ledger,after_ledger,target_native,True))
    checks.append(check(out/'native_gates','suppressed_antecedent',after_ledger,bad['group']['ledger'],target_native,False))
    for name,result in [('initial',before),('valid_B',after),('suppressed_antecedent',bad)]:
        print(name,result['counts'],flush=True)
    dump(out/'outcome.json',dict(status='gate_validated_on_recorded_scope',checks=checks,
        native_counts={n:r['counts'] for n,r in [('initial',before),('valid_B',after),('suppressed',bad)]},
        formal_calls=0,model_calls=0,independent_tests_used=False))
    print(checks,flush=True)


if __name__=='__main__':main()
