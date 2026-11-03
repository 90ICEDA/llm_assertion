"""Audit and repair a stimulus tail that abandons a stalled FIFO item.

Original plans and failed runs are retained. This repairs testbench legality,
never assertions, model prompts, or DUT RTL. Training schedules must be legal.
"""
import shutil,time
from run_repair_contract import OUT,ROOT,read,dump,definition,execute_run
audit=[]
for p in list((OUT/'runs').rglob('result.json')):
 r=read(p)
 if r['case']!='fifo':continue
 rows=read(ROOT/r['input']);bad=[]
 for i,(a,b) in enumerate(zip(rows,rows[1:]),1):
  if a['rst_ni'] and b['rst_ni'] and a['push_i'] and not a['pop_i'] and (not b['push_i'] or a['data_i']!=b['data_i']):bad.append(i)
 if not bad:audit.append({'run':r['run_id'],'legal':True,'repair':False});continue
 assert '/methods/' not in r['run_id'], 'illegal training input requires full method rerun'
 repaired=[]
 for i,row in enumerate(rows):
  if i in bad:
   drain={**rows[i-1],'push_i':1,'pop_i':1,'stimulus_id':'legality_repair_drain:'+str(i)};repaired.append(drain)
  repaired.append(dict(row))
 for i,row in enumerate(repaired):row['cycle']=i
 rd=p.parent;relative=rd.relative_to(OUT/'runs');label='/'.join(relative.parts[:-2]);candidates=read(rd/'candidates.json')
 archive=OUT/'failed_attempts'/('illegal_fifo_'+str(time.time_ns()));assert archive.resolve().is_relative_to(OUT.resolve())
 r.update(status='invalid_input',invalid_input_cycles=bad,repair_reason='insert accepted drain before abandoning stalled item');dump(p,r)
 shutil.move(str(rd),str(archive))
 rr=execute_run(definition('fifo'),repaired,candidates,label,r['variant'],param=r['parameters'],rewrite=r['rewrite'])
 audit.append({'run':r['run_id'],'legal':True,'repair':True,'old_bad_cycles':bad,'original':str(archive.relative_to(ROOT)),'new_result':rr['run_id']})
dump(OUT/'input_legality_audit.json',{'scope':'Depth=0 instantiated compatibility contract; data/push held under backpressure until pop or reset; excludes generic Depth>0 assertions','rows':audit,'repaired_runs':sum(x['repair'] for x in audit),'training_modified':False})
