"""Report and verify all terminal reset-repair trials, including failures."""
import concurrent.futures
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research27_reset_campaign_20261020_r01'
RUNS=[ROOT/'deliverables'/f'research27_closed_loop_20261020_r0{i}' for i in range(1,7)]
RESUME=False


def execute(label,*args):
    with (OUT/(label+'.log')).open('w') as stream:
        result=subprocess.run([sys.executable,*map(str,args)],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(label+'_failed; see saved log')
    print(label,'completed',flush=True)


def report(run):
    verification=run/'report/verification.json'
    if RESUME and verification.exists() and json.loads(verification.read_text())['passed']:
        print(run.name,'reused completed verification; no artifact changes permitted in resume mode',flush=True)
        return
    execute(run.name+'_report','scripts/research21_report.py','--run',run)
    execute(run.name+'_verify','scripts/research21_report.py','--run',run,'--verify')


def main():
    global RESUME
    parser=argparse.ArgumentParser()
    parser.add_argument('--resume',action='store_true',help='Reuse already completed verifications only when experiment artifacts are unchanged.')
    RESUME=parser.parse_args().resume
    for run in RUNS:
        assert json.loads((run/'outcome.json').read_text())['status']!='running'
    OUT.mkdir(parents=True,exist_ok=RESUME)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(report,RUNS))
    execute('focused_summary','scripts/research27_summary.py','--run',RUNS[-1],
        '--out',ROOT/'deliverables/research27_reset_notes_20261020_r01')
    args=['scripts/research22_report.py','--out',OUT,'--runs',*RUNS]
    for suffix in ('r01','r02','r06'):
        args+=['--qualification',ROOT/'deliverables'/f'research27_request_qualification_20261020_{suffix}']
    execute('campaign',*args)
    execute('campaign_verify','scripts/research22_report.py','--out',OUT,'--verify')
    print('FINALIZED',OUT,flush=True)


if __name__=='__main__':main()
