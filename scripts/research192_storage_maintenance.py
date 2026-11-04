"""Remove only regenerable object/PCH caches from completed NEW campaign jobs.

Native executables, generated C++/RTL, model responses, command logs, waveforms,
and every historical run are retained. This never touches an in-flight compiler.
"""
import argparse
import json
import os
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]
NAMES=('research192_ablation_prepare_20261103_r01','research192_ablation_20261103_r01',
       'research192_refinement_20261103_r01','research192_local_qualification_20261103_r01',
       'research192_independent_qualification_20261103_r01','research192_independent_20261103_r01',
       'research192_fault_family_pilot_20261103_r01')
LOG=ROOT/'deliverables/reguard_mechanisms_20261103_r01/storage_maintenance.jsonl'


def sweep():
    count=0;size=0
    for name in NAMES:
        base=(ROOT/'deliverables'/name).resolve()
        if not base.exists():continue
        if not base.is_relative_to(ROOT/'deliverables'):raise ValueError('cleanup_scope')
        for current,dirs,files in os.walk(base):
            dirs[:]=[d for d in dirs if d not in ('source_snapshot','__pycache__','run_sources')]
            path=Path(current)
            if path.name!='obj_dir':continue
            dirs[:]=[]
            result=path.parent/'result.json'
            if not result.is_file():continue
            try:
                status=json.loads(result.read_text())
            except (OSError,ValueError):continue
            if status.get('compile_status') not in ('passed','failed','unknown'):continue
            for filename in files:
                candidate=path/filename
                if candidate.suffix not in ('.gch','.o','.a'):continue
                resolved=candidate.resolve()
                if not resolved.is_relative_to(base) or candidate.is_symlink():raise ValueError('cleanup_path_escape')
                try:
                    length=resolved.stat().st_size
                    resolved.unlink()
                except OSError:
                    continue
                count+=1;size+=length
                with LOG.open('a',encoding='utf-8') as f:
                    f.write(json.dumps(dict(path=str(resolved.relative_to(ROOT)),bytes=length,
                        kind='regenerable_completed_build_cache',binary_and_evidence_retained=True,time=time.time()))+'\n')
    if count:print('CLEANED',count,'derived files;',size,'bytes',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--watch',action='store_true')
    args=ap.parse_args()
    while True:
        sweep()
        if not args.watch:break
        done=ROOT/'deliverables/research192_independent_20261103_r01/outcome.json'
        if done.is_file():break
        time.sleep(20)
