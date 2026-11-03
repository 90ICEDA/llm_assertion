import json, pathlib, subprocess, time, urllib.request
R=pathlib.Path(__file__).resolve().parents[1]; O=R/'deliverables/repair_contract_20261009'; O.mkdir(exist_ok=True)
for key in ['case118_prim_filter_ctr_early_accept','case122_prim_filter_ctr_streak_reset_ignored','case135_prim_intr_enable_mask_ignored']:
 p=R/'rtl_cases_real_scale120'/key
 for n in ['experiment/spec.txt','tb.v','correct.v','mutation.diff','case_metadata.json']:
  f=p/n
  if f.exists(): print('\nFILE',str(f.relative_to(R)),f.read_text()[-13000:])
print('OUTPUT DIRS',[p.name for p in (R/'outputs').iterdir() if p.is_dir()])
log=open(O/'ollama_server.log','a')
try: urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2)
except Exception:
 p=subprocess.Popen(['ollama','serve'],stdout=log,stderr=log,start_new_session=True)
 (O/'ollama_pid.txt').write_text(str(p.pid));time.sleep(3)
try:
 tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5));(O/'model_tags.json').write_text(json.dumps(tags,indent=2));print('MODELS',tags)
except Exception as e: print('MODEL_ERROR',repr(e))
