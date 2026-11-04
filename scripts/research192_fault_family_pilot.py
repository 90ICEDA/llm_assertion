"""Optional obligation-driven mutant qualification, reusing native REGuard runner.

This is an artificial arbiter engineering pilot, NOT a historical repair result.
Only development instances are executed. Reserved locations/operators stay unused.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
import research_native_runner as native

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'external/verilog-axis/rtl/arbiter.v'
ENCODER=ROOT/'external/verilog-axis/rtl/priority_encoder.v'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def qualify(native_result, trace):
    if native_result['compile_status']!='passed' or native_result['execution_status']!='completed':
        return dict(status='unknown_execution',valid_fault=False,violations=[],reference='independent_max_request_bit')
    if len(trace)!=12 or any(any(v is None for v in row.values()) for row in trace):
        return dict(status='unknown_trace',valid_fault=False,violations=[],reference='independent_max_request_bit')
    violations=[]
    for previous,current in zip(trace,trace[1:]):
        expected=0 if previous['rst'] else (1 << (previous['request'].bit_length()-1) if previous['request'] else 0)
        expected_valid=int(bool(expected))
        expected_index=expected.bit_length()-1 if expected else 0
        if (current['grant'],current['valid'],current['encoded'])!=(expected,expected_valid,expected_index):
            violations.append(dict(transaction=previous['cycle'],request=previous['request'],sample_cycle=current['cycle'],
                expected=dict(grant=expected,valid=expected_valid,encoded=expected_index),actual=current,
                obligation='registered_priority_response'))
    return dict(status='confirmed_violation' if violations else 'legal_within_executed_scope',
        valid_fault=bool(violations),violations=violations,reference='independent_max_request_bit',
        independent_transaction_count=len({v['transaction'] for v in violations}))


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    source=RTL.read_text()
    # The split is declared before any simulator invocation, by location AND
    # operator. Reserved instances are not executed or feedback-visible.
    specs=[dict(id='dev_missing_grant',split='development',operator='suppress_state_update',site='grant_reg_update',
                search='    grant_reg <= grant_next;',replace='    grant_reg <= grant_reg;'),
           dict(id='dev_missing_valid',split='development',operator='suppress_state_update',site='grant_valid_reg_update',
                search='    grant_valid_reg <= grant_valid_next;',replace='    grant_valid_reg <= grant_valid_reg;'),
           dict(id='reserved_priority_reversal',split='reserved_test_not_executed',operator='priority_parameter_inversion',site='priority_encoder_parameter',
                search='.LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)',replace='.LSB_HIGH_PRIORITY(!ARB_LSB_HIGH_PRIORITY)'),
           dict(id='reserved_encoded_corruption',split='reserved_test_not_executed',operator='xor_response_index',site='grant_encoded_output',
                search='assign grant_encoded = grant_encoded_reg;',replace="assign grant_encoded = grant_encoded_reg ^ 1'b1;")]
    protocol=dict(scope='4-port nonblocking MSB-priority arbiter, initial reset, finite simulation',
        provenance='Vendored upstream implementation; artificial faults, not a confirmed historical Bug/fix pair',
        obligation='After a non-reset request sample, next sample grant, valid and index identify its highest set bit; empty request gives no grant.',
        source_sha256=sha(RTL),encoder_sha256=sha(ENCODER),faults=specs,
        frozen_sva='(|request) |=> (|grant)',frozen_sva_origin='handwritten deliberately partial baseline, not model-generated',
        reference='Python highest-bit oracle derived from requests and reset; never copies mutated next-state expressions',
        split='Development state-update sites; future test disjoint priority-parameter/output sites and different operators.',
        budget=dict(native_compiles=3,native_executes=3,model_calls=0,workers=2),
        claims='Qualification and partial-assertion coverage only; no randomized/repair-region comparison or generalization gain.')
    dump(out/'protocol.json',protocol)
    dump(out/'split_manifest.json',dict(development=[x for x in specs if x['split']=='development'],
        reserved=[x for x in specs if x['split']!='development'],development_test_location_overlap=[],
        development_test_operator_overlap=[],reserved_instances_executed=0))
    tb='''`timescale 1ns/1ps
module tb;
reg clk=0; always #5 clk=~clk;
reg rst=1; reg [3:0] request=0; wire[3:0] grant; wire valid; wire[1:0] encoded;
integer cycle=0;
arbiter #(.PORTS(4),.ARB_TYPE_ROUND_ROBIN(0),.ARB_BLOCK(0),.ARB_LSB_HIGH_PRIORITY(0)) dut
(.clk(clk),.rst(rst),.request(request),.acknowledge(4'b0),.grant(grant),.grant_valid(valid),.grant_encoded(encoded));
assert property (@(posedge clk) disable iff(rst) (|request) |=> (|grant))
 else $display("ASSERT_FAIL acquisition cycle=%0d",cycle);
always @(posedge clk) begin
 $display("TRACE cycle=%0d rst=%0d request=%0d grant=%0d valid=%0d encoded=%0d",cycle,rst,request,grant,valid,encoded);
 if(!rst && |request) $display("TRIGGER acquisition cycle=%0d",cycle);
end
initial begin
 $dumpfile("wave.vcd");$dumpvars(0,tb);
 for(cycle=0;cycle<12;cycle=cycle+1) begin
  @(negedge clk); rst=(cycle<2);
  case(cycle)
   2:request=1;3:request=3;4:request=10;5:request=4;6:request=15;7:request=0;
   8:request=2;9:request=9;10:request=0;default:request=0;
  endcase
  @(posedge clk);#1;
 end
 $display("NATIVE_RUN_COMPLETE");$finish;
end
endmodule
'''
    jobs=[dict(id='correct',search=None)]+[s for s in specs if s['split']=='development']
    for job in jobs:
        text=source
        if job['search']:
            assert source.count(job['search'])==1
            text=source.replace(job['search'],job['replace'])
        p=out/(job['id']+'.v');p.write_text(text)
        job['rtl']=p
    dump(out/'pre_execution_freeze.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    def execute(job):
        folder=out/job['id']
        result=native.run_native(tb,folder,extra_sources=[job['rtl'],ENCODER],timeout=180)
        rows=[]
        if (folder/'execute.log').exists():
            for line in (folder/'execute.log').read_text().splitlines():
                if line.startswith('TRACE '):
                    rows.append({k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',line)})
        # An initial posedge precedes the first driven schedule; retain only the
        # final occurrence for each cycle and require the full fixed schedule.
        rows=list({r['cycle']:r for r in rows}.values())
        q=qualify(result,rows)
        fail_cycles={int(re.search(r'cycle=(\d+)',f['detail'])[1]) for f in result.get('failures',[]) if re.search(r'cycle=(\d+)',f['detail'])}
        q.update(id=job['id'],native=result,trace=rows,
            sva_detected_transactions=sorted({v['transaction'] for v in q['violations'] if v['sample_cycle'] in fail_cycles}),
            sva_missed_transactions=sorted({v['transaction'] for v in q['violations'] if v['sample_cycle'] not in fail_cycles}))
        dump(folder/'qualification.json',q)
        return q
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(execute,jobs))
    correct=results[0]
    good_control=correct['status']=='legal_within_executed_scope' and not correct['native'].get('failures')
    for r in results[1:]:
        r['valid_fault']=bool(good_control and r['valid_fault'])
    summary=dict(status='qualified' if good_control and all(r['valid_fault'] for r in results[1:]) else 'unknown_or_failed',
        correct_control_legal=good_control,development_mutations_attempted=2,
        valid_development_mutations=sum(r['valid_fault'] for r in results[1:]),
        independent_parent_bugs=0,artificial_parent_designs=1,reserved_tests_executed=0,
        actual_compile_attempts=len(results),actual_simulation_attempts=sum(r['native']['native_simulation_calls'] for r in results),
        unique_unprotected_obligations=sorted({'registered_priority_response' for r in results[1:] if r['valid_fault'] and r['sva_missed_transactions']}),
        model_calls=0,new_generalization_claim=False,strategies_compared=False,
        results=[dict(id=r['id'],status=r['status'],valid_fault=r['valid_fault'],
            target_transactions=r.get('independent_transaction_count',0),detected=len(r['sva_detected_transactions']),
            missed=len(r['sva_missed_transactions'])) for r in results])
    dump(out/'summary.json',summary)
    dump(out/'source_bindings.json',{str(p.relative_to(ROOT)):sha(p) for p in (RTL,ENCODER,Path(__file__),Path(native.__file__))})
    dump(out/'seal.json',{str(p.relative_to(ROOT)):sha(p) for p in out.rglob('*') if p.is_file() and 'obj_dir' not in p.parts})
    print(json.dumps(summary))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True)
    args=p.parse_args();out=(ROOT/args.out).resolve()
    if not out.is_relative_to(ROOT/'deliverables'):raise ValueError('workspace deliverables only')
    run(out)
