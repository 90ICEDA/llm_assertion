"""Qualify two declared Ibex development faults; never access held-out faults."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import research194_ibex as ibex


def run(out):
    c=ibex.register();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    queries={q['family']:q for q in ibex.query_pool()}
    plan=[('dev_ready_gate','flush_stall'),('dev_stall_advance','normal')]
    initial=ibex.get_case()['initial']
    c.dump(out/'protocol.json',dict(plan=plan,initial=initial,split='development',model_calls=0,
        no_independent_access=True,source_sha256=ibex.get_case()['provenance']['sources']))
    def one(item):
        fault,family=item
        m=ibex.evaluate('ibex_flush',initial,out/fault,[queries[family]],fault=fault)
        result=dict(case_id='ibex_flush',fault=fault,query=queries[family],measurement=str(out/fault/'measurement.json'),
            valid_reachable=bool(m['targets']) and m['native_complete'] and m['reference_complete'] and not m['critical_unknown'],
            targets=len(m['targets']),detected=len(m['detected_ids']),unknown=len(m['critical_unknown']),cost=m['cost'])
        c.dump(out/fault/'qualification.json',result);return result
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,plan))
    c.dump(out/'results.json',results);print(results,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);run(p.parse_args().out)
