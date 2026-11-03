import os,signal,shutil,time
from pathlib import Path
from run_repair_contract import ROOT,OUT,dump,read,model_pool
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 if len(args)>2 and args[1]==str(ROOT/'scripts/run_repair_contract.py').encode() and args[2]==b'methods':os.kill(int(p.name),signal.SIGTERM);time.sleep(1)
dest=OUT/'protocol_v2_skipped_unsupported_slot';dest.mkdir(exist_ok=True)
targets=[OUT/'methods/stat',OUT/'model_calls/repair/stat']
targets += [p for p in (OUT/'runs').rglob('stat') if p.is_dir() and any(x in p.parts for x in ['methods','hidden','parameters','equivalent_rewrite','legal_variant'])]
for src in targets:
 if src.exists():
  target=dest/src.relative_to(OUT);target.parent.mkdir(parents=True,exist_ok=True)
  assert src.resolve().is_relative_to(OUT.resolve()) and target.resolve().is_relative_to(OUT.resolve())
  shutil.move(str(src),str(target))
for name in ['model_pool_freeze.json','method_freeze.json']:
 if (OUT/name).exists():shutil.copyfile(OUT/name,dest/name)
shutil.copyfile(OUT/'frozen/stat/model_pool.json',dest/'stat_pool_before_inventory_fix.json')
model_pool()
dump(OUT/'candidate_inventory_amendment.json',{'reason':'Stat slot 0 had delay=2, unsupported by monitor. Loader incorrectly omitted it. Retain raw candidate as unsupported; do not substitute the next candidate. No raw model response changed and no new generation was performed.','rerun_parent':'stat','others_preserved':True,'archive':str(dest.relative_to(ROOT))})
