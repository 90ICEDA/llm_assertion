"""Independent obligations and deterministic legal input schedules for the audit.

All traces use pre-NBA rising-edge observations; inputs change at falling edges.
The oracle consumes port histories, never the candidate, golden SVA, or DUT internals.
"""
from pathlib import Path
import random

ROOT=Path(__file__).resolve().parents[1]
NAT=ROOT/'outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30'
IDS={
 'onehot':'case101_prim_onehot_multihot_suppressed',
 'filter':'case122_prim_filter_ctr_streak_reset_ignored',
 'fifo':'case438_cc_fifo_protocol_suppress_2',
 'spill':'case510_cc_spill_register_flush_push_priority',
 'stat':'case505_axis_stat_counter_frame_pulse_early',
 'intr':'case135_prim_intr_enable_mask_ignored',
}

def definition(k):
 d={'key':k,'parent_bug_id':IDS[k],'provenance':'artificial_mutation_of_repository_RTL','history_fix_commit':None}
 if k=='onehot':
  d.update(case='rtl_cases_real_scale120/case208_onehot_multihot_v8_from_case101_prim_onehot_multihot_suppressed',module='dut_case101_prim_onehot_multihot_suppressed',clk='clk',rst='rst_n',inputs={'oh_i':4,'addr_i':2,'en_i':1},outputs={'err_o':1},obligation='At every active sample with popcount(oh_i)>1, err_o must be 1 in that sample. All bit patterns are legal stimuli for an error detector. With zero/one-hot inputs, additional address/enable checks may legally assert err_o; do not prohibit those errors.',observation_base=['oh_i','addr_i','en_i','err_o'])
 elif k=='filter':
  d.update(case='rtl_cases_real_scale120/'+IDS[k],module='dut_'+IDS[k],clk='clk',rst='rst_n',inputs={'enable_i':1,'filter_i':1,'thresh_i':2},outputs={'filter_o':1,'second_new_sample_dbg':1},obligation='At threshold two, after candidate input polarity changes and opposes the stored output, the first and second new samples must not prematurely change the stored output. A change restarts progress even if the previous polarity accumulated progress. For this RTL threshold counts equal-polarity intervals, so acceptance occurs after threshold+1 samples. Disabled output bypasses input; internal qualification continues while disabled. Reset stored value=0. Threshold is held constant within a qualification episode.',observation_base=['enable_i','filter_i','thresh_i','filter_o'])
 elif k=='fifo':
  d.update(case=None,module='cc_fifo',clk='clk_i',rst='rst_ni',inputs={'clr_i':1,'flush_i':1,'push_i':1,'pop_i':1,'data_i':8},outputs={'full_o':1,'empty_o':1,'usage_o':1,'data_o':8},obligation='Depth=0: empty_o == !push_i in the same cycle, including idle push_i=0. Data is combinational passthrough and full_o == !pop_i. The target obligation is both polarities of empty. Hold presented data while push=1 and pop=0. DataWidth may change; the compatibility adapter is ONLY valid for Depth=0.',observation_base=['push_i','pop_i','data_i','full_o','empty_o','usage_o','data_o','clr_i','flush_i'])
 elif k=='spill':
  d.update(case='rtl_cases_real_scale210_independent_next/'+IDS[k],module='cc_spill_register_flushable',clk='clk_i',rst='rst_ni',inputs={'flush_i':1,'push_i':1,'data_i':8},outputs={'valid_o':1,'data_o':8},obligation='Flush has priority over simultaneous push. At next pre-edge sample after flush && push: valid_o=0, and the pushed payload must not be exposed as a valid item. data_o when valid_o=0 is architecturally unobservable; zeroing that invalid bus is implementation detail, not an obligation. Push-only stores data; flush alone empties.',observation_base=['flush_i','push_i','data_i','valid_o','data_o'])
 elif k=='stat':
  d.update(case='rtl_cases_real_scale210_independent_next/'+IDS[k],module='axis_stat_counter',clk='clk_i',rst='rst_ni',inputs={'frame_done_i':1,'frame_len_i':8},outputs={'stat_valid_o':1,'stat_len_o':8},obligation='A sampled frame_done event yields no attributable valid pulse one cycle later and a valid pulse two samples later with that event length. Consecutive events are legal (no ready port or spacing restriction exists). Pipeline pulses must equal frame_done two samples earlier; pulse data must be length captured two samples earlier. Reset cancels pending events.',observation_base=['frame_done_i','frame_len_i','stat_valid_o','stat_len_o'])
 elif k=='intr':
  d.update(case='rtl_cases_real_scale120/'+IDS[k],module='dut_'+IDS[k],clk='clk',rst='rst_n',inputs={'event_intr_i':1,'reg2hw_intr_enable_q_i':1,'reg2hw_intr_test_q_i':1,'reg2hw_intr_test_qe_i':1,'sw_clear':1},outputs={'reg2hw_intr_state_q_i':1,'hw2reg_intr_state_de_o':1,'hw2reg_intr_state_d_o':1,'intr_o':1},obligation='With FlopOutput=1 the interrupt output at sample t equals previous sampled state AND previous enable; masking is effective after the sampling edge (not before it). Event state is sticky until software clear/reset. Target: if enable at t-1 is 0, intr_o at t must be 0. Existing one-line case spec says same sampled cycle and conflicts with registered implementation; use documented FlopOutput=1 timing explicitly.',observation_base=['event_intr_i','reg2hw_intr_enable_q_i','reg2hw_intr_test_q_i','reg2hw_intr_test_qe_i','reg2hw_intr_state_q_i','intr_o','sw_clear','hw2reg_intr_state_de_o','hw2reg_intr_state_d_o'])
 return d

def sources(d):
 if d['key']=='fifo':
  p=NAT/d['parent_bug_id']/'slot_01/attempt_01'
  return p/'compat_correct.v',p/'compat_buggy.v'
 p=ROOT/d['case'];return p/'correct.v',p/'buggy.v'

def schedule(d,kind='train',h=24,seed=20261009):
 k=d['key']; rng=random.Random(seed); rows=[]; base={n:0 for n in d['inputs']};base[d['rst']]=0
 if k=='filter':base['thresh_i']=2;base['enable_i']=1
 def add(n=1,**kw):
  base.update(kw)
  for _ in range(n): rows.append(dict(base))
 add(2);base[d['rst']]=1
 if kind in ('train','hold','more'):
  if k=='onehot':
   add(oh_i=1,en_i=1,addr_i=0);add(oh_i=3);add(oh_i=0,en_i=0)
  elif k=='filter':
   add(2,filter_i=1);add(filter_i=0);add(2,filter_i=1);add(4,filter_i=0)
  elif k=='fifo':
   add(push_i=1,pop_i=1,data_i=53);add(push_i=0,pop_i=0)
  elif k=='spill':
   add(flush_i=1,push_i=1,data_i=85);add(flush_i=0,push_i=0)
  elif k=='stat':
   add(frame_done_i=1,frame_len_i=29);add(3,frame_done_i=0)
  elif k=='intr':
   add(event_intr_i=1,reg2hw_intr_enable_q_i=1);add(2,event_intr_i=0);add(reg2hw_intr_enable_q_i=0)
  if kind=='more':
   while len(rows)<h:
    if k=='onehot':add(oh_i=3,en_i=1);add(oh_i=1)
    elif k=='fifo':add(push_i=1,pop_i=1,data_i=rng.randrange(256));add(push_i=0)
    elif k=='spill':add(flush_i=1,push_i=1,data_i=rng.randrange(1,256));add(flush_i=0,push_i=0)
    elif k=='stat':add(frame_done_i=1,frame_len_i=rng.randrange(256));add(2,frame_done_i=0)
    elif k=='filter':add(2,filter_i=1);add(filter_i=0)
    else:add(event_intr_i=1,reg2hw_intr_enable_q_i=0);add(event_intr_i=0,sw_clear=1);add(sw_clear=0)
  else:add(max(0,h-len(rows)))
 elif kind=='held':
  if k=='spill':add(6,flush_i=1,push_i=1,data_i=85);add(4,flush_i=0,push_i=0)
  elif k=='onehot':add(6,oh_i=1,en_i=1,addr_i=0);add(4,oh_i=3)
  elif k=='fifo':add(4,push_i=0,pop_i=0);add(6,push_i=1,pop_i=0,data_i=17);add(2,pop_i=1)
  elif k=='filter':add(2,filter_i=1);add(2,filter_i=0);add(5,filter_i=1)
  elif k=='stat':add(3,frame_done_i=1,frame_len_i=7);add(4,frame_done_i=0)
  else:add(2,event_intr_i=1);add(4,event_intr_i=0);add(3,reg2hw_intr_enable_q_i=1)
 else:
  # New schedules sealed before any model call, only loaded after method freeze.
  for i in range(32):
   if kind=='reset' and i in (7,8,22):add(**{d['rst']:0});continue
   base[d['rst']]=1
   if k=='onehot':add(oh_i=rng.randrange(16),addr_i=rng.randrange(4),en_i=rng.randrange(2))
   elif k=='filter':add(enable_i=0 if i in (9,10,20) else 1,filter_i=(i//(1+i//8))%2)
   elif k=='fifo':
    stalled=base['push_i'] and not base['pop_i']
    add(push_i=1 if stalled else rng.randrange(2),pop_i=rng.randrange(2),data_i=base['data_i'] if stalled else rng.randrange(256))
   elif k=='spill':add(push_i=int(i%3!=0),flush_i=int(i%5<2),data_i=[0,255,1,rng.randrange(256)][i%4])
   elif k=='stat':add(frame_done_i=int(i%4<2),frame_len_i=[0,255,1,rng.randrange(256)][i%4])
   else:add(event_intr_i=int(i%6==0),reg2hw_intr_enable_q_i=int(i%5<2),sw_clear=int(i%7==0),reg2hw_intr_test_q_i=int(i%9==0),reg2hw_intr_test_qe_i=int(i%9==0))
  add(4,**{n:0 for n in d['inputs'] if n not in ('thresh_i','enable_i')})
 for i,r in enumerate(rows):r['cycle']=i;r['stimulus_id']=f'{kind}:{i}'
 return rows

def oracle(d,trace):
 """Return cycle obligations; unknown values do not become successful checks."""
 k=d['key'];out=[];stored=0;last=0;run=0;prev=None;prev2=None
 for i,t in enumerate(trace):
  checks={};trigger=False
  if not t[d['rst']]:stored=0;last=0;run=0;prev=prev2=None;out.append({'cycle':i,'checks':{},'violations':[],'trigger':False});continue
  if k=='onehot':
   trigger=t['oh_i'].bit_count()>1
   if trigger:checks['multihot_detect']=t['err_o']==1
  elif k=='fifo':trigger=True;checks['empty_relation']=t['empty_o']==int(not t['push_i'])
  elif k=='spill' and prev:
   trigger=bool(prev['flush_i'] and prev['push_i'])
   if trigger:checks['collision_empty']=t['valid_o']==0;checks['payload_not_valid']=not(t['valid_o'] and t['data_o']==prev['data_i'])
  elif k=='stat':
   trigger=bool(prev2 and prev2['frame_done_i'])
   checks['valid_latency']=t['stat_valid_o']==int(trigger)
   if trigger:checks['captured_length']=t['stat_len_o']==prev2['frame_len_i']
  elif k=='intr' and prev:
   trigger=not prev['reg2hw_intr_enable_q_i']
   if trigger:checks['registered_mask']=t['intr_o']==0
  elif k=='filter':
   trigger=bool(t['enable_i'] and t['filter_i']!=stored and run<t['thresh_i'])
   checks['qualified_value']=t['filter_o']==(stored if t['enable_i'] else t['filter_i'])
   # Count equal-input intervals. Restart on any flip; compare independently of output.
   run=0 if t['filter_i']!=last else min(run+1,t['thresh_i'])
   if run==t['thresh_i']:stored=t['filter_i']
   last=t['filter_i']
  out.append({'cycle':i,'checks':checks,'violations':[n for n,v in checks.items() if not v],'trigger':trigger})
  prev2,prev=prev,t
 return out

def controlled_candidate(k):
 # Explicit engineering controls for harness QA; NEVER entered in natural pools.
 x={
 'onehot':('((oh_i & (oh_i - 1)) != 0)','err_o',0),
 'fifo':('1', '(empty_o == !push_i)',0),
 'filter':('(enable_i && thresh_i == 2 && filter_i != p1_filter_i && filter_i != filter_o)','(filter_o == p1_filter_o)',1),
 'spill':('(flush_i && push_i)','!valid_o',1),
 'stat':('p2_frame_done_i','(stat_valid_o && stat_len_o == p2_frame_len_i)',0),
 'intr':('!reg2hw_intr_enable_q_i','!intr_o',1)}[k]
 return {'id':'engineering_control','antecedent':x[0],'consequent':x[1],'delay':x[2],'provenance':'controlled_not_natural'}
