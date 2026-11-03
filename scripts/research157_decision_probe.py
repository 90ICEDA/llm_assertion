"""Development-only exploration for the O/H decision audit; no calls/replay."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'deliverables/research145_stability_prepare_20261027_r02'
R=ROOT/'deliverables/research145_stability_real_20261027_r01'
def read(p):return json.loads(p.read_text())
for cell in read(P/'cells.json'):
    folder=R/'cells'/cell['id']/'shared/v0'
    d=read(folder/'native/decision.json')
    print(cell['id'], 'O',d['ordinary']['accepted'],'H',d['full_absolute'],'checks', [k for k,v in d['ordinary']['checks'].items() if not v])
    print(' counts',d['counts'],'lost',len(d['lost_detection_ids']),'fp',len(d['new_false_alarm_ids']))
    if not d['ordinary']['accepted']:
        c=read(folder/'model_call/candidate.json')
        print(' props',[(a['id'],a['property'],a['obligations']) for a in c['assertions']])
        for cohort,g in [('alignment',d['current_gate']['all_property_guard']),*d['all_property_guards'].items()]:
            print(' guard',cohort, {k:(len(v) if isinstance(v,list) else v) for k,v in g.items()})
            if g['false_alarms']:print(' first_fp',g['false_alarms'][0])
c=read(P/'cells.json')[0]
for cohort in ('alignment','search','history'):
    rec=read(ROOT/c['native']/cohort/'result.json')
    print('SCHEMA',cohort,list(rec),len(rec['ledger']),len(rec['reference']))
    print('ledger',rec['ledger'][0]);print('reference',rec['reference'][0])
print('inventory',[(r['id'],r['eligible'],r['exclusion_reasons']) for r in read(P/'candidate_matrix.json')])
for item in read(P/'candidate_matrix.json'):
    if item.get('measurements'):
        d=read(ROOT/item['measurements'][0]/'decision.json')
        print('ARCHIVED',item['id'],item['path'],d['ordinary']['accepted'],d['full_absolute'],d['counts'])
for ident in ['s14509_c05','s14519_c00']:
    d=read(R/'cells'/ident/'shared/v0/native/decision.json')
    from collections import Counter
    print('FP_BY_PROPERTY',ident,{k:dict(Counter(v['assertion'] for v in g['false_alarms'])) for k,g in d['all_property_guards'].items()})
