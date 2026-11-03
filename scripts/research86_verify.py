"""Final artifact consistency, split and physical-budget checks; no new queries."""
import argparse
from pathlib import Path
import research84_generalization as f
import research85_historical_transfer as h


def verify(report):
    read,dump,sha=f.read,f.dump,f.b.digest
    for name,digest in read(report/'input_hashes.json').items():assert sha(f.ROOT/name)==digest,name
    search=f.ROOT/'deliverables/research84_generalization_20261025_r01'
    history=f.ROOT/'deliverables/research85_historical_transfer_20261025_r01'
    f.b.verify(search);h.verify(history)
    records=read(search/'records.json');public=read(search/'public_feedback.json')
    assert len(records)==90
    assert {r['seed'] for r in records}==set(f.SEEDS)
    assert all(sum(r['method']==m for r in records)==18 for m in f.METHODS)
    assert read(search/'cost.json')['total']['native_execute_calls']==sum(r['native_executions'] for r in records)+sum(r['native_executions'] for p in public.values() for r in p['results'])+10
    used=set(read(history/'ibex166/excluded_words.json'));words=0;ledger_rows=0
    for seed in h.SEEDS:
        root=history/'ibex166'/f's{seed}'
        txns=read(root/'independent_cases.json');current={t['instruction'] for t in txns}
        assert len(current)==len(txns)==96 and not current&used
        assert txns==h.base.generate(seed,used)
        assert read(root/'generation.json')['generated_at']>read(history/'freeze.json')['time']
        assert sha(root/'candidate.json')==sha(history/'ibex166/candidate.json')
        assert read(root/'audit.json')['passed']
        ledger_rows+=read(root/'audit.json')['rows_audited'];used.update(current);words+=len(current)
    used54=set(read(history/'ibex54/excluded_low16.json'));new54=0
    for seed in h.SEEDS:
        root=history/'ibex54'/f's{seed}';vs=read(root/'vectors.json');current={v['low16'] for v in vs}
        assert len(current)==len(vs) and not current&used54
        assert read(root/'generation.json')['generated_at']>read(history/'freeze.json')['time']
        assert all(h.family54(v['low16'])==v['family'] for v in vs)
        assert all(v['status']=='unexposed' for v in read(root/'summary.json')['families'] if v['family'].endswith('hint'))
        used54.update(current);new54+=len(current)
    assert new54==48 and words==288 and ledger_rows==12672
    assert read(history/'cost.json')['total']['native_compile_calls']==12
    assert read(history/'cost.json')['total']['native_execute_calls']==12
    result=dict(passed=True,search_queries=90,physical_native_executions=2182,native_compiles=22,
        independent_words166=words,independent_rows166=ledger_rows,new_controls54=new54,
        original_freezes_unchanged=True,split_disjoint=True,all_artifact_inputs_bound=True,
        new_models=0,new_formal_queries=0,
        report_script_hashes={f'scripts/{n}':sha(f.ROOT/'scripts'/n) for n in ('research84_generalization.py','research85_historical_transfer.py','research86_generalization_report.py','research86_verify.py')},
        artifact_hashes={p.name:sha(p) for p in report.iterdir() if p.is_file() and p.name!='verification.json'})
    dump(report/'verification.json',result)
    print('VERIFIED86',result['search_queries'],result['physical_native_executions'],words,new54,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True,type=Path)
    verify(p.parse_args().report.resolve())
