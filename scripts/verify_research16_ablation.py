"""Verify the sealed October 16 ablation files without rerunning experiments."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    checks=[]
    for name in ('r01','r02','r03'):
        base=ROOT/f'deliverables/research16_ablation_20261016_{name}'
        manifest=json.loads((base/'report/manifest.json').read_text(encoding='utf-8'))
        for relative,expected in manifest.items():
            p=base/relative
            actual=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
            checks.append(dict(path=str(p.relative_to(ROOT)),passed=actual==expected))
    base=ROOT/'deliverables/research16_ablation_summary_20261016_r01'
    for relative,expected in json.loads((base/'manifest.json').read_text()).items():
        p=base/relative
        checks.append(dict(path=str(p.relative_to(ROOT)),passed=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==expected))
    result=dict(passed=all(c['passed'] for c in checks),file_checks=len(checks),failed=[c for c in checks if not c['passed']])
    (base/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    assert result['passed'],'sealed_ablation_artifact_mismatch'


if __name__=='__main__':main()
