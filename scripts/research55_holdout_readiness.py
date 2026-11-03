"""Audit prerequisites for Ibex independent testing without freezing rejected SVA.

Read-only with respect to experiment artifacts. Does not generate test words,
submit model requests, invoke native tools, or claim acceptance from metadata.
"""
import argparse
import json
from pathlib import Path
import research55_native_plan_alignment as g


def run(prep,experiment,out):
    out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,condition):
        checks.append(dict(name=name,passed=bool(condition)))
        assert condition,name
    for name,sha in g.read(prep/'sealed.json').items():check('seal/'+name,g.old.digest(prep/name)==sha)
    outcome=g.read(experiment/'outcome.json')
    history=g.read(prep/'history_cases.json');search=g.read(prep/'search_cases.json')
    used=sorted({t['instruction'] for t in history+search})
    manifest=g.read(prep/'development_manifest.json')
    check('151_unique_development_words',len(used)==151)
    check('development_manifest_complete',used==manifest['all_used_instructions'])
    check('history_search_counts',len(history)==115 and len(search)==36)
    bindings=g.read(prep/'source_binding.json')
    for name,sha in bindings['source_sha256'].items():check('original_rtl/'+name,g.old.digest(prep/name)==sha)
    # Cross-check all recorded transactions from this historical case's runs,
    # including local controls and repeated replays, against the exclusion list.
    transaction_sources={}
    for folder in sorted((g.ROOT/'deliverables').iterdir()):
        if not folder.is_dir() or not any(folder.name.startswith(f'research{i}_') for i in range(51,56)):continue
        for path in folder.rglob('transactions.json'):
            rows=g.read(path)
            if isinstance(rows,list) and rows and all(isinstance(t,dict) and 'instruction' in t for t in rows):
                check('exclude/'+path.relative_to(g.ROOT).as_posix(),{t['instruction'] for t in rows}<=set(used))
                transaction_sources[path.relative_to(g.ROOT).as_posix()]=g.old.digest(path)
    files={}
    for p in experiment.rglob('*'):
        if p.is_file() and (p.suffix in ('.json','.sva','.log') or p.name=='response.stream.raw') and 'obj_dir' not in p.parts:
            files[p.relative_to(g.ROOT).as_posix()]=g.old.digest(p)
    files.update({(prep/name).relative_to(g.ROOT).as_posix():g.old.digest(prep/name) for name in
                 ('source_binding.json','development_manifest.json','history_cases.json','search_cases.json','source_hashes.json')})
    files.update({(prep/name).relative_to(g.ROOT).as_posix():g.old.digest(prep/name) for name in bindings['source_sha256']})
    candidates=[]
    for folder in sorted(experiment.glob('v[0-9]*')):
        path=folder/'model_call/candidate.json'
        candidates.append(dict(version=folder.name,decision=g.read(folder/'decision.json'),
            candidate_sha256=g.old.acceptance.sha(g.read(path)) if path.exists() else None,
            classification='Rejected development proposal; not a frozen accepted version.',
            full_history_present=(folder/'history/result.json').exists(),full_search_present=(folder/'search/result.json').exists()))
    reasons=[]
    if outcome.get('accepted_candidate_sha256') is None:reasons.append('no_accepted_candidate_hash')
    if not (experiment/'accepted_candidate.json').exists():reasons.append('no_accepted_candidate_file')
    if not any(c['decision']['accepted'] and c['full_history_present'] and c['full_search_present'] for c in candidates):
        reasons.append('no_accepted_version_with_full151_replay')
    # This script records the current blocked state only. A future accepted run
    # requires an independent acceptance audit before a freeze/test operation.
    check('current_run_rejected',outcome['status']=='no_accepted_sva' and bool(reasons))
    g.dump(out/'readiness.json',dict(status='blocked_no_accepted_version',reasons=reasons,
        accepted_candidate_sha256=None,candidates=candidates,checks=checks,
        frozen=False,independent_words_generated=0,new_model_calls=0,new_native_calls=0))
    g.dump(out/'development_exclusion.json',dict(unique_words=used,unique_word_count=len(used),history_count=len(history),
        search_count=len(search),transaction_record_sources=transaction_sources,
        scope='All instruction words recorded in research51..55 original-decoder transactions, including preparation controls and replays.'))
    g.dump(out/'artifact_inventory.json',dict(files_sha256=files,source=bindings,
        note='Readiness inventory, not a freeze certificate. No secret files or values included.'))
    g.dump(out/'independent_protocol.json',dict(status='preregistered_not_executed',word_count=96,
        generation='Only after an accepted candidate and freeze certificate; exclude all development_exclusion.unique_words.',
        families=dict(branch_reserved=24,op_bit28=24,branch_legal=24,op_control=24),
        configs=g.old.CONFIGS+[dict(RV32E=1,RV32M=0)],hold_samples=dict(min=2,max=9),
        required_exposure=['illegal_branch_persists','op_bit28_illegal'],
        acceptance='Require original-RTL exposure for both obligations, necessary triggers, no misses or false alarms or critical unknown, complete native execution, unchanged frozen hashes.',
        legal_label_rule='Use independent ISA decoding per configuration, not generator family labels; report any unknown and actual exposure denominator.',
        leakage_rule='If any test result informs modification/selection, reclassify entire batch as development and draw fresh words after a new freeze.',
        scope='Original decoder only, finite simulation, no full-core or formal-proof claim.'))
    print('HOLDOUT_BLOCKED',len(checks),'checks;',len(used),'excluded; generated0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
