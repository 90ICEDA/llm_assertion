"""Save executable sources and seal all closed continuation artifacts."""
import concurrent.futures
import json
import shutil
import time
import obligation_continuation as cont
from obligation_continuation import x


def main():
    x.OUT=x.ROOT/'deliverables'/cont.NAME
    assert (x.OUT/'REPORT.md').exists()
    complete=x.read(x.OUT/'delivery/completion.json')
    isolation=x.read(x.OUT/'isolation_audit.json')
    assert isolation['formal_messages']==32
    assert not x.read(x.OUT/'historical_integrity.json')['changed']
    sources=set()
    for block in ('formal','historical_formal'):
        for manifest in ('freeze.json','final_freeze.json'):
            for path,h in x.read(x.OUT/block/manifest).items():
                p=x.ROOT/path;assert x.sha(p)==h,('freeze_changed',path)
                if p.suffix=='.py':sources.add(p)
    sources.update((x.ROOT/'scripts').glob('*obligation*continuation*.py'))
    sources.update((x.ROOT/'scripts').glob('obligation_ibex*.py'))
    folder=x.OUT/'delivery/code_snapshot';folder.mkdir(exist_ok=False)
    for p in sorted(sources):shutil.copyfile(p,folder/p.name)
    x.dump(x.OUT/'delivery/source_manifest.json',{x.rel(p):x.sha(p) for p in sorted(sources)})
    model=x.read(x.OUT/'delivery/model_costs.json')
    assert len(model['calls'])==39
    x.dump(x.OUT/'delivery/final_checks.json',dict(frozen_interfaces_and_candidates_unchanged=True,
        actual_model_calls=39,formal_model_calls=32,preflight_calls=3,initial_generation_calls=4,
        main_development_queries=168,historical_development_queries=56,
        independent_acceptance_pairs=336,postfreeze_regression_queries=192,explanatory_pairs=2,
        original_historical_tests_refreshed=x.read(x.OUT/'historical_original_replay/summary.json')['passed_reproduction'],
        snapshot_sources=len(sources),native_cross_execution=complete['native_sva'],
        reruns_and_errors_retained=True,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    excluded={'seal.stdout','seal.stderr','delivery/continuation_artifact_manifest.json'}
    files=[p for p in x.OUT.rglob('*') if p.is_file() and str(p.relative_to(x.OUT)) not in excluded]
    def hashed(p):return x.rel(p),x.sha(p)
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:hashes=dict(pool.map(hashed,files))
    x.dump(x.OUT/'delivery/continuation_artifact_manifest.json',dict(files=hashes,
        excludes=sorted(excluded),reason='own manifest and currently-open sealing stdout/stderr excluded; all experimental logs included'))
    print('SEALED',len(hashes),'files;',len(sources),'source snapshots; 39 actual model calls',flush=True)


if __name__=='__main__':main()
