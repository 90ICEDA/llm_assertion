"""Native replay of frozen engineering FIFO candidates, not LLM generation."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from research_fifo_experiment import ROOT, DEFAULT_OUT, stimulus, testbench, oracle, parse_trace, write_json
from research_native_runner import run_native


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=DEFAULT_OUT/'native_engineering_controls')
    args=ap.parse_args()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    # Assertions are unchanged from the first engineering experiment. Only
    # native diagnostic action blocks are added, never assertion lowering.
    assertions='''
ap_valid_only: assert property (@(posedge clk) disable iff (rst) (svalid && sready) |=> mvalid)
  else $display("ASSERT_FAIL valid_only time=%0t", $time);
ap_stable: assert property (@(posedge clk) disable iff (rst) (mvalid && !mready) |=> (mvalid && $stable(mdata)))
  else $display("ASSERT_FAIL stable_under_backpressure time=%0t", $time);
always @(posedge clk) if (!rst) begin
  if (svalid && sready) $display("TRIGGER valid_only time=%0t", $time);
  if (mvalid && !mready) $display("TRIGGER stable_under_backpressure time=%0t", $time);
end
'''
    (out/'frozen_assertions.sva').write_text(assertions)
    write_json(out/'freeze.json',dict(timestamp=time.time(),sha256=hashlib.sha256(assertions.encode()).hexdigest(),
        origin='same frozen hand-written engineering properties, diagnostic action blocks added',
        no_llm=True, independent_seed=100129111,depth_requested=3,actual_ram_depth=4,pipeline=2,
        test_policy='fresh seed created only after candidate freeze; no subsequent assertion changes'))
    rows=stimulus(100129111)
    write_json(out/'intent_schedule.json',rows)
    results={}
    for mutation in ('correct','corrupt'):
        source=testbench(rows,3,2,mutation).replace('  task drive(',assertions+'\n  task drive(')
        source=source.replace('#1; $finish;', '#1; $display("NATIVE_RUN_COMPLETE"); $finish;')
        result=run_native(source,out/mutation,extra_sources=[ROOT/'external/verilog-axis/rtl/axis_fifo.v'])
        trace=parse_trace(out/mutation/'execute.log') if result['execution_status']=='completed' else []
        reference=oracle(trace) if trace else {'obligation_verdict':'unknown'}
        write_json(out/mutation/'trace.json',trace)
        write_json(out/mutation/'independent_oracle.json',reference)
        result['independent_oracle_verdict']=reference['obligation_verdict']
        result['by_assertion']={name:dict(triggers=sum(t['id']==name for t in result.get('triggers',[])),
            failures=sum(f['id']==name for f in result.get('failures',[])))
            for name in ('valid_only','stable_under_backpressure')}
        results[mutation]=result
    write_json(out/'results.json',results)
    print(json.dumps({k:dict(compile=v['compile_status'],native=v['property_status'],
        oracle=v['independent_oracle_verdict'],by_assertion=v['by_assertion']) for k,v in results.items()},indent=2))


if __name__=='__main__': main()
