"""Require all paired R/A terminal versions before independent test admission."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(refinement,ablation,acquisition,out):
    rows=[]
    for experiment,folder,arms in [('refinement',refinement,['R0','R1','R2','R3']),('ablation',ablation,['A0','A1','A2','A3'])]:
        outcome=read(folder/'outcome.json')
        if outcome['status'] not in ('completed','completed_with_infrastructure_interruption'):
            raise ValueError('all_arms_must_finish_before_test')
        results=read(folder/'results.json')
        field='strategy' if experiment=='refinement' else 'arm'
        expected={(s,a) for s in (19207,19219) for a in arms}
        if len(results)!=8 or {(r['seed'],r[field]) for r in results}!=expected:raise ValueError('paired_population')
        if sum(r['model_calls'] for r in results)>8:raise ValueError('call_budget_exceeded')
        for result in results:
            directory=folder/f"seed{result['seed']}"/result[field]
            candidate=directory/'terminal.json';meta=directory/'frozen.json'
            row=dict(experiment=experiment,arm=result[field],seed=result['seed'],
                path=candidate.relative_to(ROOT).as_posix(),sha256=sha(candidate),
                freeze_path=meta.relative_to(ROOT).as_posix(),freeze_sha256=sha(meta),
                origin='accepted_real_model_proposal' if result['accepted'] else 'initial_retained_after_rejection',
                parent_bug='axis_fifo_oversize_atomic_drop')
            if experiment=='ablation':
                stream=result['search_stream']
                descriptors=acquisition/f"seed{result['seed']}"/stream/'descriptors.json'
                row.update(development_descriptors=descriptors.relative_to(ROOT).as_posix(),development_descriptors_sha256=sha(descriptors))
            rows.append(row)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x',encoding='utf-8') as f:json.dump(rows,f,ensure_ascii=False,indent=2)
    print('FROZEN',len(rows),'terminal versions; independent input selection may now begin',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refinement',type=Path,default=ROOT/'deliverables/research192_refinement_20261103_r01')
    parser.add_argument('--ablation',type=Path,default=ROOT/'deliverables/research192_ablation_20261103_r01')
    parser.add_argument('--acquisition',type=Path,default=ROOT/'deliverables/research192_ablation_prepare_20261103_r01')
    parser.add_argument('--out',type=Path,default=ROOT/'deliverables/reguard_mechanisms_20261103_r01/frozen_versions.json')
    freeze(**vars(parser.parse_args()))
