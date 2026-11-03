"""Configurable launcher for frozen four-policy search experiments.

python3 scripts/research_search_cli.py --run NAME prepare
python3 scripts/research_search_cli.py --run NAME run [--case stat]
python3 scripts/research_search_cli.py --run NAME report
"""
import argparse
from pathlib import Path
import re
import shutil

import research_search_compare as experiment


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',default='research_search_20261014_r01')
    ap.add_argument('action',choices=['prepare','run','report'])
    ap.add_argument('--case',choices=experiment.CASES)
    a=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*',a.run):
        ap.error('--run must be a single safe directory name')
    experiment.OUT=experiment.x.ROOT/'deliverables'/a.run
    experiment.setup()
    if a.action=='prepare':
        experiment.prepare()
        # Freeze the wrapper too, before any queries. Never rewrite old freezes.
        own=Path(__file__).resolve()
        shutil.copy2(own,experiment.OUT/'source_snapshot'/own.name)
        freeze=experiment.x.read(experiment.OUT/'freeze.json')
        freeze[experiment.x.rel(own)]=experiment.x.sha(own)
        experiment.x.dump(experiment.OUT/'freeze.json',freeze)
    elif a.action=='run':experiment.run(a.case)
    else:experiment.report()


if __name__=='__main__':main()
