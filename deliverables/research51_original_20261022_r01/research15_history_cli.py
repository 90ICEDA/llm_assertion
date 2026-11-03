"""Reproduce the historical decoder experiment in a new directory.

python3 scripts/research15_history_cli.py --run NAME prepare
python3 scripts/research15_history_cli.py --run NAME run
python3 scripts/research15_history_cli.py --run NAME report

prepare reuses locally verified immutable upstream source downloads; no fetch or
model calls are needed. The original experiment remains untouched.
"""
import argparse
from pathlib import Path
import re
import shutil
import research15_history as experiment


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('action',choices=['prepare','run','report']);a=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',a.run):ap.error('run must be a single directory name')
    origin=experiment.OUT;experiment.OUT=experiment.ROOT/'deliverables'/a.run
    if a.action=='prepare':
        assert experiment.OUT!=origin
        experiment.OUT.mkdir(exist_ok=False)
        for rev in ('before','after'):shutil.copytree(origin/rev,experiment.OUT/rev)
        for name in ('ibex166_archived_metadata.json','ibex166_live_pr.json'):shutil.copy2(origin/name,experiment.OUT/name)
        experiment.prepare()
        own=Path(__file__).resolve();shutil.copy2(own,experiment.OUT/own.name)
        freeze=experiment.read(experiment.OUT/'freeze.json');freeze[str(own.relative_to(experiment.ROOT))]=experiment.sha(own);experiment.dump(experiment.OUT/'freeze.json',freeze)
    elif a.action=='run':experiment.run()
    else:experiment.report()


if __name__=='__main__':main()
