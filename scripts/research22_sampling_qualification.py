"""Hand-authored next-cycle/reset tool and adapter qualification, never repair."""
import argparse
import hashlib
from pathlib import Path
import re

import research15_native_interface as native
from research15_evidence import paired_ledger, epoch_map, marker_map
from research17_fifo_feedback import feedback

# reset, antecedent, faulty consequent; all values driven on falling edge.
SCHEDULE = [(1,0,0),(0,0,0),(0,1,0),(0,0,0),(0,1,0),(1,0,0),
            (1,1,0),(0,0,0),(0,1,0),(0,1,1),(0,0,0),(0,0,0)]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve();assert native.ROOT in out.parents
    out.mkdir(parents=True,exist_ok=False)
    candidate=native.normalize_candidate({'assertions':[{'property':'svalid |=> mvalid','obligations':['order_payload']}]})
    expected=dict(triggers=[2,4,8,9],fixed_failures=[],mutant_failures=[3,10],
        cancelled_attempt=dict(trigger_cycle=4,reset_cycle=5),
        disabled_antecedent=dict(reset_cycle=6,release_cycle=7))
    native.dump(out/'expectations_before_execution.json',dict(expected=expected,schedule=SCHEDULE,
        scope='Manually authored tool qualification. svalid/mvalid are abstract Boolean operands here, not FIFO transactions. No generated candidate or repair success.'))
    native.dump(out/'candidate.json',candidate)
    drives=[]
    for c,(rst,a,b) in enumerate(SCHEDULE):
        # Correct next-sample response is independently set from the explicit
        # previous sampled antecedent; no candidate expression is evaluated.
        good=SCHEDULE[c-1][1] if c and not SCHEDULE[c-1][0] and not rst else 0
        drives.append(f'@(negedge clk);native_cycle={c};rst={rst};svalid={a};mvalid=fault_mode?{b}:{good};')
    source='''module tb;
bit clk=0;always #5 clk=~clk;
bit rst=1,svalid=0,mvalid=0;
integer native_cycle=-1,fault_mode=0;
PROPERTIES
always @(posedge clk) if ($sampled(native_cycle)>=0)
  $display("SAMPLE %0d %0d %0d %0d",$sampled(native_cycle),$sampled(rst),$sampled(svalid),$sampled(mvalid));
initial begin
  if ($value$plusargs("fault=%d",fault_mode)) begin end
  $dumpfile("wave.vcd");$dumpvars(0,tb);
  DRIVES
  @(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;
end
endmodule
'''.replace('PROPERTIES',native.candidate_sva(candidate)).replace('DRIVES','\n'.join(drives))
    fixed=native.run_native(source,out/'native',timeout=180)
    mutant=native.replay_native(out/'native',out/'mutant',['+fault=1'])
    checks=[]
    def check(name,value,detail=None):checks.append(dict(name=name,passed=bool(value),detail=detail))
    def record(result,path,mode):
        rows=[]
        for c,r,a,b in re.findall(r'^SAMPLE (\d+) (\d+) (\d+) (\d+)$',(path/'execute.log').read_text(),re.M):
            rows.append(dict(cycle=int(c),rst=int(r),svalid=int(a),sready=1,sdata=0,mready=1,mvalid=int(b),mdata=0,ref_count=0,ref_expected=0,drain_due=0))
        check(mode+':samples_match_driven_schedule',len(rows)==len(SCHEDULE) and all(
            [row['rst'],row['svalid']]==list(SCHEDULE[row['cycle']][:2]) for row in rows))
        return dict(native=result,trace=rows,reference_trace=rows,candidate=candidate,mode=mode,directory=str(path),
            oracle=dict(legality='legal',unknown=[],violations=[] if mode=='correct' else [
                dict(cycle=c,obligation='order_payload',passed=False) for c in expected['mutant_failures']],transactions=[]),
            sampling_qualification=dict(status='passed',scope='Explicit Boolean tool stimulus; not FIFO queue qualification'))
    a=record(fixed,out/'native','correct');b=record(mutant,out/'mutant','mutant')
    for name,result in [('fixed',fixed),('mutant',mutant)]:
        check(name+':healthy',result['compile_status']=='passed' and result['execution_status']=='completed')
        check(name+':exact_cover_cycles',sorted(marker_map(result,'triggers')['a0'])==expected['triggers'])
        check(name+':exact_failure_cycles',sorted(marker_map(result,'failures')['a0'])==expected[name+'_failures'])
    epochs=epoch_map(b['trace'])
    check('reset_samples_not_in_epoch_map',5 not in epochs and 6 not in epochs)
    check('reset_changes_epoch',epochs[4]!=epochs[7])
    group=paired_ledger(a,b,'tool_qualification:next_cycle_reset')
    diagnostics=feedback(a,b,group)
    native.dump(out/'adapter_fixture_ledger.json',group)
    native.dump(out/'adapter_fixture_feedback.json',diagnostics)
    targets=diagnostics['target_evidence']
    check('adapter_target_cycles_are_actual_next_cycle_failures',[t['cycle'] for t in targets]==[3,10])
    check('adapter_uses_previous_cycle_trigger',all(t['gap_observation']=='detected' and
        t['assertions']==[dict(id='a0',trigger=True,failed=True,causal_detection=True)] for t in targets))
    check('cancelled_attempt_does_not_become_false_failure',5 not in marker_map(mutant,'failures')['a0'] and 7 not in marker_map(mutant,'failures')['a0'])
    check('pre_reset_cover_not_attributed_to_post_reset_sample',all(
        not r['native']['assertions'][0]['trigger'] for r in group['ledger'] if
        r['variant']=='mutant' and r['cycle']==7 and r['obligation']=='order_payload'))
    report=dict(passed=all(c['passed'] for c in checks),checks=checks,expected=expected,
        compile_calls=1,native_execution_calls=2,model_calls=0,formal_calls=0,
        prior_qualifications=['deliverables/research15_native_20261015_r01/cover_qualification/qualification.json',
                              'deliverables/research19_native_qualification_20261016_r01/qualification.json'],
        findings=['|=> delay=1 aligns failure at cycle c to native cover at c-1 in the same reset epoch.',
                  'disable iff(rst) cancels a pending attempt when reset is high at its next clock sample.',
                  'An antecedent while reset is high does not create an attempt at the subsequent release sample.',
                  'The harness reset changes at negedge and spans posedges; asynchronous disable iff is compatible with the synchronous RTL reset for this restricted stimulus timing.'],
        limitations=['No arbitrary inter-edge reset-pulse or same-posedge reset-race qualification; disable iff itself is asynchronous, not a general synchronous reset operator.',
                     'The adapter oracle fixture is the independently predeclared Boolean stimulus expectation, not a FIFO oracle or newly found RTL bug.',
                     'No model candidate, independent research test, or repair result was inspected or generated.'],
        source_hashes={str(p.relative_to(native.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),
            native.ROOT/'scripts/research15_native_interface.py',native.ROOT/'scripts/research15_evidence.py',native.ROOT/'scripts/research17_fifo_feedback.py']})
    native.dump(out/'qualification.json',report)
    print(dict(passed=report['passed'],checks=len(checks)))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
