"""Finalize terminal boundary runs; no generation and no candidate selection."""
import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    out=args.out.resolve()
    assert ROOT in out.parents
    old=[ROOT/'deliverables'/n for n in (
        'research22_closed_loop_20261019_r01','research22_closed_loop_20261019_r02',
        'research23_closed_loop_20261019_r01','research24_closed_loop_20261019_r01',
        'research25_closed_loop_20261020_r01')]
    new=[ROOT/'deliverables'/f'research26_closed_loop_20261020_r0{i}' for i in range(1,7)]
    # This guard precedes all independent result/report access.
    for run in old+new:
        assert json.loads((run/'outcome.json').read_text())['status']!='running',str(run)
    out.mkdir(parents=True,exist_ok=False)
    def execute(label,*arguments):
        command=[sys.executable,*map(str,arguments)]
        with (out/(label+'.log')).open('w') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(f'{label}_failed_{result.returncode}; see saved log')
        print(label,'completed',flush=True)
    execute('service_shutdown','scripts/research20_close_service.py','--owner',new[1],
        '--finished',*new)
    def report(run):
        label=run.name
        execute(label+'_report','scripts/research21_report.py','--run',run)
        execute(label+'_verify','scripts/research21_report.py','--run',run,'--verify')
    # r01 and old runs have already been verified and are not mutated here.
    for run in old+[new[0]]:
        assert json.loads((run/'report/verification.json').read_text())['passed'],str(run)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(report,new[1:]))
    qualifiers=sorted(p for p in (ROOT/'deliverables').iterdir() if p.is_dir()
        and any(p.name.startswith('research'+str(i)+'_') for i in range(22,27))
        and any(tag in p.name for tag in ('feedback_qualification','sampling_qualification','schema_probe','interface_qualification','preflight_qualification')))
    arguments=['scripts/research22_report.py','--out',out,'--runs',*old,*new]
    for path in qualifiers:
        arguments+=['--qualification',path]
    for suffix in ('r01','r02'):
        arguments+=['--preceding',ROOT/'deliverables'/('research21_closed_loop_20261018_'+suffix)]
    execute('campaign',*arguments)
    execute('campaign_verify','scripts/research22_report.py','--out',out,'--verify')
    print('FINALIZED',out,flush=True)


if __name__=='__main__':
    main()
