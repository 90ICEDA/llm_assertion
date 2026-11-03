"""Version two: independent contract views and deterministic unseen scenarios."""
import copy, random
from repair_contract_cases import definition as old_definition, oracle as old_oracle, IDS, sources, ROOT

SEED=20261009
HIDDEN_SEED=2026101901

def definition(k):
    d=old_definition(k)
    if k=='spill':
        d['obligation']='Flush has priority over simultaneous push: at the next pre-edge sample valid_o must be zero. The independent text also says not expose the pushed payload. Two unresolved interpretations are retained: payload is observable only with valid_o=1, or raw data_o must differ from the pushed payload (including zero). Do not assume either interpretation is settled. Reset cancels outstanding pushes.'
    if k=='intr':
        d['obligation']='Interrupt masking has unresolved sampling interpretations. The case text requires intr_o=0 in a sample with enable=0 even if state is set; the configured FlopOutput=1 primitive registers the masked output, implying enable(t-1)=0 requires intr_o(t)=0. Both are independently evaluated; neither is declared the uniquely resolved specification. Reset clears state and cancels pending output; software clear updates the external sticky state at the edge.'
    return d

def contract(k):
    d=definition(k)
    src={
      'onehot':['rtl_cases_real_scale120/case101_prim_onehot_multihot_suppressed/STIMULUS_NOTES.md','external/opentitan/hw/ip/prim/rtl/prim_onehot_check.sv'],
      'filter':['rtl_cases_real_scale120/case122_prim_filter_ctr_streak_reset_ignored/STIMULUS_NOTES.md','external/opentitan/hw/ip/prim/rtl/prim_filter_ctr.sv'],
      'fifo':['rtl_cases_real_scale210_independent/case438_cc_fifo_protocol_suppress_2/spec.md','rtl_cases_real_scale210_independent/case438_cc_fifo_protocol_suppress_2/correct.v'],
      'spill':['rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/spec.txt'],
      'stat':['rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early/spec.txt'],
      'intr':['rtl_cases_real_scale120/case135_prim_intr_enable_mask_ignored/STIMULUS_NOTES.md','external/opentitan/hw/ip/prim/rtl/prim_intr_hw.sv']
    }[k]
    # Resolve the extension without substituting assertion/candidate evidence.
    resolved=[]
    for name in src:
        p=ROOT/name
        if not p.exists():
            matches=list(p.parent.glob('spec*')) if p.name.startswith('spec') else []
            if len(matches)==1:p=matches[0]
        resolved.append(str(p.relative_to(ROOT)))
    return {'parent_bug_id':IDS[k],'case':k,'sources':resolved,'text':d['obligation'],
       'status':'spec_unresolved' if k in ('spill','intr') else 'scoped_contract',
       'interpretations':views(k),'initialization':'two sampled active-low reset cycles; inputs change on falling edges; monitor samples before rising-edge NBA',
       'reset_cancellation':'asynchronous active-low reset cancels all pending temporal obligations and observer history; no inherited obligations across effective reset',
       'legal_inputs': 'all width-correct sampled values; no X/Z; filter threshold changes only during reset; FIFO holds push/data while stalled until acceptance or reset; reset may cancel any transaction',
       'environment':'FIFO Depth=0 case-specific passthrough interface, not general Depth>0 FIFO assertions; interrupt sticky-state harness gives software clear priority over event updates',
       'parameters':{'onehot':'4-bit oh_i; StrictCheck=1 and documented 0 variant','filter':'AsyncOn=0; CntWidth=2 or 3; thresholds held within episodes','fifo':'Depth=0 only; DataWidth=8 or 4','spill':'8-bit payload, no ready port','stat':'8-bit length, two-sample pipeline, consecutive events allowed','intr':'Width=1, IntrT=Event, FlopOutput=1'}[k],
       'required_branches':branches(k),'required_assertion_trigger_branches':trigger_branches(k),'target_components':components(k),
       'target_scope':'repair target obligations, not all module functionality',
       'independence_limit': 'independent case prose plus original upstream parameter/reset documentation; no candidate or candidate score used; ambiguity is retained',
       'historical_repair_commit':None,'origin':'existing_artificial_mutation'}

def views(k):
    return ['validity_gated','raw_payload'] if k=='spill' else ['registered_mask','same_sample_mask'] if k=='intr' else ['primary']

def components(k):
    return {'onehot':['multihot_detect'],'filter':['qualified_value'],
            'fifo':['empty_when_idle','nonempty_when_present'],
            'spill':['collision_empty','payload_not_exposed'],
            'stat':['valid_latency','captured_length'],
            'intr':['masked_output']}[k]

def branches(k):
    return {'onehot':['multihot','zero_or_onehot'],
      'filter':['restart_0_to_1','restart_1_to_0','first_new_sample','second_new_sample','disabled_bypass','stable_acceptance'],
      'fifo':['idle','present_accepted','present_stalled'],
      'spill':['collision_zero','collision_nonzero','flush_only','push_only','reset_cancellation'],
      'stat':['isolated_event','consecutive_event','zero_length','max_length','reset_cancellation'],
      'intr':['masked_state_set','mask_falling','event','software_clear','test_interrupt','reset_cancellation']}[k]

def trigger_branches(k):
    # Negative/legal controls and cancellation must be exercised, but a target
    # antecedent is NOT required to fire when its necessary condition is false.
    return {'onehot':['multihot'],
      'filter':['restart_0_to_1','restart_1_to_0','first_new_sample','second_new_sample'],
      'fifo':['idle','present_accepted','present_stalled'],
      'spill':['collision_zero','collision_nonzero'],
      'stat':['isolated_event','consecutive_event','zero_length','max_length'],
      'intr':['masked_state_set','mask_falling']}[k]

def adjudicate(d,trace,view=None):
    k=d['key'];view=view or views(k)[0];old=old_oracle(d,trace);out=[];past=[];last_filter=0;streak=0
    for i,t in enumerate(trace):
        if not t[d['rst']]:
            past=[];last_filter=0;streak=0
            out.append({'cycle':i,'active':False,'checks':{},'violations':[],'branches':[], 'pending':[], 'cancelled_by_reset':True});continue
        prev=past[-1] if past else None;prev2=past[-2] if len(past)>1 else None
        checks=dict(old[i]['checks']);bs=[];pending=[]
        if k=='onehot':bs=['multihot' if t['oh_i'].bit_count()>1 else 'zero_or_onehot']
        elif k=='fifo':
            checks={('nonempty_when_present' if t['push_i'] else 'empty_when_idle'):t['empty_o']==int(not t['push_i'])}
            bs=['present_accepted' if t['push_i'] and t['pop_i'] else 'present_stalled' if t['push_i'] else 'idle']
        elif k=='filter':
            changed=t['filter_i']!=last_filter
            streak=1 if changed else streak+1
            if changed:bs.append('restart_0_to_1' if t['filter_i'] else 'restart_1_to_0')
            if streak==1:bs.append('first_new_sample')
            if streak==2:bs.append('second_new_sample')
            if streak>=t['thresh_i']+2:bs.append('stable_acceptance')
            if not t['enable_i']:bs.append('disabled_bypass')
            last_filter=t['filter_i']
        elif k=='spill':
            checks={}
            if prev and prev['flush_i'] and prev['push_i']:
                checks['collision_empty']=t['valid_o']==0
                checks['payload_not_exposed']=(not(t['valid_o'] and t['data_o']==prev['data_i'])) if view=='validity_gated' else t['data_o']!=prev['data_i']
                bs.append('collision_zero' if prev['data_i']==0 else 'collision_nonzero')
            if t['flush_i'] and not t['push_i']:bs.append('flush_only')
            if t['push_i'] and not t['flush_i']:bs.append('push_only')
            if t['flush_i'] and t['push_i']:pending=[{'trigger_cycle':i,'due_cycle':i+1,'components':components(k)}]
        elif k=='stat':
            if t['frame_done_i']:
                bs.append('consecutive_event' if prev and prev['frame_done_i'] else 'isolated_event')
                if t['frame_len_i']==0:bs.append('zero_length')
                if t['frame_len_i']==255:bs.append('max_length')
                pending.append({'trigger_cycle':i,'due_cycle':i+2,'components':components(k)})
            if prev and prev['frame_done_i']:pending.append({'trigger_cycle':i-1,'due_cycle':i+1,'components':components(k)})
        elif k=='intr':
            checks={};sample=prev if view=='registered_mask' else t
            if sample and not sample['reg2hw_intr_enable_q_i']:checks['masked_output']=t['intr_o']==0
            if sample and sample['reg2hw_intr_state_q_i'] and not sample['reg2hw_intr_enable_q_i']:bs.append('masked_state_set')
            if prev and prev['reg2hw_intr_enable_q_i'] and not t['reg2hw_intr_enable_q_i']:bs.append('mask_falling')
            if t['event_intr_i']:bs.append('event')
            if t['sw_clear']:bs.append('software_clear')
            if t['reg2hw_intr_test_q_i'] and t['reg2hw_intr_test_qe_i']:bs.append('test_interrupt')
            if view=='registered_mask' and not t['reg2hw_intr_enable_q_i']:pending=[{'trigger_cycle':i,'due_cycle':i+1,'components':components(k)}]
        if i+1<len(trace) and not trace[i+1][d['rst']] and (pending or (k=='intr' and t['event_intr_i'])):bs.append('reset_cancellation')
        out.append({'cycle':i,'active':True,'checks':checks,'violations':[n for n,v in checks.items() if not v], 'branches':bs,'pending':pending,'cancelled_by_reset':False})
        past.append(t)
    return out

def legality(d,rows):
    bad=[];prev=None
    for i,r in enumerate(rows):
        for n,w in d['inputs'].items():
            # Parameter widths are verified by the actual rebuilt harness separately.
            if not isinstance(r[n],int) or r[n]<0:bad.append([i,n,'invalid_value'])
        if prev and r[d['rst']] and prev[d['rst']]:
            if d['key']=='fifo' and prev['push_i'] and not prev['pop_i'] and (not r['push_i'] or r['data_i']!=prev['data_i']):bad.append([i,'stalled_item_changed'])
            if d['key']=='filter' and r['thresh_i']!=prev['thresh_i']:bad.append([i,'threshold_changed_without_reset'])
        prev=r
    return bad

def hidden_schedule(d,kind,seed=HIDDEN_SEED):
    k=d['key'];rng=random.Random(seed);rows=[];b={n:0 for n in d['inputs']};b[d['rst']]=0
    if k=='filter':b.update(thresh_i=2,enable_i=1)
    def add(n=1,**kw):
        b.update(kw)
        for _ in range(n):rows.append({**b,'cycle':len(rows),'stimulus_id':f'v2_hidden_{kind}:{len(rows)}'})
    add(2);b[d['rst']]=1
    if k=='onehot':
        vals=list(range(16));rng.shuffle(vals)
        for v in vals:add(2,oh_i=v,addr_i=rng.randrange(4),en_i=rng.randrange(2))
        add(2,oh_i=0,en_i=1);add(2,oh_i=15)
    elif k=='filter':
        for bit in [1,0,1,0]:add(5,filter_i=bit);add(1,filter_i=1-bit);add(2,filter_i=bit)
        add(3,enable_i=0,filter_i=1);add(3,filter_i=0);add(4,enable_i=1)
        if kind=='boundary':
            for threshold in [0,1,3]:add(2,**{d['rst']:0,'thresh_i':threshold});add(1,**{d['rst']:1});add(7,filter_i=1);add(7,filter_i=0)
    elif k=='fifo':
        for value in [0,255,rng.randrange(1,255),1,254]:
            add(2,push_i=0,pop_i=0);add(3,push_i=1,pop_i=0,data_i=value);add(1,pop_i=1);add(2,push_i=1,data_i=(value+1)%256);add(1,push_i=0,pop_i=1)
    elif k=='spill':
        for value in [0,255,rng.randrange(1,255),1]:
            add(1,flush_i=0,push_i=1,data_i=value);add(1,flush_i=1,push_i=1,data_i=value);add(2,push_i=0,flush_i=0);add(1,flush_i=1);add(1,flush_i=0)
        add(4,flush_i=1,push_i=1,data_i=255);add(3,flush_i=0,push_i=0)
    elif k=='stat':
        for value in [0,255,rng.randrange(1,255),1]:add(1,frame_done_i=1,frame_len_i=value);add(4,frame_done_i=0)
        for value in [255,0,47,19,251]:add(1,frame_done_i=1,frame_len_i=value)
        add(5,frame_done_i=0)
    else:
        for en in [1,0,1]:
            add(2,event_intr_i=1,reg2hw_intr_enable_q_i=en);add(2,event_intr_i=0);add(3,reg2hw_intr_enable_q_i=0);add(1,sw_clear=1);add(1,sw_clear=0)
        add(1,reg2hw_intr_test_q_i=1,reg2hw_intr_test_qe_i=1);add(3,reg2hw_intr_test_qe_i=0)
    if kind=='reset':
        # An effective reset deliberately cancels an outstanding obligation/transaction.
        if k=='spill':add(1,flush_i=1,push_i=1,data_i=71)
        if k=='stat':add(1,frame_done_i=1,frame_len_i=71)
        if k=='intr':add(1,event_intr_i=1)
        if k=='fifo':add(2,push_i=1,pop_i=0,data_i=71)
        add(2,**{d['rst']:0});add(1,**{d['rst']:1})
        if k=='fifo':add(1,pop_i=1)
    # Drain pending work with legal stable inputs; do not abandon a stalled FIFO item.
    if k=='fifo' and b['push_i'] and not b['pop_i']:add(1,pop_i=1)
    if k=='stat':add(4,frame_done_i=0)
    elif k=='spill':add(3,flush_i=0,push_i=0)
    else:add(4)
    assert not legality(d,rows),legality(d,rows)
    return rows
