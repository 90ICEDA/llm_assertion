"""Development-only qualification of the original flush fix and local repair."""
import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import research194_ibex as ibex


def run(out):
    c=ibex.register();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    initial=ibex.get_case()['initial'];broadened=copy.deepcopy(initial)
    broadened[0]['antecedent']='flush'
    queries=ibex.query_pool()
    protocol=dict(queries=queries,initial=initial,handwritten_local_control=broadened,
                  model_calls=0,split='development',source_hashes=ibex.get_case()['provenance']['sources'],
                  scope='Original upstream flush sub-fix at compressed decoder; no independent inputs or mutants executed.')
    c.dump(out/'protocol.json',protocol)
    def one(pair):
        name,candidate=pair
        result=ibex.evaluate('ibex',candidate,out/name,queries)
        return dict(name=name,targets=len(result['targets']),detected=len(result['detected_ids']),
                    fp=len(result['false_positives']),unknown=len(result['critical_unknown']),cost=result['cost'],
                    exposed_obligations=sorted({e['obligation'] for e in result['evidence'] if e['status']=='confirmed' and e['label']=='violation'}))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(one,[('initial',initial),('local_control',broadened)]))
    c.dump(out/'results.json',results)
    c.dump(out/'outcome.json',dict(status='qualified' if all(r['unknown']==0 and r['fp']==0 for r in results) else 'unknown_or_failed',
        model_calls=0,native_compiles=sum(r['cost']['native_compile_attempts'] for r in results),
        no_model_improvement_claim=True,no_independent_test_access=True))
    print(results)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);run(ap.parse_args().out)
