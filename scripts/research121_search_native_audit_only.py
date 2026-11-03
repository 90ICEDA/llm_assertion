"""Audit completed research117 raw records without regenerating cost reports.

The original auditor is reused unchanged. This entry avoids repeated filesystem
cost scans; it performs no native execution and writes only the audit directory.
"""
import argparse
from pathlib import Path
from unittest.mock import patch
import research117_search_preparation as s


def run(root, out):
    s.b.verify(root)
    assert s.read(root / 'outcome.json')['status'] == 'completed'
    with s.b.extension.installed(), patch.object(s.b, 'MODES', s.previous.MODES):
        s.previous.raw.audit(root, out)
    s.b.verify(root)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); run(a.run.resolve(), a.out.resolve())
