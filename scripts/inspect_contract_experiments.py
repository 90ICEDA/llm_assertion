import json, pathlib, shutil, subprocess, urllib.request
R=pathlib.Path(__file__).resolve().parents[1]
def show(p, limit=15000):
 print('\nFILE',p.relative_to(R)); print(p.read_text(errors='replace')[:limit])
print('AGENTS', list(R.glob('AGENTS.md')), list((R/'.agents').rglob('AGENTS.md')))
for parent in [R.parent, R.parent.parent]:
 p=parent/'AGENTS.md'
 if p.is_file(): show(p)
for pattern in ['*onehot*','*filter*','*fifo_protocol*','*spill_register*']:
 for p in (R/'rtl_cases_real_scale210_independent_next').glob(pattern):
  print('CASE',p.name)
  for n in ['spec.md','correct.v','buggy.v','tb.v','case.json','metadata.json']:
   if (p/n).is_file(): show(p/n,6500)
base=R/'outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30'
for case in [*base.glob('*onehot*'),*base.glob('*fifo_protocol*'),*base.glob('*spill_register*')]:
 for s in ['01','06','07','08']:
  p=case/f'slot_{s}/attempt_01/evidence.json'
  if p.exists():
   d=json.loads(p.read_text(encoding='utf-8-sig'));print('CANDIDATE',case.name,s,json.dumps(d)[:9500])
for p in (R/'src').glob('*behavioral*v3*'):
 print('SOURCE',p.name)
print('OLLAMA')
for host in ['http://127.0.0.1:11434/api/tags']:
 try: print(host,urllib.request.urlopen(host,timeout=5).read().decode())
 except Exception as e: print(type(e).__name__,str(e))
print('VENV',subprocess.run([str(R/'.venv-pilot/bin/python'),'--version'],capture_output=True,text=True).stdout)
