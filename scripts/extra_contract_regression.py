"""Additional frozen-assertion boundary and legal-variant controls."""
import copy,sys
from run_repair_contract import OUT,read,dump,definition,execute_run,schedule,natural

f={'rows':[]} if '--legacy-only' in sys.argv else read(OUT/'method_freeze.json')
for m in f['rows']:
 if m['status']!='frozen':continue
 d=definition(m['case']);k=d['key'];rows=schedule(d,'train')[:2];base=dict(rows[-1]);base[d['rst']]=1
 def add(n=1,**kw):
  base.update(kw)
  for _ in range(n):
   r=dict(base);r['cycle']=len(rows);r['stimulus_id']='hidden_boundary:'+str(len(rows));rows.append(r)
 if k=='onehot':
  for bits in [0,1,2,4,8,15,3,12]:add(2,oh_i=bits,addr_i=0,en_i=int(bits!=0))
 elif k=='filter':
  # Threshold configuration changes only across reset, avoiding an unspecified transition.
  for threshold in [0,1,2,3]:
   add(2,**{d['rst']:0,'thresh_i':threshold,'filter_i':0});add(1,**{d['rst']:1});add(5,filter_i=1);add(5,filter_i=0)
 elif k=='fifo':
  for value in [0,255]:
   add(1,push_i=0,pop_i=0);add(4,push_i=1,pop_i=0,data_i=value);add(1,pop_i=1);add(1,push_i=0)
 elif k=='spill':
  for value in [0,255]:add(1,push_i=1,flush_i=1,data_i=value);add(2,push_i=0,flush_i=0)
  add(3,push_i=1,flush_i=0,data_i=255);add(2,flush_i=1)
 elif k=='stat':
  for value in [0,255,1,254]:add(1,frame_done_i=1,frame_len_i=value)
  add(4,frame_done_i=0)
 else:
  add(1,event_intr_i=1,reg2hw_intr_enable_q_i=1);add(2,event_intr_i=0);add(2,reg2hw_intr_enable_q_i=0);add(1,sw_clear=1);add(1,sw_clear=0);add(1,reg2hw_intr_test_q_i=1,reg2hw_intr_test_qe_i=1);add(2,reg2hw_intr_test_qe_i=0,reg2hw_intr_enable_q_i=1)
 for v in ['correct','buggy']:execute_run(d,rows,[m['candidate']],f'boundary/{m["arm"]}',v)
 execute_run(d,schedule(d,'regression',seed=20261009+333),[m['candidate']],f'equivalence_reference/{m["arm"]}')
 if k=='onehot':
  variant_rows=schedule(d,'train')[:2];r=dict(variant_rows[-1]);r['rst_n']=1
  for bits,en in [(0,1),(1,1),(3,1),(0,0),(15,1)]:
   for _ in range(2):
    r={**r,'oh_i':bits,'en_i':en,'cycle':len(variant_rows),'stimulus_id':'strict_parameter:'+str(len(variant_rows))};variant_rows.append(r)
  execute_run(d,variant_rows,[m['candidate']],f'legal_variant/{m["arm"]}',param={'StrictCheck':0})
  execute_run(d,variant_rows,[m['candidate']],f'legal_variant_reference/{m["arm"]}')
# Old slot06/07 get the same actual behavior-changing legal variant after freeze,
# so its effect is distinguished from ordinary alpha-renaming.
d=definition('spill');execute_run(d,schedule(d,'held'),natural('spill'),'legacy_legal_variant',invalid_bus_variant=True)
for k,mutation in [('spill','spill_valid_only'),('stat','stat_drop_valid'),('stat','stat_corrupt_length')]:
 d=definition(k)
 execute_run(d,schedule(d,'train'),natural(k),'controlled_coverage/'+mutation,'buggy',controlled_mutation=mutation)
