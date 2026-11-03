from pathlib import Path
import json,difflib
R=Path(__file__).resolve().parents[1]/'rtl_cases_real_scale210_independent_next'

def emit(cid,module,c,b,spec,golden,weaks,tbs,bug_class,family,sigs):
 d=R/cid;d.mkdir(parents=True,exist_ok=True)
 assets={'correct.v':c,'buggy.v':b,'spec.md':spec+'\n','golden.sva':golden+'\n'}
 for n,v in assets.items():(d/n).write_text(v,encoding='utf8')
 (d/'mutation.diff').write_text(''.join(difflib.unified_diff(c.splitlines(True),b.splitlines(True),fromfile='correct.v',tofile='buggy.v')),encoding='utf8')
 aa=[]
 for i,(k,p,a,why) in enumerate(weaks,1):aa.append({'id':f'W{i}_{k}','weakness_class':k,'property':p,'antecedent':a,'antecedent_nonempty':a is not None,'expected_weakness':why,'validation_status':'pending','catches_bug':None,'nonvacuity_verified':False})
 (d/'weak_assertions.json').write_text(json.dumps({'schema_version':'weak-assertions-v1','case_id':cid,'parent_bug_id':cid,'source_project':'common_cells','admission_rule':'At least two non-vacuous weak assertions must miss the RTL bug.','overall_validation_status':'pending','assertions':aa},indent=2)+'\n',encoding='utf8')
 (d/'weak_assertions.sva').write_text('\n'.join(f'// {k}\nassert property (@(posedge clk_i) disable iff (!rst_ni) ({p}));' for k,p,a,w in weaks)+'\n',encoding='utf8')
 for n,v in zip(('tb.v','tb_holdout.v','tb_decoy.v'),tbs):(d/n).write_text(v,encoding='utf8')
 meta={'name':cid,'parent_bug_id':cid,'source_project':'common_cells','source_url':'https://github.com/pulp-platform/common_cells.git','source_commit':'local-vendored-snapshot','source_module':module,'source_files':[f'external/common_cells/src/{module}.sv'],'bug_class':bug_class,'bug_family':family,'mutation_kind':'actual_rtl_logic_change','relevant_signals':sigs,'temporal_type':'combinational protocol relation' if bug_class=='combination_protocol' else 'cross-cycle state transition','status':'candidate_pending_semantic_and_hardness_validation','golden_sva':{'assertion':golden},'trace_variants':['primary','heldout','decoy'],'first_divergence':{'primary':None,'heldout':None,'decoy':None}}
 (d/'case_metadata.json').write_text(json.dumps(meta,indent=2)+'\n',encoding='utf8')

def tb(decl,inst,mon,args,body):
 return f'''`timescale 1ns/1ps
module tb;
  reg clk_i = 0;
  reg rst_ni = 0;
  reg clr_i = 0;
  always #5 clk_i = ~clk_i;
  {decl}
  {inst}
  initial begin
    if ($test$plusargs("VCD")) begin
      $dumpfile("wave.vcd");
      $dumpvars(0,tb);
    end
    $monitor("T=%0t {mon}",$time,{args});
    #12 rst_ni = 1;
    {body}
    #40 $finish;
  end
endmodule
'''

addr='''module cc_addr_decode_overlap(input clk_i,input rst_ni,input clr_i,input [7:0] addr_i,input en_i,output [1:0] sel_o,output valid_o,output error_o);
  wire m0 = en_i && (addr_i >= 8'h20) && (addr_i < 8'h40);
  wire m1 = en_i && (addr_i >= 8'h30) && (addr_i < 8'h50);
  assign sel_o = {m1,m0};
  assign valid_o = m0 ^ m1;
  assign error_o = m0 && m1;
endmodule
'''
addrb=addr.replace('assign error_o = m0 && m1;','assign error_o = 1\'b0;\n  // MUTATION: overlapping rules are silently accepted as no-match.')
def atb(body):return tb('reg [7:0] addr_i=0; reg en_i=0; wire [1:0] sel_o; wire valid_o,error_o;','cc_addr_decode_overlap dut(.*);','addr=%h en=%b sel=%b valid=%b err=%b','addr_i,en_i,sel_o,valid_o,error_o',body)
wa=[('single_cycle_implication','en_i && addr_i<8\'h20 |-> !valid_o','en_i && addr_i<8\'h20','Checks only an unmapped region.'),('final_output_only','valid_o |-> $onehot(sel_o)','valid_o','Overlap suppresses valid in both designs.'),('delay_removed','en_i |-> !$isunknown(sel_o)','en_i','Knownness does not require overlap error.'),('antecedent_removed','!valid_o || $onehot(sel_o)',None,'Drops overlap antecedent.'),('simple_invariant','error_o |-> !valid_o','error_o','True only when error is already reported.')]
emit('case481_cc_addr_decode_overlap_error_suppressed','cc_addr_decode',addr,addrb,'When two address rules match simultaneously, error_o is asserted and valid_o is deasserted.','assert property (@(posedge clk_i) disable iff (!rst_ni) (en_i && addr_i>=8\'h30 && addr_i<8\'h40) |-> error_o);',wa,[atb('#13 en_i=1; addr_i=8\'h35; #20 en_i=0;'),atb('#13 en_i=1; addr_i=8\'h25; #10 addr_i=8\'h3f; #20 en_i=0;'),atb('#13 en_i=1; addr_i=8\'h4a; #10 addr_i=8\'h30; #20 en_i=0;')],'combination_protocol','overlap_error_suppression',['clk_i','rst_ni','addr_i','en_i','sel_o','valid_o','error_o'])

demux='''module cc_stream_demux #(parameter N=4,parameter W=8)(input clk_i,input rst_ni,input clr_i,input valid_i,output ready_o,input [W-1:0] data_i,input [1:0] sel_i,output [N-1:0] valid_o,input [N-1:0] ready_i,output [W-1:0] data_o);
  assign valid_o = valid_i ? (4'b0001 << sel_i) : 4'b0000;
  assign ready_o = ready_i[sel_i];
  assign data_o = data_i;
endmodule
'''
demuxb=demux.replace('assign ready_o = ready_i[sel_i];','assign ready_o = |ready_i;\n  // MUTATION: an unselected ready lane can consume the input.')
def dtb(body):return tb('reg valid_i=0; reg [7:0] data_i=0; reg [1:0] sel_i=0; reg [3:0] ready_i=0; wire ready_o; wire [3:0] valid_o; wire [7:0] data_o;','cc_stream_demux dut(.*);','vi=%b sel=%d ri=%b ro=%b vo=%b','valid_i,sel_i,ready_i,ready_o,valid_o',body)
wd=[('single_cycle_implication','valid_i |-> $onehot(valid_o)','valid_i','Valid routing remains one-hot.'),('final_output_only','data_o==data_i',"1'b1",'Payload path is unaffected.'),('delay_removed','ready_i[sel_i] |-> ready_o','ready_i[sel_i]','Only checks the sufficient direction.'),('antecedent_removed','!valid_i || $onehot(valid_o)',None,'No selected-ready equivalence.'),('simple_invariant','|valid_o |-> valid_i','|valid_o','Valid encoding survives mutation.')]
emit('case482_cc_stream_demux_unselected_ready_accept','cc_stream_demux',demux,demuxb,'Input ready equals the ready signal of the selected output; unselected ready lanes must not acknowledge input.','assert property (@(posedge clk_i) disable iff (!rst_ni) valid_i |-> (ready_o==ready_i[sel_i]));',wd,[dtb('#13 valid_i=1; data_i=8\'h51; sel_i=2; ready_i=4\'b0001; #20 valid_i=0;'),dtb('#13 valid_i=1; data_i=8\'h62; sel_i=3; ready_i=4\'b0010; #10 ready_i=4\'b1000; #20 valid_i=0;'),dtb('#13 valid_i=1; data_i=8\'h73; sel_i=1; ready_i=4\'b0101; #20 valid_i=0;')],'combination_protocol','unselected_lane_backpressure_leak',['clk_i','rst_ni','valid_i','ready_o','data_i','sel_i','valid_o','ready_i','data_o'])

filt='''module cc_stream_filter(input clk_i,input rst_ni,input clr_i,input valid_i,output ready_o,input drop_i,input ready_i,output valid_o);
  assign valid_o = drop_i ? 1'b0 : valid_i;
  assign ready_o = drop_i ? 1'b1 : ready_i;
endmodule
'''
filtb=filt.replace("assign ready_o = drop_i ? 1'b1 : ready_i;","assign ready_o = ready_i;\n  // MUTATION: dropped items incorrectly inherit downstream backpressure.")
def ftb(body):return tb('reg valid_i=0,drop_i=0,ready_i=0; wire ready_o,valid_o;','cc_stream_filter dut(.*);','vi=%b drop=%b ri=%b ro=%b vo=%b','valid_i,drop_i,ready_i,ready_o,valid_o',body)
wf=[('single_cycle_implication','!drop_i && valid_i |-> valid_o','!drop_i && valid_i','Pass path is unchanged.'),('final_output_only','drop_i |-> !valid_o','drop_i','Only checks suppression, not acceptance.'),('delay_removed','ready_i |-> ready_o','ready_i','Only sufficient ready condition.'),('antecedent_removed','!valid_o || valid_i',None,'No drop/backpressure relationship.'),('simple_invariant','valid_o |-> valid_i','valid_o','Validity implication survives mutation.')]
emit('case483_cc_stream_filter_drop_backpressured','cc_stream_filter',filt,filtb,'A dropped input is always accepted independently of downstream ready, and is never presented as valid downstream.','assert property (@(posedge clk_i) disable iff (!rst_ni) (valid_i && drop_i && !ready_i) |-> (ready_o && !valid_o));',wf,[ftb('#13 valid_i=1; drop_i=1; ready_i=0; #20 valid_i=0;'),ftb('#13 valid_i=1; drop_i=0; ready_i=0; #10 drop_i=1; #20 valid_i=0;'),ftb('#13 valid_i=1; drop_i=1; ready_i=1; #10 ready_i=0; #20 valid_i=0;')],'combination_protocol','drop_must_ignore_downstream_backpressure',['clk_i','rst_ni','valid_i','drop_i','ready_i','ready_o','valid_o'])

back='''module cc_exp_backoff(input clk_i,input rst_ni,input clr_i,input set_cnt_i,input clr_cnt_i,output is_zero_o,output [3:0] count_o);
  reg [3:0] count_q;
  reg [3:0] mask_q;
  assign count_o = count_q;
  assign is_zero_o = count_q==0;
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin count_q<=0; mask_q<=1; end
    else if (clr_i) begin count_q<=0; mask_q<=1; end
    else if (clr_cnt_i) begin count_q<=0; mask_q<=1; end
    else if (set_cnt_i) begin count_q<=mask_q; mask_q<={mask_q[2:0],1'b1}; end
    else if (count_q!=0) count_q<=count_q-1'b1;
  end
endmodule
'''
backb=back.replace('else if (clr_cnt_i) begin count_q<=0; mask_q<=1; end\n    else if (set_cnt_i)', 'else if (set_cnt_i) begin count_q<=mask_q; mask_q<={mask_q[2:0],1\'b1}; end\n    else if (clr_cnt_i) begin count_q<=0; mask_q<=1; end\n    else if (1\'b0)')
def btb(body):return tb('reg set_cnt_i=0,clr_cnt_i=0; wire is_zero_o; wire [3:0] count_o;','cc_exp_backoff dut(.*);','set=%b clear=%b zero=%b count=%d','set_cnt_i,clr_cnt_i,is_zero_o,count_o',body)
wb=[('single_cycle_implication','set_cnt_i && !clr_cnt_i |=> !is_zero_o','set_cnt_i && !clr_cnt_i','Nonconcurrent set still works.'),('final_output_only','is_zero_o == (count_o==0)',"1'b1",'Output consistency survives mutation.'),('delay_removed','clr_cnt_i |-> is_zero_o || !is_zero_o','clr_cnt_i','Removes next-cycle clear.'),('antecedent_removed','count_o<=15',None,'No priority trigger.'),('simple_invariant','!is_zero_o |-> count_o!=0','!is_zero_o','Local encoding invariant survives.')]
emit('case484_cc_exp_backoff_clear_set_priority','cc_exp_backoff',back,backb,'A successful-trial clear has priority over a simultaneous failed-trial set; the next state is zero with reset mask.','assert property (@(posedge clk_i) disable iff (!rst_ni) (clr_cnt_i && set_cnt_i) |=> (is_zero_o && count_o==0));',wb,[btb('#13 set_cnt_i=1; #10 set_cnt_i=0; #20 set_cnt_i=1; clr_cnt_i=1; #10 set_cnt_i=0; clr_cnt_i=0;'),btb('#13 set_cnt_i=1; #10 set_cnt_i=0; #10 set_cnt_i=1; #10 set_cnt_i=0; #10 set_cnt_i=1; clr_cnt_i=1; #10 set_cnt_i=0; clr_cnt_i=0;'),btb('#13 set_cnt_i=1; #10 set_cnt_i=0; #30 clr_cnt_i=1; set_cnt_i=1; #10 clr_cnt_i=0; set_cnt_i=0;')],'temporal_cross_cycle','simultaneous_clear_set_priority',['clk_i','rst_ni','clr_i','set_cnt_i','clr_cnt_i','is_zero_o','count_o'])

maxc='''module cc_max_counter #(parameter W=4)(input clk_i,input rst_ni,input clr_i,input clr_max_i,input en_i,input down_i,input [W-1:0] delta_i,output reg [W-1:0] q_o,output [W-1:0] max_o);
  reg [W-1:0] max_q;
  wire [W-1:0] q_next = down_i ? q_o-delta_i : q_o+delta_i;
  assign max_o = (en_i && !down_i && q_next>max_q) ? q_next : max_q;
  always @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin q_o<=0;max_q<=0;end
    else if(clr_i) begin q_o<=0;max_q<=0;end
    else begin
      if(clr_max_i) max_q<=0;
      else if(en_i && !down_i && q_next>max_q) max_q<=q_next;
      if(en_i) q_o<=q_next;
    end
  end
endmodule
'''
maxb=maxc.replace('else if(en_i && !down_i && q_next>max_q) max_q<=q_next;', 'else if(en_i && !down_i && q_o>max_q) max_q<=q_o;\n      // MUTATION: peak capture uses the previous count and is one cycle late.')
maxb=maxb.replace('assign max_o = (en_i && !down_i && q_next>max_q) ? q_next : max_q;', 'assign max_o = max_q;')
def mtb(body):return tb('reg clr_max_i=0,en_i=0,down_i=0; reg[3:0]delta_i=1; wire[3:0]q_o,max_o;','cc_max_counter dut(.*);','en=%b down=%b q=%d max=%d','en_i,down_i,q_o,max_o',body)
wm=[('single_cycle_implication','!en_i |-> max_o>=q_o','!en_i','Checks only idle cycles.'),('final_output_only','max_o>=q_o || en_i',"1'b1",'Allows mismatch exactly on update.'),('delay_removed','en_i |-> !$isunknown(max_o)','en_i','Knownness ignores capture time.'),('antecedent_removed','max_o<=15',None,'Range invariant only.'),('simple_invariant','clr_max_i |=> max_o==0','clr_max_i','Clear path is unchanged.')]
emit('case485_cc_max_counter_peak_capture_late','cc_max_counter',maxc,maxb,'An enabled upward count that creates a new peak updates max_o to the new counter value without an extra-cycle lag.','assert property (@(posedge clk_i) disable iff (!rst_ni) (en_i && !down_i && (q_o+delta_i)>dut.max_q) |=> max_o==$past(q_o+delta_i));',wm,[mtb('#13 en_i=1;delta_i=3;#10 en_i=0;down_i=1;#10 en_i=1;delta_i=1;#10 en_i=0;'),mtb('#13 en_i=1;delta_i=2;#30 down_i=1;delta_i=5;#10 en_i=0;'),mtb('#13 en_i=1;delta_i=4;#10 en_i=0;#20 en_i=1;delta_i=1;#10 en_i=0;')],'temporal_cross_cycle','new_peak_capture_delayed',['clk_i','rst_ni','clr_i','clr_max_i','en_i','down_i','delta_i','q_o','max_o','dut.max_q'])
