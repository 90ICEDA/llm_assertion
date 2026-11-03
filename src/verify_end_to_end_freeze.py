from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);args=ap.parse_args();r=Path(args.run_dir).resolve();fail=[]
 for manifest_name,key in [('result_freeze.json','sha256'),('pipeline_manifest.json','artifact_sha256')]:
  p=r/manifest_name
  if not p.exists():fail.append(f'missing {manifest_name}');continue
  m=json.loads(p.read_text(encoding='utf-8'))
  for name,expected in m.get(key,{}).items():
   q=Path(name)
   if not q.exists():fail.append(f'missing artifact: {q}')
   elif sha(q)!=expected:fail.append(f'hash mismatch: {q}')
  if manifest_name=='pipeline_manifest.json':
   for name,expected in m.get('external_input_sha256',{}).items():
    q=Path(name)
    if not q.exists():fail.append(f'missing external input: {q}')
    elif sha(q)!=expected:fail.append(f'external input hash mismatch: {q}')
 report={'all_pass':not fail,'failure_count':len(fail),'failures':fail};print(json.dumps(report,indent=2))
 if fail:sys.exit(1)
if __name__=='__main__':main()
