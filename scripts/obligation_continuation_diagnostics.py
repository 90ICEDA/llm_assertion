"""All-cell diagnosis/minimization, isolated from model and formal budgets."""
import argparse
import collections
import copy
import json
from pathlib import Path
import shutil
import subprocess
import time
import obligation_continuation as cont
from obligation_continuation import x, iso, PRIOR


def minimize():
    out=x.OUT/'minimization';out.mkdir(exist_ok=False)
    cont.configure()
    ledger=x.read(PRIOR/'diagnostics/problem_ledger.json')
    mapping=[];cache={};physical=[]
    for record in ledger:
        if not record.get('reproduction'):continue
        folder=x.ROOT/record['reproduction'];d=x.read(folder/'definition.json');cs=x.read(folder/'candidates.json')
        rows=x.read(folder/'input.json');raw=x.read(folder/'result.json');variant=raw['variant']
        original_a=x.read(folder/'adjudication.json')
        selected=next((j,e) for j,group in enumerate(original_a['evidence']) for e in group
                      if e['kind'] in ('miss','false_positive') and e['cycle']==record['witness_cycle'])
        j,target=selected;c=cs[j]
        identity=[(z['obligation'],z['trigger_cycle'],z['branch']) for z in target['obligations']]
        original_rows=copy.deepcopy(rows)
        for i,r in enumerate(rows):r['source_sample']=i
        calls=[];count=0
        def attempt(trial):
            nonlocal count
            count+=1;trial=copy.deepcopy(trial)
            for i,r in enumerate(trial):r['cycle']=i;r['stimulus_id']=f"original_sample:{r['source_sample']}"
            ident=record['record_id']+'/'+str(count)
            x.append(out/'attempts.jsonl',dict(id=ident,input_sha256=x.digest(trial),status='submitted'))
            key=x.digest([d,x.sha(folder/'rtl.v'),c,trial])
            start=time.perf_counter()
            if key in cache:
                result=dict(cache[key],cache_hit=True,id=ident);calls.append(result);x.append(out/'queries.jsonl',result)
                return result['preserves_target'],result
            errors=x.check_inputs(d,trial)
            result=dict(id=ident,cache_hit=False,preserves_target=False,compile_attempts=0,simulation_attempts=0,
                        input_sha256=x.digest(trial),samples=len(trial),errors=errors,status='invalid_input' if errors else 'pending')
            if not errors:
                x.engine.sources=lambda definition:(folder/'rtl.v',folder/'rtl.v')
                r=x.engine.execute_run(d,trial,[c],'minimization/'+ident,variant)
                result.update(run=r['run_id'],status=r['status'],compile_attempts=1,simulation_attempts=int(r['simulate'] is not None))
                if r['status']=='ok':
                    dest=x.ROOT/r['run_id'];a=x.adjudicate_folder(dest,d);x.dump(dest/'adjudication.json',a)
                    for ev in a.get('evidence',[[]])[0]:
                        if ev['kind']!=target['kind'] or trial[ev['cycle']]['source_sample']!=target['cycle']:continue
                        got=[(z['obligation'],trial[z['trigger_cycle']]['source_sample'],z['branch']) for z in ev['obligations']]
                        if got==identity:result.update(preserves_target=True,witness=ev);break
            result['wall_seconds']=time.perf_counter()-start;cache[key]=dict(result);physical.append(result)
            calls.append(result);x.append(out/'queries.jsonl',result)
            return result['preserves_target'],result
        ok,kept=attempt(rows);assert ok,record['record_id']
        anchors={0,1,target['cycle'],*(v[1] for v in identity)}
        # Greedy chunk deletion followed by a complete single-sample pass.
        size=max(1,(len(rows)-2)//2)
        while size>=1 and count<256:
            changed=False
            for i in range(2,len(rows),size):
                remove=rows[i:i+size]
                if any(r['source_sample'] in anchors for r in remove):continue
                ok,z=attempt(rows[:i]+rows[i+size:])
                if ok:rows=rows[:i]+rows[i+size:];kept=z;changed=True;break
                if count>=256:break
            if not changed:size//=2
        final_pass_complete=size==0
        dest=out/record['record_id'];x.dump(dest/'original_input.json',original_rows);x.dump(dest/'minimal_input.json',rows)
        result=dict(record_id=record['record_id'],case=record['case'],original_status=record['original_status'],original_run=record['reproduction'],
            candidate_id=c['id'],candidate_sha256=x.digest(c),kind=target['kind'],transaction_identity=identity,
            original_samples=len(original_rows),minimal_samples=len(rows),minimal_run=kept['run'],
            query_attempts=len(calls),cache_hits=sum(z['cache_hit'] for z in calls),
            physical_compiles=sum(z['compile_attempts'] for z in calls if not z['cache_hit']),
            standard='single-sample deletion minimal with initial two reset samples, original witness and trigger identity fixed; input values unchanged',
            status='locally_minimal' if final_pass_complete else 'budget_minimal_256_attempts',reproduce='sh '+kept['run']+'/reproduce.sh')
        x.dump(dest/'result.json',result);mapping.append(result)
        print('MINIMIZED',record['record_id'],len(original_rows),'->',len(rows),result['status'],flush=True)
    x.dump(out/'index.json',mapping)
    x.dump(out/'summary.json',dict(records=len(mapping),locally_minimal=sum(r['status']=='locally_minimal' for r in mapping),
        attempts=sum(r['query_attempts'] for r in mapping),physical_queries=len(physical),cache_hits=sum(r['cache_hits'] for r in mapping),
        physical_compiles=sum(r['compile_attempts'] for r in physical),physical_simulations=sum(r['simulation_attempts'] for r in physical),
        input_value_minimization=False,all_original_ids_preserved=True))


def unresolved():
    out=x.OUT/'unresolved_diagnostics';out.mkdir(exist_ok=False);cont.configure()
    ledger=x.read(PRIOR/'diagnostics/problem_ledger.json');unknown=[r for r in ledger if not r.get('reproduction')]
    results=[]
    for k in ('filter','intr'):
        rr=[r for r in unknown if r['case']==k];d=x.read(x.OUT/'frozen'/k/'definition.json')
        cs=[dict(r['candidate'],id=r['record_id']) for r in rr]
        for i in range(12):
            rows=x.policy.ordinary(d,923071+i*263)
            if k=='intr':
                for t,r in enumerate(rows):
                    r[d['rst']]=int(t>=2 and t!=15);r['event_intr_i']=int(t in (2,3,9,17))
                    r['reg2hw_intr_enable_q_i']=int(t in (2,3,4,8,9,10,17,18))
                    r['sw_clear']=int(t in (7,13));r['reg2hw_intr_test_q_i']=int(i%2==1 and t==11);r['reg2hw_intr_test_qe_i']=int(t==11)
            # Preserve unsupported expressions for an actual compiler diagnostic.
            for variant in ('correct','buggy'):
                raw=x.engine.execute_run(d,rows,cs,f'unresolved/{k}/{i}',variant)
                row=dict(case=k,scenario=i,variant=variant,run=raw['run_id'],status=raw['status'],covered_record_ids=[r['record_id'] for r in rr])
                if raw['status']=='ok':
                    dest=x.ROOT/raw['run_id'];a=x.adjudicate_folder(dest,d);x.dump(dest/'adjudication.json',a)
                    oracle=x.read(dest/'independent_reference.json');row['antecedent_hits']={c['id']:c['trigger_count'] for c in raw['candidates']}
                    row['conditional_violations']=dict(collections.Counter(c['obligation'] for e in oracle['events'] for c in e['checks'] if not c['passed']))
                    row['conditional_obligations_reached']=dict(collections.Counter(c['obligation'] for e in oracle['events'] for c in e['checks']))
                results.append(row);x.append(out/'queries.jsonl',row)
        if k=='filter':
            # Separate port-only reachability execution, not a repaired candidate.
            qa=dict(id='reachability_only',antecedent='1',consequent='1',delay=0,provenance='manual_tool_QA_not_candidate',authorized_history_depth=0)
            for i in range(4):
                q=iso.evaluate(d,x.policy.guided(d,923499+i,i),[qa],f'unresolved_reachability/filter/{i}')
                x.append(out/'reachability_queries.jsonl',q)
    mapping=[]
    for r in unknown:
        actual=[q for q in results if r['record_id'] in q['covered_record_ids']]
        mapping.append(dict(record_id=r['record_id'],case=r['case'],original_status=r['original_status'],actual_shared_executions=len(actual),
            runs=[q['run'] for q in actual],status='execution_unsupported' if r['case']=='filter' else 'spec_unresolved_conditional_experiment_completed',
            reachable_hits=sum(q.get('antecedent_hits',{}).get(r['record_id'],0) for q in actual),
            cause='dotted/internal expression is outside candidate language; no semantic blame' if r['case']=='filter' else 'both mask sampling interpretations tested; upstream registered output does not override conflicting artificial case text',
            additional_model_calls=0))
    x.dump(out/'records.json',mapping)
    x.dump(out/'summary.json',dict(records=len(mapping),shared_executions=len(results),conditional_not_definitive=True,
        filter_manual_controls=4,record_mapping_complete=len(mapping)==9))


def stat_search():
    out=x.OUT/'stat_search_v2';out.mkdir(exist_ok=False);cont.configure()
    d=x.read(x.OUT/'frozen/stat/definition.json');cs=x.read(x.OUT/'frozen/stat/candidates.json')['candidates']
    results=[]
    for seed in (3113,3119,3121):
        for method in ('ordinary','disagreement','obligation'):
            incumbent=None;best=-1
            for step in range(12):
                s=seed+step*1009
                if method=='ordinary':rows=x.policy.ordinary(d,s)
                elif method=='disagreement':rows=x.policy.disagreement(d,s,incumbent if step%3 else None)
                else:rows=x.policy.guided(d,s,step)
                q=iso.evaluate(d,rows,cs,f'stat_search_v2/{seed}/{method}/{step}')
                q.update(case='stat',method=method,seed=seed,step=step);results.append(q);x.append(out/'queries.jsonl',q)
                if method=='disagreement' and q['disagreement_score']>best:best=q['disagreement_score'];incumbent=rows
    summary=[dict(method=m,queries=sum(q['method']==m for q in results),gaps=sorted(iso.gaps([q for q in results if q['method']==m]))) for m in ('ordinary','disagreement','obligation')]
    x.dump(out/'summary.json',dict(scope='only affected parent; new corrected-control RTL, same candidates/methods/seeds/budget; original 13/13/8 retained',results=summary))


def specs_tools():
    out=x.OUT/'specs_tools';out.mkdir(exist_ok=False);cont.configure()
    tools={n:shutil.which(n) for n in ('iverilog','vvp','yosys','verilator','slang','sv2v','jg','jaspergold','vcs','vsim','xrun')}
    x.dump(out/'tool_inventory.json',tools)
    for flags,name in [([], 'iverilog_native'),(['-gsupported-assertions'],'iverilog_supported_subset')]:
        f=out/name;f.mkdir();shutil.copyfile(PRIOR/'baseline/native_sva/probe.sv',f/'probe.sv')
        result=x.command(['iverilog','-g2012',*flags,'-s','tb','-o','probe.out','probe.sv'],f,'compile')
        x.dump(f/'verdict.json',dict(native_execution_supported=result['status']=='ok',result=result,
            warning='A successful ignored assertion is not native execution; inspect stderr before accepting capability.'))
    x.qualify.OUT=out/'checker_qualification';x.qualify.qualify()
    import obligation_checker_async as async_checker
    async_checker.qualify(x.OUT.name)
    sources=[x.ROOT/'rtl_cases_real_scale120/case135_prim_intr_enable_mask_ignored/STIMULUS_NOTES.md',
        x.ROOT/'external/opentitan/hw/ip/prim/rtl/prim_intr_hw.sv',
        x.ROOT/'rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/spec.md',
        x.ROOT/'rtl_cases_real_scale210_independent_next/case510_cc_spill_register_flush_push_priority/tb.v',
        x.ROOT/'external/common_cells/src/cc_spill_register_flushable.sv']
    provenance=[]
    for p in sources:
        if p.exists():
            f=out/'sources'/p.name;f.parent.mkdir(exist_ok=True);shutil.copyfile(p,f)
            provenance.append(dict(path=x.rel(p),sha256=x.sha(p),snapshot=x.rel(f)))
    history=x.command(['git','log','-5','--oneline'],out,'git_history',15)
    spec=dict(local_sources=provenance,git_history=history,
        web_sources=[dict(url='https://opentitan.org/book/doc/contributing/hw/comportability/index.html',finding='Documented event interrupt timing includes an output-flop-enabled waveform; supports registered interpretation but does not rewrite the artificial case requirement.'),
            dict(url='https://github.com/pulp-platform/common_cells/blob/master/src/cc_spill_register_flushable.sv',finding='Upstream interface has ready/valid and forbids concurrent flush and valid; it is not the same simplified push/flush case and cannot settle raw invalid payload semantics.')],
        formal_status='spill payload and artificial intr sampling remain unresolved unless user supplies clarification',
        pending_questions=['When valid_o=0 must data_o be zero or is it unconstrained?','Does configured intr use current enable or one-sample delayed enable under pre-NBA observation?'])
    x.dump(out/'specification_review.json',spec)
    d=x.read(x.OUT/'frozen/spill/definition.json');cs=x.read(x.OUT/'frozen/spill/candidates.json')['candidates']
    conditions=[]
    for i,value in enumerate((0,1,165,255)):
        rows=x.policy.guided(d,74311+i,0)
        for r in rows:r['data_i']=value
        for alternate in (False,True):
            raw=x.engine.execute_run(d,rows,cs,f'conditional_spill/{i}/{int(alternate)}','correct',invalid_bus_variant=alternate)
            f=x.ROOT/raw['run_id'];a=x.adjudicate_folder(f,d);x.dump(f/'adjudication.json',a);tr=x.read(f/'trace.json')
            conditions.append(dict(value=value,invalid_payload_alternate=alternate,run=raw['run_id'],
                common_valid_violations=sum(not c['passed'] for e in x.read(f/'independent_reference.json')['events'] for c in e['checks']),
                raw_zero_interpretation_violations=[r['cycle'] for r in tr if r[d['rst']] and not r['valid_o'] and r['data_o']!=0],
                status='conditional_only'))
    x.dump(out/'spill_conditional_results.json',conditions)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default=cont.NAME);p.add_argument('action',choices=['minimize','unresolved','stat_search','specs_tools'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
