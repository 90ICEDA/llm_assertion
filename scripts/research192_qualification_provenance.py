"""Preserve the exact source loaded before an in-flight hardening edit.

Reconstruction is accepted only if its SHA256 equals the pre-existing prepared
source binding. This adjusts provenance, never native observations or decisions.
"""
import argparse
import hashlib
from pathlib import Path
import research192_temporal_refinement as r


def snapshot(out, finalize=False):
    source = Path(r.__file__).read_text()
    block = '''    for assertion in candidate:
        observed = [(row, a) for row in evidence
                    if row.get('status') == 'confirmed' and row.get('label') in ('legal', 'violation')
                    for a in row.get('assertions', []) if a.get('assertion') == assertion['label']]
        targets = [row for row, a in observed if row['label'] == 'violation']
        if targets and all(a.get('trigger') is False for _, a in observed):
            add('vacuity_or_insufficient_trigger', assertion['label'], 'antecedent', targets[0],
                'No trigger in the confirmed finite evidence despite exposed targets; this is finite-suite inactivity, not proof of logical vacuity.')
'''
    if source.count(block) != 1:
        raise ValueError('unexpected_source')
    source = source.replace(block, '')
    source = source.replace("            s.dump(Path(job['folder']) / 'result.json', job['result'])\n", '')
    source = source.replace("    if p.digest(initial) != p.digest(baseline):\n        raise ValueError('external_initial_requires_a_separately_bound_baseline')\n", '')
    source = source.replace('dict(source=reused, candidate_sha256=p.digest(proposal),', 'dict(source=reused, candidate_sha256=key,')
    old = r.s.read(r.ROOT/'deliverables/research192_refinement_prepare_20261103_r01/source_bindings.json')
    expected = old[r.s.rel(Path(r.__file__))]
    if hashlib.sha256(source.encode()).hexdigest() != expected:
        raise ValueError('loaded_source_hash_not_reconstructed')
    target = out/'run_sources/research192_temporal_refinement.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
    r.s.dump(out/'source_provenance_note.json',dict(
        loaded_module_snapshot=r.s.rel(target), sha256=expected,
        evidence='Exact SHA256 equals source binding made before the native qualification process started.',
        reason='While native fixtures were running, only finite-vacuity diagnostics, native-exception recording and external-initial/cache metadata guards were hardened. Already-running process retains its imported module.',
        native_outcomes_modified=False, reconstructed_source_verified=True))
    if finalize:
        if not (out/'REPORT.md').exists():
            raise ValueError('qualification_still_running')
        r.s.dump(out/'source_bindings.json',{
            r.s.rel(target):r.s.sha(target),
            'scripts/research192_local_qualification.py':r.s.sha(r.ROOT/'scripts/research192_local_qualification.py'),
            r.s.rel(Path(__file__)):r.s.sha(Path(__file__))})
    print('LOADED_SOURCE_SNAPSHOT_VERIFIED', expected, flush=True)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out',type=Path,required=True)
    cli.add_argument('--finalize',action='store_true')
    a=cli.parse_args()
    snapshot(a.out.resolve(),a.finalize)
