"""Adversarial adapter fixtures; these are unit checks, not RTL experiments."""
import copy
from research15_acceptance import inspect, decide
from research15_evidence import paired_ledger, merge_ledgers


def run():
    def rec(mode='correct', violations=(), fails=(), delay=0, triggers=(1,2,4,5)):
        return dict(mode=mode, directory='synthetic_fixture',
            candidate=dict(assertions=[dict(id='a0',obligations=['order_payload'],derived_delay=delay)]),
            trace=[dict(cycle=i,rst=int(i in (0,3)),svalid=0,sready=1,sdata=0,mready=1,mvalid=0,mdata=0) for i in range(6)],
            oracle=dict(legality='legal',violations=[dict(cycle=i,obligation='order_payload',passed=False) for i in violations],unknown=[]),
            native=dict(compile_status='passed',execution_status='completed',tool_support_status='supported_for_compiled_constructs',
                trigger_measurement='native cover property',
                failures=[dict(id='a0',detail=f'cycle={i}') for i in fails],
                triggers=[dict(id='a0',detail=f'cycle={i}') for i in triggers]))
    checks=[]
    def check(name, condition):
        assert condition,name
        checks.append(dict(name=name,passed=True))
    fixed=rec()
    result=paired_ledger(fixed,rec('corrupt',violations=(1,2,4,5),fails=(1,2,4,5)),'fixture')
    info=inspect(result['ledger'])
    check('only_first_violation_per_reset_epoch_attributable',len(info['detections'])==2 and len(result['exclusions'])==2)
    result=paired_ledger(fixed,rec('corrupt',violations=(2,5),fails=(1,2,5)),'fixture')
    info=inspect(result['ledger'])
    check('prior_false_alarm_confounds_target_but_reset_restores_attribution',len(info['detections'])==1 and len(info['unknown'])==1 and len(info['false_positives'])==1)
    result=paired_ledger(rec(delay=1),rec('corrupt',violations=(2,),fails=(2,),delay=1,triggers=(1,)),'fixture')
    check('nonoverlap_uses_previous_native_cover',len(inspect(result['ledger'])['detections'])==1)
    result=paired_ledger(rec(delay=1),rec('corrupt',violations=(4,),fails=(4,),delay=1,triggers=(3,)),'fixture')
    check('reset_disabled_antecedent_cannot_count_as_trigger',len(inspect(result['ledger'])['detections'])==0)
    result=paired_ledger(fixed,rec('corrupt',fails=(2,)),'fixture')
    check('assertion_failure_does_not_create_oracle_target',len(inspect(result['ledger'])['detections'])==0 and len(inspect(result['ledger'])['false_positives'])==1)
    result=paired_ledger(rec(fails=(1,)),rec('corrupt',violations=(1,),fails=(1,)),'fixture')
    check('same_sample_fixed_false_alarm_cannot_be_detection',len(inspect(result['ledger'])['detections'])==0 and bool(inspect(result['ledger'])['unknown']))
    other=rec('corrupt',violations=(2,),fails=(2,))
    other['candidate']['assertions'][0]['obligations']=['no_unsolicited_output']
    result=paired_ledger(fixed,other,'fixture')
    check('different_obligation_alarm_is_not_silent_set_miss',len(inspect(result['ledger'])['misses'])==0 and bool(inspect(result['ledger'])['unknown']))
    no_cover=rec('corrupt',violations=(2,),fails=(2,));no_cover['native']['trigger_measurement']='model asserted trigger'
    result=paired_ledger(fixed,no_cover,'fixture')
    check('procedural_trigger_not_native_evidence',bool(inspect(result['ledger'])['unknown']))
    wrong_input=rec('corrupt',violations=(2,),fails=(2,));wrong_input['trace'][1]['sdata']=8
    result=paired_ledger(fixed,wrong_input,'fixture')
    check('unequal_paired_inputs_unknown',not result['stats']['paired_inputs_identical'] and bool(inspect(result['ledger'])['unknown']))
    partial=rec('corrupt');partial['oracle']['unknown']=[dict(reason='trace_length_mismatch')]
    result=paired_ledger(fixed,partial,'fixture')
    check('incomplete_oracle_cannot_silently_pass',bool(inspect(result['ledger'])['unknown']))
    result=paired_ledger(fixed,None,'fixture')
    check('identical_control_rows_deduplicate',len(merge_ledgers([result,result])['ledger'])==len(result['ledger']))
    no_properties=copy.deepcopy(result['ledger'])
    for r in no_properties:r['native']['assertions']=[]
    check('known_empty_projection_is_gap_not_unknown',not inspect(no_properties)['unknown'])
    check('deleting_obligation_properties_loses_triggers',not decide(result['ledger'],no_properties)['accepted'])
    return dict(passed=True,tests=checks,scope='Synthetic adapter qualification; no actual model/simulation claimed.')


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args()
    result=run();Path(args.out).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=result['passed'],tests=len(result['tests']))))
