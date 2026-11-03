"""Read-only audit of actual four-policy native search, including negative runs."""
from collections import Counter
from pathlib import Path
from research15_pipeline import ROOT,OUT,read,dump
from research15_acceptance import sha
from research15_search_experiment import Policy,stimulus

BASE=ROOT/'deliverables/research15_search_20261015_r01/fixed_initial_negative'


def run():
    protocol=read(BASE/'protocol.json');results=read(BASE/'results.json')
    checks=[]
    def check(name,value,**details):checks.append(dict(name=name,passed=bool(value),**details))
    check('all_planned_queries_executed',len(results)==protocol['planned_queries'])
    candidate=read(BASE/'initial_candidate.json')
    check('candidate_is_original_model_response',sha(candidate)==sha(read(Path(protocol['candidate_source_path']))))
    for spec in protocol['specs']:
        for method in protocol['methods']:
            rows=sorted([r for r in results if r['seed']==spec['seed'] and r['method']==method],key=lambda r:r['query'])
            check(f'budget:{spec["seed"]}:{method}',len(rows)==protocol['queries_per_method_per_seed'])
            policy=Policy(method,spec['seed'])
            for r in rows:
                label=f'{spec["seed"]}:{method}:{r["query"]}'
                expected_selection=policy.choose()
                check('past_only_selection:'+label,expected_selection==r['selection'])
                expected_view=policy.update(r['selection']['family'],r['evidence'])
                check('permitted_feedback:'+label,expected_view==r['permitted_feedback_view'])
                folder=BASE/r['folder']
                expected_rows=stimulus(spec['seed']+r['query']*1009,r['selection']['family'])
                check('seeded_input:'+label,expected_rows==read(folder/'stimulus.json'))
                traces=[]
                for mode in ('correct','corrupt','duplicate_payload','drop','reset_residue'):
                    replay=read(folder/mode/'replay.json')
                    check('native_replay:'+label+':'+mode,
                        replay['native']['compile_status']=='passed' and replay['native']['execution_status']=='completed'
                        and sha(replay['candidate'])==sha(candidate))
                    traces.append([{k:t[k] for k in ('cycle','rst','svalid','sready','sdata','mready')} for t in replay['trace']])
                check('identical_paired_input:'+label,all(t==traces[0] for t in traces))
    counts={}
    for method in protocol['methods']:
        subset=[r for r in results if r['method']==method]
        findings=[e for r in subset for e in r['evidence']['findings']]
        counts[method]=dict(queries=len(subset),event_classes=dict(Counter(f['kind'] for f in findings)),
            semantic_classes_by_kind={kind:len({f['semantic_key'] for f in findings if f['kind']==kind}) for kind in sorted({f['kind'] for f in findings})},
            independent_missed_gap_classes=len({key for r in subset for key in r['evidence']['obligation_gap_keys']}),
            unknown_queries=sum(r['evidence']['status']!='ok' for r in subset))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,per_method=counts,
        initial_candidate_qualified=False,initial_selection='First genuine model output, selected before any method run, not best-of failed candidates.',
        candidate_disagreement_effective=protocol['candidate_disagreement_eligible'],
        treatment_witness=read(BASE/'treatment_witness.json'),
        limitation='Replays policy state and physical artifact invariants; this is not an independent proof of the selection algorithm. Candidate false positives confound target attribution; zero verified missed gaps is not evidence of complete protection. First native model candidate deliberately kept unchanged for an honest negative experiment.')
    dump(OUT/'search_independent_audit.json',result)
    print(__import__('json').dumps(dict(passed=result['passed'],checks=len(checks),per_method=counts)))
    return result


if __name__=='__main__':run()
