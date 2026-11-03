#!/usr/bin/env python3
import difflib, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'rtl_cases_real_scale210_independent_next'
COMMIT='3d0ce04455d4568c3d140517555ad95db4fb04c8'

CASES=[]

clock_rtl='''`timescale 1ns/1ps
module prim_clock_timeout #(parameter integer TimeOutCnt=4, parameter integer CntWidth=3)(
 input logic clk_chk_i,rst_chk_ni,clk_i,rst_ni,en_i, output logic timeout_o);
 logic [CntWidth-1:0] cnt; logic ack,timeout; logic chk_seen;
 always_ff @(posedge clk_chk_i or negedge rst_chk_ni) begin
   if(!rst_chk_ni) chk_seen<=0; else chk_seen<=~chk_seen;
 end
 logic chk_q1,chk_q2;
 always_ff @(posedge clk_i or negedge rst_ni) begin
   if(!rst_ni) begin chk_q1<=0; chk_q2<=0; end else begin chk_q1<=chk_seen; chk_q2<=chk_q1; end
 end
 assign ack=chk_q1^chk_q2;
 assign timeout = int'(cnt) >= TimeOutCnt;
 always_ff @(posedge clk_i or negedge rst_ni) begin
   if(!rst_ni) cnt<='0;
   else if(ack || !en_i) cnt<='0;
   else if(timeout) cnt<='{default:'1};
   else if(en_i) cnt<=cnt+1'b1;
 end
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) timeout_o<=0; else timeout_o<=timeout;
endmodule
'''

count_rtl='''`timescale 1ns/1ps
module prim_count #(parameter integer Width=4)(input logic clk_i,rst_ni,clr_i,set_i,incr_en_i,decr_en_i,
 input logic [Width-1:0] set_cnt_i,step_i,input logic commit_i,
 output logic [Width-1:0] cnt_o,cnt_after_commit_o,output logic err_o);
 logic [Width-1:0] cnt_q,cnt_d,cnt_d_committed; logic [Width:0] ext_cnt; logic uflow,oflow,cnt_en;
 assign ext_cnt=decr_en_i?{1'b0,cnt_q}-{1'b0,step_i}:incr_en_i?{1'b0,cnt_q}+{1'b0,step_i}:{1'b0,cnt_q};
 assign oflow=incr_en_i&&ext_cnt[Width]; assign uflow=decr_en_i&&ext_cnt[Width];
 wire [Width-1:0] cnt_sat=uflow?'0:oflow?{Width{1'b1}}:ext_cnt[Width-1:0];
 assign cnt_en=(incr_en_i ^ decr_en_i)&&((incr_en_i&&!(&cnt_q))||(decr_en_i&&cnt_q!='0));
 assign cnt_d=clr_i?'0:set_i?set_cnt_i:cnt_en?cnt_sat:cnt_q;
 assign cnt_d_committed = commit_i ? cnt_d : cnt_q;
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) cnt_q<='0; else cnt_q<=cnt_d_committed;
 assign cnt_o=cnt_q; assign cnt_after_commit_o=cnt_d; assign err_o=0;
endmodule
'''

crc_rtl='''`timescale 1ns/1ps
module prim_crc32(input logic clk_i,rst_ni,set_crc_i,data_valid_i,input logic [31:0] data_i,crc_in_i,output logic [31:0] crc_out_o);
 function automatic [31:0] next_crc(input [31:0] c,input [31:0] d); integer i; reg [31:0] x; begin
   x=c; for(i=0;i<32;i=i+1) x=(x[0]^d[i])?((x>>1)^32'hEDB88320):(x>>1); next_crc=x;
 end endfunction
 logic [31:0] crc_d,crc_q; logic crc_en;
 assign crc_en = set_crc_i | data_valid_i;
 always_comb if(set_crc_i) crc_d=~crc_in_i; else crc_d=next_crc(crc_q,data_i);
 always_ff @(posedge clk_i or negedge rst_ni) if(!rst_ni) crc_q<=32'hFFFFFFFF; else if(crc_en) crc_q<=crc_d;
 assign crc_out_o=~crc_q;
endmodule
'''

def tb_clock(mode, clear_bug=False):
    # chk clock is enabled only during warm-up; mutation 2 uses isolated ack pulse via one chk edge.
    schedules={
      'primary':"repeat(2) @(posedge clk_i); run_chk=0; repeat(8) @(posedge clk_i);",
      'holdout':"repeat(3) @(posedge clk_i); run_chk=0; repeat(10) @(posedge clk_i);",
      'decoy':"repeat(1) @(posedge clk_i); run_chk=0; repeat(6) @(posedge clk_i); run_chk=1; repeat(2) @(posedge clk_chk_i); run_chk=0; repeat(6) @(posedge clk_i);"}
    if clear_bug:
      schedules={
       'primary':"run_chk=0; repeat(3) @(posedge clk_i); en_i=0; repeat(2) @(posedge clk_i); en_i=1; repeat(6) @(posedge clk_i);",
       'holdout':"run_chk=0; repeat(2) @(posedge clk_i); run_chk=1; @(posedge clk_chk_i); run_chk=0; repeat(7) @(posedge clk_i);",
       'decoy':"run_chk=0; repeat(3) @(posedge clk_i); en_i=0; @(posedge clk_i); en_i=1; repeat(2) @(posedge clk_i); run_chk=1; @(posedge clk_chk_i); run_chk=0; repeat(6) @(posedge clk_i);"}
    return f'''`timescale 1ns/1ps
module tb; logic clk_i=0,clk_chk_i=0,rst_ni=0,rst_chk_ni=0,en_i=1,run_chk=1; logic timeout_o;
 always #5 clk_i=~clk_i; always begin #3; if(run_chk) clk_chk_i=~clk_chk_i; end
 prim_clock_timeout #(.TimeOutCnt(4),.CntWidth(3)) dut(.*);
 initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);
 #2;rst_ni=1;rst_chk_ni=1; {schedules[mode]} $finish;end endmodule
'''

def tb_count(mode, dual=False):
 s={
 'primary':("set_i=1;set_cnt_i=4;@(posedge clk_i);#1;set_i=0;commit_i=0;incr_en_i=1;repeat(2)@(posedge clk_i);#1;commit_i=1;@(posedge clk_i);" if not dual else "set_i=1;set_cnt_i=7;@(posedge clk_i);#1;set_i=0;incr_en_i=1;decr_en_i=1;repeat(2)@(posedge clk_i);"),
 'holdout':("set_i=1;set_cnt_i=2;@(posedge clk_i);#1;set_i=0;commit_i=0;incr_en_i=1;step_i=2;repeat(3)@(posedge clk_i);#1;commit_i=1;@(posedge clk_i);" if not dual else "set_i=1;set_cnt_i=10;@(posedge clk_i);#1;set_i=0;incr_en_i=1;decr_en_i=1;step_i=2;repeat(2)@(posedge clk_i);"),
 'decoy':("set_i=1;set_cnt_i=1;@(posedge clk_i);#1;set_i=0;commit_i=0;decr_en_i=1;repeat(2)@(posedge clk_i);#1;commit_i=1;@(posedge clk_i);" if not dual else "set_i=1;set_cnt_i=5;@(posedge clk_i);#1;set_i=0;incr_en_i=1;decr_en_i=1;repeat(3)@(posedge clk_i);")}
 return f'''`timescale 1ns/1ps
module tb;logic clk_i=0,rst_ni=0,clr_i=0,set_i=0,incr_en_i=0,decr_en_i=0,commit_i=1;logic[3:0]set_cnt_i=0,step_i=1,cnt_o,cnt_after_commit_o;logic err_o;
 always #5 clk_i=~clk_i;prim_count dut(.*);initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);#2;rst_ni=1;{s[mode]}repeat(3)@(posedge clk_i);$finish;end endmodule
'''

def tb_crc(mode):
 s={'primary':"set_crc_i=1;crc_in_i=32'h12345678;@(posedge clk_i);#1;set_crc_i=0;repeat(2)@(posedge clk_i);",
 'holdout':"set_crc_i=1;crc_in_i=32'hA5A55A5A;@(posedge clk_i);#1;set_crc_i=0;data_valid_i=1;data_i=32'hDEADBEEF;@(posedge clk_i);#1;data_valid_i=0;",
 'decoy':"data_valid_i=1;data_i=32'hCAFEBABE;@(posedge clk_i);#1;data_valid_i=0;set_crc_i=1;crc_in_i=32'h0F0F0F0F;@(posedge clk_i);#1;set_crc_i=0;"}
 return f'''`timescale 1ns/1ps
module tb;logic clk_i=0,rst_ni=0,set_crc_i=0,data_valid_i=0;logic[31:0]data_i=0,crc_in_i=0,crc_out_o;always #5 clk_i=~clk_i;
 prim_crc32 dut(.*);initial begin string vcd;if(!$value$plusargs("VCD=%s",vcd))vcd="trace.vcd";$dumpfile(vcd);$dumpvars(0,tb);#2;rst_ni=1;{s[mode]}repeat(3)@(posedge clk_i);$finish;end endmodule
'''

CASES=[
('case451_prim_clock_timeout_threshold_off_by_one','prim_clock_timeout','prim_clock_timeout.sv',clock_rtl,"assign timeout = int'(cnt) >= TimeOutCnt;","assign timeout = int'(cnt) > TimeOutCnt;",'timeout_threshold_off_by_one','temporal_cross_cycle','counter threshold crossing','When enabled and no checked-clock acknowledgement arrives for TimeOutCnt reference cycles, timeout_o asserts after the output register latency.',lambda m:tb_clock(m),"en_i && !ack |-> ##5 timeout_o",['clk_i','clk_chk_i','rst_ni','rst_chk_ni','en_i','ack','cnt','timeout','timeout_o']),
('case452_prim_clock_timeout_clear_condition','prim_clock_timeout','prim_clock_timeout.sv',clock_rtl,"else if(ack || !en_i) cnt<='0;","else if(ack && !en_i) cnt<='0;",'timeout_clear_condition_conjunction','temporal_cross_cycle','conditional counter clear','Either an acknowledgement or disabling the monitor clears the timeout counter on the following reference edge.',lambda m:tb_clock(m,True),"(ack || !en_i) |=> cnt == 0",['clk_i','clk_chk_i','rst_ni','en_i','ack','cnt','timeout_o']),
('case453_prim_count_commit_inversion','prim_count','prim_count.sv',count_rtl,"assign cnt_d_committed = commit_i ? cnt_d : cnt_q;","assign cnt_d_committed = commit_i ? cnt_q : cnt_d;",'deferred_commit_polarity_inversion','temporal_cross_cycle','commit-gated state transition','The counter state changes to cnt_d only on an asserted commit; a deasserted commit retains cnt_o.',lambda m:tb_count(m),"commit_i && incr_en_i |=> cnt_o == $past(cnt_after_commit_o)",['clk_i','rst_ni','commit_i','incr_en_i','decr_en_i','cnt_o','cnt_after_commit_o']),
('case454_prim_count_simultaneous_command','prim_count','prim_count.sv',count_rtl,"assign cnt_en=(incr_en_i ^ decr_en_i)","assign cnt_en=(incr_en_i | decr_en_i)",'simultaneous_increment_decrement_not_suppressed','combination_protocol','mutually exclusive command arbitration','When increment and decrement are asserted together, the counter must retain its prior value.',lambda m:tb_count(m,True),"incr_en_i && decr_en_i |=> $stable(cnt_o)",['clk_i','rst_ni','incr_en_i','decr_en_i','cnt_en','cnt_o']),
('case455_prim_crc32_set_enable_coupling','prim_crc32','prim_crc32.sv',crc_rtl,"assign crc_en = set_crc_i | data_valid_i;","assign crc_en = set_crc_i & data_valid_i;",'crc_set_update_enable_coupled','temporal_cross_cycle','set-only state update','A set_crc_i pulse loads the complemented seed independently of data_valid_i, so crc_out_o equals the sampled crc_in_i on the next cycle.',lambda m:tb_crc(m),"set_crc_i && !data_valid_i |=> crc_out_o == $past(crc_in_i)",['clk_i','rst_ni','set_crc_i','data_valid_i','crc_in_i','crc_en','crc_out_o'])]

def weak(case,golden):
 observed=case[-1][-1]
 props=[('single_cycle_implication','rst_ni |-> !$isunknown('+observed+')','rst_ni'),('final_output_only','rst_ni |-> !$isunknown('+observed+')','rst_ni'),('delay_removed',golden.replace('|=>','|->').replace('##5',''),'rst_ni'),('antecedent_removed','!$isunknown('+observed+')',None),('simple_invariant','rst_ni |-> 1\'b1','rst_ni')]
 return {'schema_version':'weak-assertions-v1','case_id':case[0],'parent_bug_id':case[0],'source_project':'opentitan','admission_rule':'At least two non-vacuous weak assertions must miss the RTL bug.','overall_validation_status':'pending','assertions':[{'id':f'W{i}_{k}','weakness_class':k,'property':p,'antecedent':a,'antecedent_nonempty':a is not None,'expected_weakness':'Deliberately omits the exact trigger, delay, duration, or state relation of the golden property.','validation_status':'pending','catches_bug':None,'nonvacuity_verified':False} for i,(k,p,a) in enumerate(props,1)]}

for c in CASES:
 name,module,src,correct,old,new,family,bclass,ttype,spec,tbf,golden,signals=c
 d=OUT/name;d.mkdir(parents=True,exist_ok=True); buggy=correct.replace(old,new)
 if buggy==correct: raise RuntimeError((name,old))
 (d/'correct.v').write_text(correct);(d/'buggy.v').write_text(buggy)
 (d/'mutation.diff').write_text(''.join(difflib.unified_diff(correct.splitlines(True),buggy.splitlines(True),fromfile='correct.v',tofile='buggy.v')))
 (d/'spec.md').write_text('# Behavioral specification\n\n'+spec+'\n')
 (d/'golden.sva').write_text(f'// Pending semantic validation; not admitted.\nassert property (@(posedge clk_i) disable iff (!rst_ni) {golden});\n')
 w=weak(c,golden);(d/'weak_assertions.json').write_text(json.dumps(w,indent=2));(d/'weak_assertions.sva').write_text('\n'.join(f"// {x['id']}\nassert property (@(posedge clk_i) disable iff (!rst_ni) {x['property']});" for x in w['assertions'])+'\n')
 for mode,fn in [('primary','tb.v'),('holdout','tb_holdout.v'),('decoy','tb_decoy.v')]: (d/fn).write_text(tbf(mode))
 md={'name':name,'parent_bug_id':name,'source_project':'opentitan','source_url':'https://github.com/lowRISC/opentitan.git','source_commit':COMMIT,'source_module':module,'source_files':[f'external/opentitan/hw/ip/prim/rtl/{src}'],'top_file':f'external/opentitan/hw/ip/prim/rtl/{src}','bug_class':bclass,'bug_family':family,'bug_type':ttype,'spec':spec,'mutation_edits':[{'search':old,'replace':new}],'mutation_signal':signals[-2] if len(signals)>1 else signals[-1],'relevant_signals':signals,'temporal_type':ttype,'mutation_kind':'real_rtl_line_replacement','dataset_phase':'independent_next_hard_batch1','status':'pending_trace_and_hardness_validation','golden_sva':{'name':'Golden_A','clock':'@(posedge clk_i)','disable_iff':'!rst_ni','assertion':f'assert property (@(posedge clk_i) disable iff (!rst_ni) {golden});','temporal_type':ttype},'first_divergence':{'primary':None,'heldout':None,'decoy':None},'correct_sha256':hashlib.sha256(correct.encode()).hexdigest(),'buggy_sha256':hashlib.sha256(buggy.encode()).hexdigest()}
 (d/'case_metadata.json').write_text(json.dumps(md,indent=2))
print(f'materialized {len(CASES)} cases in {OUT}')
