"""Repair vector antecedent truncation and replay EVERY executable monitor.

Archive original monitor, logs and raw results. Verify unchanged training
feedback before allowing existing model decisions to remain in the experiment.
"""
import shutil,time
from run_repair_contract import ROOT,OUT,read,dump,definition,execute_run
records=[]
for p in list((OUT/'runs').rglob('result.json')):
 old=read(p)
 if old['status']!='ok':continue
 rd=p.parent;source=(rd/'checker_tb.sv').read_text()
 if "? 1'b1 : 1'b0" in source:continue
 relative=rd.relative_to(OUT/'runs');label='/'.join(relative.parts[:-2]);rows=read(rd/'input.json');cs=read(rd/'candidates.json')
 archive=OUT/'checker_lowering_v1'/relative
 assert archive.resolve().is_relative_to(OUT.resolve());archive.parent.mkdir(parents=True,exist_ok=True)
 shutil.move(str(rd),str(archive))
 new=execute_run(definition(old['case']),rows,cs,label,old['variant'],param=old['parameters'],rewrite=old['rewrite'],invalid_bus_variant=old['legal_behavior_variant'],controlled_mutation=old.get('controlled_mutation'))
 def signature(r):return [(c['id'],c['trigger_cycles'],c['failure_cycles']) for c in r['candidates']]
 same=new['status']=='ok' and signature(old)==signature(new)
 record={'run':new['run_id'],'old_evidence':str(archive.relative_to(ROOT)),'unchanged_metrics':same,'training_run':'/methods/' in new['run_id'],'new_status':new['status']};records.append(record)
 dump(OUT/'lowering_replay_audit.json',{'runs':records,'training_all_unchanged':all(r['unchanged_metrics'] for r in records if r['training_run']),'changed_run_count':sum(not r['unchanged_metrics'] for r in records),'status':'running'})
result={'runs':records,'training_all_unchanged':all(r['unchanged_metrics'] for r in records if r['training_run']),'changed_run_count':sum(not r['unchanged_metrics'] for r in records),'status':'complete'}
dump(OUT/'lowering_replay_audit.json',result)
assert result['training_all_unchanged'], 'training feedback changed; affected method arms MUST be rerun'
assert all(r['new_status']=='ok' for r in records)
print('LOWERING_AUDIT',len(records),result['changed_run_count'],result['training_all_unchanged'],flush=True)
