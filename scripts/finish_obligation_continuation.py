"""Finish already-frozen experiments; fail closed, preserve every run/log."""
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/obligation_continuation_20261013_r01'


def run(label,script,*args):
    stdout=OUT/(label+'.stdout');stderr=OUT/(label+'.stderr')
    with stdout.open('x') as out,stderr.open('x') as err:
        started=time.time();argv=[sys.executable,'-B',str(ROOT/'scripts'/script),*args]
        p=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=err)
    record=dict(label=label,argv=argv,exit_code=p.returncode,wall_seconds=time.time()-started)
    (OUT/(label+'.orchestration.json')).write_text(json.dumps(record,indent=2))
    print(label,p.returncode,flush=True)
    if p.returncode:raise RuntimeError(label+' failed; logs preserved')


def main_validation():
    run('formal_acceptance','obligation_continuation_experiment.py','acceptance')
    run('formal_regression','obligation_continuation_regression.py')


def main():
    while not (OUT/'formal/final_freeze.json').exists():time.sleep(2)
    print('Formal final freeze observed; starting independent validation and separate historical initial generation',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        validation=pool.submit(main_validation)
        run('ibex_generate','obligation_ibex_experiment.py','generate')
        run('ibex_develop','obligation_ibex_experiment.py','develop')
        validation.result()
    run('ibex_acceptance','obligation_ibex_experiment.py','acceptance')
    run('ibex_regression','obligation_continuation_regression.py','--historical')
    run('isolation','obligation_continuation_isolation.py')
    print('ALL FROZEN EXPERIMENTS COMPLETE',flush=True)


def historical_resume():
    assert (OUT/'historical_formal/freeze.json').exists()
    run('ibex_develop','obligation_ibex_experiment.py','develop')
    run('ibex_acceptance','obligation_ibex_experiment.py','acceptance')
    run('ibex_regression','obligation_continuation_regression.py','--historical')
    while not (OUT/'formal/postfreeze_regression/summary.json').exists():time.sleep(2)
    run('isolation','obligation_continuation_isolation.py')
    print('ALL FROZEN EXPERIMENTS COMPLETE; failed initial generation retained separately',flush=True)


if __name__=='__main__':
    if '--historical-resume' in sys.argv:historical_resume()
    else:main()
