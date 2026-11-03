"""Isolate the permanent development-read audit hook from local file fixtures.

The child runs the unchanged strict no-holdout-read controller audit. The parent
only tests a clearly synthetic file-binding fixture, not independent data.
"""
import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import research149_execution_preflight as execution


def isolated(prep,out):
    subprocess.run([sys.executable,str(Path(__file__).with_name('research147_stability_preflight.py')),
        '--prepared',str(prep),'--out',str(out)],check=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    with patch.object(execution.prior,'audit',isolated):execution.audit(a.prepared.resolve(),a.out.resolve())
