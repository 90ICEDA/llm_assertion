"""Fresh original Ibex #54 test replay, separate from generated SVA results."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
PRIOR=ROOT/'deliverables/obligation_continuation_20261013_r01'


def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,indent=2)+'\n')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'deliverables/research_ibex_20261014_r01');a=ap.parse_args()
    out=a.out.resolve();out.mkdir(exist_ok=False,parents=True)
    dump(out/'provenance.json',dict(source= json.loads((PRIOR/'historical_formal/history_lineage.json').read_text()),
        status='fresh original RTL/test reproduction only; not new generated/native SVA result',
        dataset='development: these historical test vectors have been observed before'))
    results=[]
    for revision in ('before','after'):
        for cohort in ('benchmark','boundary'):
            old=PRIOR/'historical_original_replay'/revision/cohort
            folder=out/revision/cohort;folder.mkdir(parents=True)
            hashes={}
            for name in ('ibex_defines.sv','ibex_compressed_decoder.sv','tb.sv'):
                shutil.copyfile(old/name,folder/name)
                hashes[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
            commands=[('compile',['iverilog','-g2012','-s','tb','-o','sim.out','ibex_defines.sv','ibex_compressed_decoder.sv','tb.sv']),('execute',['vvp','sim.out'])]
            record=dict(revision=revision,cohort=cohort,source_sha256=hashes)
            for label,argv in commands:
                t=time.monotonic();p=subprocess.run(argv,cwd=folder,capture_output=True,text=True,timeout=60)
                (folder/(label+'.stdout')).write_text(p.stdout);(folder/(label+'.stderr')).write_text(p.stderr)
                c=dict(argv=argv,cwd=str(folder),exit_code=p.returncode,wall_seconds=time.monotonic()-t)
                dump(folder/(label+'.json'),c);record[label]=c
                if label=='compile' and p.returncode:break
            record['original_log_matches']=('execute' in record and (folder/'execute.stdout').read_text()==(old/'simulate.stdout').read_text())
            record['expected_behavior_reproduced']=bool(record.get('execute') and record['compile']['exit_code']==0 and
                record['original_log_matches'] and ((record['execute']['exit_code']!=0) if revision=='before' else (record['execute']['exit_code']==0)))
            results.append(record)
    dump(out/'summary.json',dict(results=results,all_expected_reproduced=all(r['expected_behavior_reproduced'] for r in results),
        model_calls=0,native_sva_calls=0,formal_calls=0,scope='Original historical benchmark/boundary regression; procedural RTL testbench, not native concurrent SVA or proof.'))
    print(json.dumps(dict(reproduced=sum(r['expected_behavior_reproduced'] for r in results),total=len(results))))


if __name__=='__main__':main()
