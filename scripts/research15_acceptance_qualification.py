"""Adversarial admission tests. Synthetic fixtures are NOT research observations."""
from copy import deepcopy
from research15_acceptance import decide


def run():
    def row(key, verdict, trigger=True, failed=False, causal=False, assertion='a'):
        return dict(evidence_id=key, obligation='order_payload', stimulus_sha256='fixture-only',
                    oracle=dict(legality='legal', verdict=verdict, validator='synthetic_test_fixture'),
                    native=dict(compile='ok', support='supported', execution='ok',
                                trigger_source='property_antecedent_cover', assertions=[
                                    dict(id=assertion, trigger=trigger, failed=failed, causal_detection=causal)]))
    old = [row('legal', 'satisfied'), row('historical_bug', 'violated', failed=True, causal=True),
           row('new_gap', 'violated')]
    good = deepcopy(old)
    good[2]['native']['assertions'].append(dict(id='complementary', trigger=True, failed=True, causal_detection=True))
    tests = []
    def check(name, value, expected, reason=None):
        decision = decide(old, value, ['new_gap'])
        assert decision['accepted'] == expected, (name, decision)
        assert reason is None or reason in {r['kind'] for r in decision['reasons']}, (name, decision)
        tests.append(dict(name=name, passed=True, decision=decision))
    check('complementary_set_repairs_gap', good, True)
    bad=deepcopy(good); bad.pop(0)
    check('deleting_historical_legal_row_rejected', bad, False, 'missing_historical_replay')
    bad=deepcopy(good); bad[0]['native']['assertions'][0]['failed']=True
    check('new_false_positive_rejected', bad, False, 'new_legal_false_positive')
    bad=deepcopy(good); bad[1]['native']['assertions'][0].update(failed=False, causal_detection=False)
    check('historical_detection_loss_rejected', bad, False, 'lost_target_detection')
    bad=deepcopy(good); bad[0]['native']['assertions'][0]['trigger']=False
    check('antecedent_masking_rejected', bad, False, 'lost_obligation_trigger')
    bad=deepcopy(good); bad[0]['native']['trigger_source']='model_declared_boolean'
    check('model_claim_not_native_cover', bad, False, 'unconfirmed_replay')
    bad=deepcopy(good); bad[1]['oracle']['verdict']='satisfied'
    check('relabeling_target_rejected', bad, False, 'changed_evidence_identity')
    bad=deepcopy(good); bad[1]['native']['assertions'][0]['causal_detection']=None
    check('attribution_unknown_rejected', bad, False, 'unconfirmed_replay')
    bad=deepcopy(good); bad[0]['native']['support']='unsupported'
    check('unsupported_rejected', bad, False, 'unconfirmed_replay')
    bad=deepcopy(good); bad.append(deepcopy(good[0]))
    check('duplicate_evidence_id_rejected', bad, False, 'malformed_ledger')
    bad=deepcopy(good); bad[2]['native']['assertions']=[dict(id='masked', trigger=False, failed=False, causal_detection=False)]
    check('vacant_current_target_rejected', bad, False, 'current_gap_not_confirmed_repaired')
    renamed=deepcopy(good)
    for r in renamed:
        for a in r['native']['assertions']: a['id']='renamed_'+a['id']
    check('assertion_id_is_not_evidence_identity', renamed, True)
    return dict(passed=True, tests=tests, scope='Synthetic admission unit qualification only; no model or RTL claims.')


if __name__ == '__main__':
    import json
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args=parser.parse_args()
    result=run()
    path=Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'], tests=len(result['tests']))))
