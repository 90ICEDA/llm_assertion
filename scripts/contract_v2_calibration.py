"""Named engineering controls validate the harness and legal-variant behavior.
These never enter the model pool, method selection or parent success statistics.
"""
from run_contract_v2 import OUT,read,dump,definition,run,rel,sha,stamp
from contract_v2_spec import adjudicate
from repair_contract_cases import controlled_candidate
from contract_v2_hidden import custom_run

records=[]
for k in ['onehot','fifo']:
    d=definition(k);c=controlled_candidate(k);rows=read(OUT/'frozen'/k/'hidden_transactions.json')
    for variant in ['correct','buggy']:
        records.append(run(d,c,None,'calibration/engineering_control',variant,rows=rows))
    if k=='onehot':records.append(run(d,c,None,'calibration/legal_variant',rows=rows,param={'StrictCheck':0}))
    else:
        control=next(x for x in read(OUT/'independent_plan/plan.json')['controls'] if x['case']=='fifo')
        records.append(custom_run(d,c,rows,'calibration/component_present',control))
output=[]
for r in records:
    output.append({'run':r['run_id'],'status':r['status'],'case':r['case'],'candidate':r['candidates'],'purpose':'engineering_harness_calibration_only_not_a_natural_or_method_candidate','independent_labels':r.get('contract_views')})
dump(OUT/'calibration_results.json',output)
print('Calibration records',len(records),flush=True)
