"""Stop only this audit's methods process; archive its incomplete experiment."""
import os,signal,time,shutil
from pathlib import Path
from run_repair_contract import ROOT,OUT,dump
for p in Path('/proc').iterdir():
 if not p.name.isdigit():continue
 try:args=(p/'cmdline').read_bytes().split(b'\0')
 except OSError:continue
 if len(args)>2 and args[1]==str(ROOT/'scripts/run_repair_contract.py').encode() and args[2]==b'methods':
  os.kill(int(p.name),signal.SIGTERM);time.sleep(1)
dest=OUT/'protocol_v1_missing_compile_feedback';dest.mkdir(exist_ok=True)
for relative in ['methods','model_calls/repair','runs/methods','runs/hidden','runs/parameters','runs/equivalent_rewrite','runs/legal_variant','method_freeze.json']:
 src=OUT/relative;target=dest/relative
 if src.exists():
  assert src.resolve().is_relative_to(OUT.resolve()) and target.resolve().is_relative_to(OUT.resolve())
  target.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(src),str(target))
dump(OUT/'method_protocol_amendment.json',{'reason':'Initial repair prompt omitted concrete compiler/signal-legality diagnostics; repeated unsupported candidates. Preserve incomplete v1 and rerun every method from same frozen pool, same model, same 2-repair-call budget.','candidate_pool_unchanged':True,'new_model_calls_charged_as_separate_protocol_run':True,'validation':'recompile original baseline and all corrected feedback arms, then freeze before hidden evaluation','date':'2026-10-09'})
