"""Native adapter qualification with explicitly handwritten specification controls."""
import argparse
import copy
import json
from pathlib import Path
import research194_cases as c


def run(out):
    out.mkdir(parents=True,exist_ok=False);results=[]
    for case in c.list_cases():
        props=[]
        for prefix,group in [('initial',c.get_case(case)['initial']),('control',c.controls(case))]:
            for a in group:
                a=copy.deepcopy(a);a['label']=prefix+'_'+a['label'];props.append(a)
        pool=c.query_pool(case)
        query=dict(pool[0],id=case+'/all_development',family='all_development',
            rows=[r for q in pool for r in q['rows']],semantic_key=c.digest([q['semantic_key'] for q in pool]))
        m=c.evaluate(case,props,out/case,queries=[query])
        result=dict(case=case,native_complete=m['native_complete'],reference_complete=m['reference_complete'],
            targets=len(m['targets']),transactions=len(m['target_transaction_ids']),detected=len(m['detected_ids']),
            false_positives=len(m['false_positives']),unknown=len(m['critical_unknown']),cost=m['cost'],
            handwritten_fixture=True,model_calls=0)
        results.append(result);c.dump(out/'summary.json',results);print(json.dumps(result),flush=True)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();run(a.out.resolve())
