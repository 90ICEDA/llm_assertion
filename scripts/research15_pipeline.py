"""2026-10-15 integration audit. Does not modify sealed earlier experiments."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deliverables/research15_integration_20261015_r01'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def audit():
    old = ROOT / 'deliverables/research_integration_20261014_r01'
    checks=[]
    for rel, expected in read(old/'delivery_manifest.json').items():
        path=ROOT/rel
        actual=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        checks.append(dict(path=rel, expected=expected, actual=actual, passed=expected==actual))
    matrix=read(old/'completion_matrix.json')
    result=dict(previous_artifacts_unchanged=all(c['passed'] for c in checks),
                checks=checks, prior_completion_matrix=matrix,
                audit_scope='Rehash prior delivery manifest; does not rerun or reclassify prior experiments.',
                git_version=None, git_reason='Workspace .git is empty; use executed source SHA256 snapshots.')
    dump(OUT/'baseline_audit.json', result)
    print(json.dumps(dict(previous_artifacts_unchanged=result['previous_artifacts_unchanged'], checks=len(checks))))
    return result


def qualify():
    from research15_acceptance_qualification import run
    result=run()
    dump(OUT/'gate_qualification.json',result)
    print(json.dumps(dict(passed=result['passed'], tests=len(result['tests']))))
    from research15_evidence_qualification import run as evidence_run
    evidence=evidence_run();dump(OUT/'evidence_qualification.json',evidence)
    print(json.dumps(dict(evidence_passed=evidence['passed'],tests=len(evidence['tests']))))


def dispatch(args):
    if not args.run or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',args.run):
        raise ValueError('--run must be a new single directory name')
    base=ROOT/'deliverables'/args.run
    if args.action=='search':
        if not args.candidate:raise ValueError('--candidate is required')
        argv=[sys.executable,str(ROOT/'scripts/research15_search_experiment.py'),
              '--candidate',args.candidate,'--out',str(base),'--budget',str(args.budget)]
        subprocess.run(argv,check=True)
    elif args.action=='regression':
        from research15_regression import run
        run(base)
    elif args.action=='history':
        if args.stage not in ('prepare','run','report'):raise ValueError('--stage prepare/run/report required')
        subprocess.run([sys.executable,str(ROOT/'scripts/research15_history_cli.py'),'--run',args.run,args.stage],check=True)
    elif args.action=='native':
        import research15_native_interface as interface
        import research15_native_models as models
        import research15_native_experiment as experiment
        interface.OUT=models.OUT=experiment.OUT=base
        if args.stage=='initial':
            base.mkdir(parents=True,exist_ok=False);models.initial()
        elif args.stage=='qualify':models.qualify_initial()
        elif args.stage=='temporal':
            if (base/'shared_initial.json').exists():
                raise ValueError('Shared initial is already qualified; do not run the extra failure-repair block.')
            import research15_native_temporal_repair as extra
            extra.main()
        elif args.stage=='baseline':experiment.baseline()
        elif args.stage=='arms':
            if not args.witness:raise ValueError('--witness is required; no synthetic fallback')
            experiment.arms(args.witness)
        elif args.stage=='holdout':experiment.holdout()
        else:raise ValueError('--stage initial/qualify/temporal/baseline/arms/holdout required')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action', choices=['audit','qualify','costs','report','seal','search','native','history','regression'])
    parser.add_argument('--run')
    parser.add_argument('--stage')
    parser.add_argument('--candidate')
    parser.add_argument('--witness')
    parser.add_argument('--budget',type=int,default=6)
    args=parser.parse_args()
    if args.action in ('search','native','history','regression'):dispatch(args)
    elif args.action=='costs':
        from research15_costs import run
        run()
    elif args.action in ('report','seal'):
        import research15_report
        getattr(research15_report,args.action)()
    else:globals()[args.action]()
