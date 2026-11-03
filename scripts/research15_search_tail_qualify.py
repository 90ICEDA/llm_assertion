"""Replay-only qualification of isolated terminal loss; no model or search credit."""
import json
from research15_search_runtime import ROOT,execute,write_json
from research15_search_experiment import stimulus

if __name__=='__main__':
    root=ROOT/'deliverables/research15_search_20261015_r01'
    compiled=json.loads((root/'engineering_qualification/compiled/compiled.json').read_text())
    out=root/'tail_loss_qualification';out.mkdir(exist_ok=False)
    rows=stimulus(2026101551,'tail_loss');write_json(out/'stimulus.json',rows)
    result={m:execute(compiled,out/m,rows,m) for m in ('correct','drop')}
    checks=dict(correct_accepted_inputs=len(result['correct']['oracle']['transactions']),
        drop_accepted_inputs=len(result['drop']['oracle']['transactions']),
        correct_violations=result['correct']['oracle']['violations'],drop_violations=result['drop']['oracle']['violations'])
    passed=checks['correct_accepted_inputs']==4 and checks['drop_accepted_inputs']==4 and not checks['correct_violations'] and len(checks['drop_violations'])==1 and checks['drop_violations'][0]['obligation']=='drain_no_loss'
    write_json(out/'summary.json',dict(passed=passed,provenance='engineering_harness_qualification_not_model_or_search_evidence',
        reused_compilation=compiled['directory'],native_replays=2,checks=checks))
    print(json.dumps(dict(passed=passed,checks=checks),indent=2))
