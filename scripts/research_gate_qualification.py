"""Acceptance decisions under adversarial set changes; deterministic unit tests."""
import copy
import json
from pathlib import Path
from research_acceptance_gate import decide, merge


def run():
    before=dict(status='ok',false_positives=['legal:old'],detections=['bug:txn1:data'],
                effective_triggers=['legal:txn1:data'],misses=['bug:txn2:latency'],resolved_keys=['bug:txn1:data'])
    improved=copy.deepcopy(before)
    improved.update(false_positives=[],misses=[],resolved_keys=['legal:old','bug:txn1:data','bug:txn2:latency'],
                    detections=['bug:txn1:data','bug:txn2:latency'])
    cases=[]
    def test(name, after, target, expected, reason=None):
        result=decide(before,after,target)
        assert result['accepted']==expected,(name,result)
        if reason:assert reason in {r['kind'] for r in result['reasons']},(name,result)
        cases.append(dict(name=name,decision=result,passed=True))
    test('complementary_set_repairs_gap_preserves_history',improved,['bug:txn2:latency'],True)
    bad=copy.deepcopy(improved);bad['false_positives']=['legal:new']
    test('new_false_alarm_despite_higher_detection',bad,[],False,'new_legal_false_positive')
    bad=copy.deepcopy(improved);bad['detections']=['bug:txn2:latency']
    test('fix_current_loses_historical_detection',bad,['bug:txn2:latency'],False,'lost_target_detection')
    bad=copy.deepcopy(improved);bad['effective_triggers']=[]
    test('strengthened_mask_evades_trigger',bad,[],False,'lost_effective_trigger')
    bad=copy.deepcopy(before);bad['misses']=[]
    test('unknown_attribution_is_not_target_repair',bad,['bug:txn2:latency'],False,'current_gap_not_confirmed_repaired')
    bad=copy.deepcopy(improved);bad['status']='tool_unsupported'
    test('unsupported_not_pass',bad,[],False,'replay_unknown')
    test('unchanged_current_gap_rejected',before,['bug:txn2:latency'],False,'current_gap_not_confirmed_repaired')
    assert merge([])['status']=='unknown'
    assert merge([before,before])['detections']==before['detections']
    return dict(passed=True,cases=cases,limitations='Logic qualification only; not an end-to-end research result.')


if __name__=='__main__':
    out=Path(__file__).resolve().parents[1]/'deliverables/research_integration_20261014_r01/gate_qualification.json'
    out.write_text(json.dumps(run(),indent=2)+'\n')
    print('7 acceptance-gate qualification scenarios passed')
