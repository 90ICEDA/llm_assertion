"""Append a legal interrupt drain; preserve the predeclared input prefix and old run.
This is a testbench window repair after pending-obligation audit, not a change
to method selection, candidates, budget checkpoints, labels or success rules.
"""
import copy,shutil,time
from run_contract_v2 import OUT,ROOT,read,dump,rel,sha,definition,run,stamp
from contract_v2_spec import adjudicate,legality

ledger=OUT/'window_closure_amendment.json'
if ledger.exists():
    print('Window closure already applied');raise SystemExit(0)
affected=[];d=definition('intr')
for p in (OUT/'runs/hidden').glob('*/**/intr/*/result.json'):
    r=read(p)
    if r['status']!='ok':continue
    obs=adjudicate(d,read(ROOT/r['trace']),'registered_mask')
    if not obs[-1]['pending']:continue
    rows=read(p.parent/'input.json');extended=copy.deepcopy(rows)
    for _ in range(2):
        row={**extended[-1],'reg2hw_intr_enable_q_i':1,'event_intr_i':0,'reg2hw_intr_test_qe_i':0,'sw_clear':0,'cycle':len(extended),'stimulus_id':'v2_pending_drain:'+str(len(extended))};extended.append(row)
    assert extended[:len(rows)]==rows and not legality(d,extended)
    affected.append({'run':r['run_id'],'original_input_sha256':sha(p.parent/'input.json'),'original_pending':obs[-1]['pending'],'original_cycles':len(rows),'new_cycles':len(extended),'candidate':read(p.parent/'candidates.json')[0],'record':r,'extended_input':extended})
dump(OUT/'window_closure_plan.json',{'time':stamp(),'rule':'append exactly two active samples enable=1,event=0,test_qe=0,clear=0; preserve every original input sample; complete prior one-cycle mask obligations without continually initiating new ones','before_rerun':True,'affected':affected,'method_freeze_sha256':sha(OUT/'method_freeze.json'),'success_rule_unchanged':True})
start=time.perf_counter();done=[]
for item in affected:
    rd=ROOT/item['run'];relative=rd.relative_to(OUT/'runs');archive=OUT/'window_closure_archive'/relative
    assert rd.resolve().is_relative_to(OUT.resolve()) and archive.resolve().is_relative_to(OUT.resolve()) and not archive.exists()
    archive.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(rd),str(archive))
    (archive/'reproduce_archived.sh').write_text((archive/'reproduce.sh').read_text().replace(str(rd),str(archive)))
    r=item['record'];label='/'.join(relative.parts[:-2]);new=run(d,item['candidate'],None,label,r['variant'],rows=item['extended_input'],param=r['parameters'],rewrite=r['rewrite'])
    newobs=adjudicate(d,read(ROOT/new['trace']),'registered_mask');assert not newobs[-1]['pending']
    done.append({'run':item['run'],'archive':rel(archive),'original_cycles':item['original_cycles'],'new_cycles':item['new_cycles'],'same_input_prefix':True,'pending_after':[],'new_input_sha256':sha(rd/'input.json')})
dump(ledger,{'time':stamp(),'runs':done,'wall_seconds':time.perf_counter()-start,'training_or_model_changed':False,'parent_success_rule_changed':False,'independent_spec_ambiguity_remains':True})
# Preserve the auditor's earlier replays before fixing its final serialization NameError.
src=OUT/'audit_replays';dst=OUT/'audit_attempt_before_stamp_fix'
if src.exists() and not dst.exists():
    assert src.resolve().is_relative_to(OUT.resolve()) and dst.resolve().is_relative_to(OUT.resolve())
    shutil.move(str(src),str(dst))
    for p in dst.glob('*/reproduce.sh'):(p.parent/'reproduce_archived.sh').write_text(p.read_text().replace(str(src),str(dst)))
dump(OUT/'audit_serialization_failure.json',{'command':'python3 scripts/contract_v2_audit.py','exit_code':1,'stage':'after checks and four actual replays, before writing audit.json','error':"NameError: name 'stamp' is not defined",'fix':'import stamp; serialize each replay result immediately; rerun entire audit','raw_replay_evidence':rel(dst),'failed_attempt_replay_wall_seconds':None,'cost_status':'unknown for first successful four replay invocations before final serialization failed; retained as unknown rather than zero'})
print('Closed interrupt windows',len(done),flush=True)
