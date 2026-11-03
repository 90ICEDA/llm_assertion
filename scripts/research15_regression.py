"""Small replay-only regressions for onehot and FIFO Depth=0; no optimization."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
from research15_pipeline import ROOT, dump, read


def run(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    results=[]
    for case in ('onehot','fifo'):
        for variant in ('correct','buggy'):
            old=ROOT/f'deliverables/research_search_20261014_r01/runs/search/{case}/3113/ordinary/00/{case}/{variant}'
            folder=out/case/variant;folder.mkdir(parents=True)
            manifest={}
            for name in ('rtl.v','checker_tb.sv','assertions.sva','candidates.json','input.json','definition.json'):
                shutil.copy2(old/name,folder/name)
                manifest[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
            record=dict(case=case,variant=variant,original_run=str(old.relative_to(ROOT)),source_hashes=manifest)
            for stage in ('compile','simulate'):
                argv=read(old/(stage+'.command.json'))['argv']
                start=time.monotonic()
                p=subprocess.run(argv,cwd=folder,capture_output=True,text=True,timeout=60)
                (folder/(stage+'.stdout')).write_text(p.stdout)
                (folder/(stage+'.stderr')).write_text(p.stderr)
                item=dict(argv=argv,cwd=str(folder),exit_code=p.returncode,wall_seconds=time.monotonic()-start,
                          matches_previous_stdout=p.stdout==(old/(stage+'.stdout')).read_text())
                dump(folder/(stage+'.json'),item);record[stage]=item
                if p.returncode:break
            record['regression_reproduced']=bool(record.get('simulate',{}).get('matches_previous_stdout'))
            results.append(record)
    result=dict(results=results,all_reproduced=all(r['regression_reproduced'] for r in results),
        compile_attempts=sum('compile' in r for r in results),simulation_attempts=sum('simulate' in r for r in results),
        native_sva_calls=0,model_calls=0,formal_calls=0,
        scope='Identical old stimuli and procedural checker; regression only, no new evidence discovery or independent test.')
    dump(out/'summary.json',result)
    print(json.dumps(dict(reproduced=sum(r['regression_reproduced'] for r in results),total=len(results))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);args=p.parse_args();run(args.out)
