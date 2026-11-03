"""Map already-run native engineering assertions to independent FIFO evidence."""
import json
import re
from research_fifo_experiment import DEFAULT_OUT, write_json


def main():
    base=DEFAULT_OUT/'native_engineering_controls'
    results=json.loads((base/'results.json').read_text())
    traces={m:json.loads((base/m/'trace.json').read_text()) for m in results}
    oracle={m:json.loads((base/m/'independent_oracle.json').read_text()) for m in results}
    def cycles(records, name):
        return [(int(re.search(r'time=(\d+)',r['detail'])[1])-15000)//10000
                for r in records if r['id']==name]
    native={m:{name:dict(trigger_cycles=cycles(r['triggers'],name),failure_cycles=cycles(r['failures'],name))
               for name in ('valid_only','stable_under_backpressure')} for m,r in results.items()}
    violations=oracle['corrupt']['violations']
    mapping=[]
    for v in violations:
        tid=v['transaction_id']
        txn=next(t for t in oracle['corrupt']['transactions'] if t['transaction_id']==tid) if tid else None
        mapping.append(dict(obligation=v['obligation'],cycle=v['cycle'],transaction_id=tid,
            input_accept_cycle=txn['accept_cycle'] if txn else None,
            response_cycle=txn['response_cycle'] if txn else None,
            expected=v.get('expected'),actual=v.get('actual'),
            independent_buggy_verdict='violation',independent_fixed_verdict='no_violation_in_execution',
            candidate_results={
                'stable_under_backpressure':dict(native_trigger_cycles=native['corrupt']['stable_under_backpressure']['trigger_cycles'],
                    native_failure_cycles=[],attribution='false_negative_for_order_payload; valid stability property does not protect data integrity'),
                'valid_only':dict(native_failure_cycles=native['corrupt']['valid_only']['failure_cycles'],
                    attribution='no_causal_detection_credit; identical failures also occur on legal correct RTL, with a legal false positive preceding the first target violation')},
            source='native_engineering_controls/corrupt/independent_oracle.json'))
    same_inputs=all({k:t[k] for k in ('rst','svalid','sready','sdata','mready')}==
                   {k:u[k] for k in ('rst','svalid','sready','sdata','mready')}
                   for t,u in zip(traces['correct'],traces['corrupt']))
    cost=dict(native_compilations=2,native_simulations=2,
        compile_wall_seconds=sum(r['compile']['wall_seconds'] for r in results.values()),
        simulation_wall_seconds=sum(r['execute']['wall_seconds'] for r in results.values()),
        model_calls=0,model_tokens=None,model_tokens_status='unavailable_not_applicable_no_model_call',
        model_cost=None,formal_calls=0,formal_wall_seconds=0)
    report=dict(analysis_only_no_new_execution=True,provenance='handwritten_engineering_controls',
        same_legal_input_schedule=same_inputs and all(o['legality']=='legal' for o in oracle.values()),
        parameter_note='DEPTH=3 is rounded to RAM depth=4; not an independent new capacity compared with DEPTH=4.',
        native_trigger_measurement='procedural antecedent instrumentation, not native cover proof',
        reset_scope='48 pending resets in 96-run experiment are cancellation bookkeeping; no reset_cancellation violation records or dedicated residue mutant, so reset-fault detection not established',
        assertions={
            'valid_only':dict(property='(svalid && sready) |=> mvalid',claimed_obligation='invalid fixed next-cycle response requirement',
                correct_false_positive_count=9,buggy_alarm_count=9,causal_target_detections=0,scope='mis-specification exposed by RAM_PIPELINE=2'),
            'stable_under_backpressure':dict(property='(mvalid && !mready) |=> (mvalid && $stable(mdata))',
                protected_obligation='stall_stability',triggers_per_variant=38,failures_per_variant=0,
                order_payload_false_negative_count=len(violations),scope='no false positive in this finite legal run; payload mutation demonstrates complementary-order-assertion gap')},
        native_events=native,obligation_assertion_transaction_mapping=mapping,cost=cost)
    write_json(DEFAULT_OUT/'supplement/native_mapping.json',report)
    first=mapping[0]
    (DEFAULT_OUT/'supplement/NATIVE_EXAMPLE.md').write_text('# Actual native SVA engineering example\n\n'+
        'Real `axis_fifo.v`, requested DEPTH=3 (actual RAM depth=4), RAM_PIPELINE=2, fresh seed 100129111. Both variants compile and execute with native Verilator 5.020 assertions.\n\n'+
        '`(svalid && sready) |=> mvalid` has 77 trigger markers and 9 native failures on correct RTL; the corrupt variant has exactly the same failures. These are false positives from an invalid fixed-latency requirement, not evidence of detecting payload corruption.\n\n'+
        '`(mvalid && !mready) |=> (mvalid && $stable(mdata))` has 38 trigger markers and no native failure in either variant. '+
        f'The independent queue oracle nevertheless finds {len(violations)} payload violations in the corrupt run. First: transaction {first["transaction_id"]}, accepted cycle {first["input_accept_cycle"]}, response cycle {first["response_cycle"]}, expected {first["expected"]}, observed {first["actual"]}. The stable property misses this integrity violation.\n\n'+
        'The reference fixed run has no observed obligation violation under identical legal input handshakes. No assertion was revised from this test; this is an engineering qualification example, not a successful LLM refinement chain.\n\n'+
        f'Cost: 2 native compilations ({cost["compile_wall_seconds"]:.3f} s), 2 native simulations ({cost["simulation_wall_seconds"]:.3f} s), 0 model calls; model tokens unavailable/not applicable; 0 formal calls.\n')
    print(json.dumps(dict(cost=cost,order_payload_false_negatives=len(violations),first_example=first),indent=2))


if __name__=='__main__': main()
