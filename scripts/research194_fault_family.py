"""Preregistered three-policy artificial fault-family native experiment.

Real project RTL, artificial faults: seeded-region is NOT a historical fix region.
Independent operators/sites are committed but never executed by this command.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import time
import research194_cases as c


def plans(seed=19407):
    result={}
    for case in ('arbiter','counter','uart'):
        dev=copy.deepcopy([f for f in c.FAULTS[case] if f['split']=='development'])
        reserved=[f for f in c.FAULTS[case] if f['split']=='independent']
        primary=dev[0];src=(c.ROOT/c.CONFIG[case]['sources'][primary.get('file',0)]).read_text()
        sites=[]
        for match in re.finditer(r'(?m)^(\s*(?:assign\s+)?[A-Za-z_]\w*(?:\[[^\]\n]+\])?\s*(?:<=|=(?!=))\s*)([^;\n]+);',src):
            line=match.group(0)
            if any(f['search'] in line or line.strip() in f['search'] for f in reserved):continue
            if any(t in match.group(2) for t in ('"','//','`')):continue
            sites.append((line,match.group(1)+'('+match.group(2)+") ^ 1'b1;",src[:match.start()].count('\n')+1))
        rng=random.Random(str(seed)+'/'+case);selected=rng.sample(sites,3)
        randoms=[dict(id='random_'+str(i),operator='xor_assignment_lsb',site='line_'+str(line),search=s,replace=r,file=primary.get('file',0),split='development',obligation='unassigned_before_oracle') for i,(s,r,line) in enumerate(selected)]
        region=[]
        replacements={
          'arbiter':['    grant_valid_reg <= grant_valid_reg;',"    grant_valid_reg <= 1'b0;",'    grant_valid_reg <= !grant_valid_next;'],
          'counter':['counter_d = counter_q + delta_i + delta_i;','counter_d = counter_q;','counter_d = counter_q + delta_i + delta_i + delta_i;'],
          'uart':["{1'b0,baud_div_q} + 5'h2","{1'b0,baud_div_q} + 5'h0","{1'b0,baud_div_q} + 5'h3"]}[case]
        for i,replacement in enumerate(replacements):
            f=copy.deepcopy(primary);f.update(id='region_'+str(i),replace=replacement);region.append(f)
        result[case]=dict(random=randoms,seeded_region=region,obligation_guided=dev,
          independent_reserved=reserved,random_candidate_sites=len(sites),random_selection='uniform without replacement over assignment statements excluding reserved independent sites',
          split_rule='Independent sites and mutation operators are excluded from development selection. Test definitions are audit-only, not passed to model.',
          source_sha256={s:hashlib.sha256((c.ROOT/s).read_bytes()).hexdigest() for s in c.CONFIG[case]['sources']})
    return result


def run(out,seed=19407):
    out.mkdir(parents=True,exist_ok=False);plan=plans(seed)
    protocol=dict(seed=seed,model_calls=0,cohort='artificial obligation faults on real RTL',historical_repair_region=False,
      strategy_budget=dict(mutants_per_case=3,logical_queries_per_mutant=1,native_compile_attempts_per_mutant=2,baseline_correct_rerun_each_mutant=True),
      caveat='Equal actual compile-attempt budget; execution counts/time can differ after compilation failure. Runtime costs are measured, not assumed equal.',
      independent_test_executed=False,plans=plan,created_unix=time.time(),source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    c.dump(out/'preregistration.json',protocol)
    candidates={case:c.get_case(case)['initial'] for case in plan};c.dump(out/'frozen_initial.json',candidates)
    freeze=c.digest(candidates);rows=[];feedback=[]
    for case,p in plan.items():
        pool=c.query_pool(case,'development',seed)
        query=dict(pool[0],id=case+'/fault_all_development',family='all_development',rows=[r for q in pool for r in q['rows']],semantic_key=c.digest([q['semantic_key'] for q in pool]))
        for strategy in ('random','seeded_region','obligation_guided'):
            for i,f in enumerate(p[strategy]):
                fault=copy.deepcopy(f);fault['id']='family_'+strategy+'_'+str(i)
                c.FAULTS[case].append(fault);folder=out/case/strategy/str(i)
                m=c.evaluate(case,candidates[case],folder,queries=[query],fault=fault['id'])
                targets=set(m['targets']);detected=set(m['detected_ids']);confirmed=[e for e in m['evidence'] if e['status']=='confirmed' and e['label']=='violation' and e.get('counted_target')]
                gap_obligations=sorted({e['obligation'] for e in confirmed if e['id'] not in detected})
                # Reference reachability is independent of SVA alarm attribution.
                refs=[j for j in m['executions'] if j['variant']!='correct'];correct=[j for j in m['executions'] if j['variant']=='correct']
                legal_correct=all(not j['reference']['unknown'] and all(x['passed'] for x in j['reference']['checks']) for j in correct)
                valid=m['native_complete'] and legal_correct and any(not x['passed'] for j in refs for x in j['reference']['checks'])
                row=dict(case=case,parent_bug=m['parent_bug'],strategy=strategy,index=i,mutant=fault,
                  valid_reachable_fault=valid,compiled=m['native_complete'],reference_complete=m['reference_complete'],
                  no_exposure=m['native_complete'] and legal_correct and not targets,
                  target_transactions=len(m['target_transaction_ids']),target_obligation_transactions=len(targets),detected=len(detected),
                  gap_obligations=gap_obligations,unclassified_alarms=len(m['critical_unknown']),false_positives=len(m['false_positives']),
                  cost=m['cost'],measurement=str(folder/'measurement.json'),frozen_candidate_sha256=m['candidate_sha256'])
                rows.append(row)
                if valid:feedback.append(dict(case=case,mutant_id=fault['id'],measurement=row['measurement'],evidence=[e for e in confirmed if e['id'] not in detected],visibility='development_only'))
                c.dump(out/'results.json',rows);c.dump(out/'development_feedback.json',feedback)
                print(json.dumps({k:row[k] for k in ('case','strategy','index','valid_reachable_fault','detected','gap_obligations','cost')}),flush=True)
    summary=[]
    for case in plan:
        for strategy in ('random','seeded_region','obligation_guided'):
            rr=[r for r in rows if r['case']==case and r['strategy']==strategy]
            summary.append(dict(case=case,strategy=strategy,mutants=len(rr),valid=sum(r['valid_reachable_fault'] for r in rr),
              gap_obligations=sorted({o for r in rr for o in r['gap_obligations']}),unknown=sum(r['unclassified_alarms'] for r in rr),
              compile_attempts=sum(r['cost']['native_compile_attempts'] for r in rr),execution_attempts=sum(r['cost']['native_execution_attempts'] for r in rr),
              native_seconds=sum(r['cost']['native_seconds'] for r in rr)))
    c.dump(out/'summary.json',dict(rows=summary,frozen_candidates_sha256=freeze,independent_test_executed=False,model_calls=0,
      next_stage='Freeze baseline and refinement candidates before evaluating reserved operators/sites; development mutant detections are not generalization results.'))
    return summary


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--seed',type=int,default=19407)
    a=ap.parse_args();run(a.out.resolve(),a.seed)
