"""Posthoc actual-token checkpoints; immutable R194 evidence, no new models.

Selection reads only paid model usage and accepted state transitions. Held-out
grades are joined only AFTER checkpoint registration. Already-seen R194 test
inputs are reused for descriptive cost slices, never called a fresh holdout.
"""
import argparse
import copy
import hashlib
import html
import json
import statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'
CAM=D/'research194_campaign_execute_20261103_r01'
OUT=D/'research195_cost_sections_20261103_r01'
BUDGETS=(0,16384,32768,65536,131072,262144,524288)
ARMS=('S0_R0','S0_R1','S0_R2','S0_R3','S1_R1','S2_R1','S3_R1','S3_R3')
GROUPS={'R':{'R0':'S0_R0','R1':'S0_R1','R2':'S0_R2','R3':'S0_R3'},
        'S':{'S0':'S0_R1','S1':'S1_R1','S2':'S2_R1','S3':'S3_R1'},
        'A':{'A0':'S0_R1','A1':'S3_R1','A2':'S0_R3','A3':'S3_R3'}}

def read(path,default=None):return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def select_checkpoint(points,budget):
    eligible=[p for p in points if p['cumulative_tokens']<=budget]
    if not eligible:raise ValueError('missing_zero_checkpoint')
    return max(eligible,key=lambda p:p['round'])

def prepare(out=OUT):
    import research194_cases as cases
    out=Path(out)
    if (out/'registration.json').exists():raise ValueError('immutable_registration_exists')
    trajectories=[];bindings={};candidates={}
    for case in ('arbiter','counter','uart','ibex_flush'):
        for seed in (19407,19419):
            for arm in ARMS:
                folder=CAM/'base'/case/str(seed)/arm/'refinement'
                outcome=read(folder/'outcome.json');initial=read(folder/'initial.json',cases.get_case(case)['initial'])
                if not outcome or outcome['status']!='frozen':raise ValueError('unfinished_source')
                state=copy.deepcopy(initial);total=0;points=[];calls=0
                costs=read(folder/'cost_components.json',[]);rounds={x['round']:x for x in read(folder/'rounds.json',[])}
                def point(index,status):
                    h=digest(state);candidates.setdefault(case,{})[h]=copy.deepcopy(state)
                    return dict(round=index,status=status,candidate_sha256=h,cumulative_tokens=total,model_calls=calls,
                        model_cost_unknown=False,native_seconds=sum(x.get('native_seconds',0) or 0 for x in costs if x.get('round',0)<=index) if index else 0,
                        physical_execution_attempts=sum(x.get('native_execution_attempts',0) for x in costs if x.get('round',0)<=index) if index else 0)
                points.append(point(0,'initial'))
                for p in sorted(folder.glob('round*/model_call/result.json')):
                    r=int(p.parent.parent.name[5:]);record=read(p)
                    prompt,completion=record.get('prompt_tokens'),record.get('completion_tokens')
                    if not isinstance(prompt,int) or not isinstance(completion,int):raise ValueError('unknown_paid_token_usage')
                    calls+=record.get('model_calls',0);total+=prompt+completion
                    decision=rounds.get(r,{})
                    if decision.get('status')=='accepted':
                        proposal=p.parent.parent/'proposal.json';state=read(proposal)
                        if state is None:raise ValueError('accepted_without_saved_candidate')
                        bindings[str(proposal.relative_to(ROOT))]=sha(proposal)
                    points.append(point(r,decision.get('status','outer_interruption_after_call')))
                    bindings[str(p.relative_to(ROOT))]=sha(p)
                frozen=read(folder/'frozen.json')
                if digest(state)!=digest(frozen):raise ValueError('checkpoint_transition_mismatch:'+str(folder))
                for name in ('outcome.json','rounds.json','frozen.json','initial.json','cost_components.json'):
                    p=folder/name
                    if p.exists():bindings[str(p.relative_to(ROOT))]=sha(p)
                trajectories.append(dict(case_id=case,seed=seed,arm=arm,folder=str(folder.relative_to(ROOT)),points=points,
                    final_tokens=total,terminal_status=outcome.get('termination_reason',outcome.get('status')),
                    causal_comparison_eligible=outcome.get('causal_comparison_eligible'),provenance=outcome.get('provenance')))
    sections=[]
    for group,arms in GROUPS.items():
        for case in ('arbiter','counter','uart','ibex_flush'):
            for seed in (19407,19419):
                runs={label:next(t for t in trajectories if (t['case_id'],t['seed'],t['arm'])==(case,seed,arm)) for label,arm in arms.items()}
                common=min(t['final_tokens'] for t in runs.values())
                for label,budget in [(str(b),b) for b in BUDGETS]+[('minimum_observed_total',common)]:
                    sections.append(dict(group=group,case_id=case,seed=seed,budget_label=label,token_budget=budget,
                        common_observed_support=all(t['final_tokens']>=budget for t in runs.values()),
                        checkpoints={a:dict(select_checkpoint(t['points'],budget),arm=t['arm'],final_tokens=t['final_tokens'],
                            source_terminal_status=t['terminal_status'],source_provenance=t['provenance']) for a,t in runs.items()}))
    used={(s['case_id'],p['candidate_sha256']) for s in sections for p in s['checkpoints'].values()}
    candidates={case:{h:c for h,c in cc.items() if (case,h) in used} for case,cc in candidates.items()}
    reg=dict(version='research195-cost-sections-v1',posthoc=True,selection_reads_test_grades=False,model_calls=0,
        budgets=list(BUDGETS),groups=GROUPS,trajectories=trajectories,sections=sections,candidates=candidates,source_bindings=bindings,
        limitations=['This is completed-prefix actual prompt+completion token analysis, not a randomized rerun with matched wall time.',
            'Never use the response or candidate of a call that exceeds the token cut; token cost of rejected/truncated calls is included.',
            'Native seconds and physical executions are separately reported; shared baseline/reused first acquisitions are not recharged as new executions.',
            'The original independent inputs have already been inspected in R194; reuse is retrospective validation, not a fresh generalization test.',
            'A natural early stop is carried forward as its frozen checkpoint and explicitly flagged outside common observed support; it is not a successful completed budget.',
            'Minimum-observed-total cuts are data-derived from costs only, not from outcome quality; zero-call groups can have a zero common cut.'])
    bindings[str(Path(__file__).relative_to(ROOT))]=sha(__file__)
    for name in ('research194_cases.py','research194_ibex.py','research194_active_search.py','research194_metrics.py','research_native_runner.py'):
        bindings['scripts/'+name]=sha(ROOT/'scripts'/name)
    dump(out/'registration.json',reg);dump(out/'seal.json',dict(registration_sha256=sha(out/'registration.json')))
    print(json.dumps(dict(status='registered',trajectories=len(trajectories),sections=len(sections),unique_candidates={c:len(x) for c,x in candidates.items()},model_calls=0)))

def validate(out):
    reg=read(out/'registration.json')
    if sha(out/'registration.json')!=read(out/'seal.json')['registration_sha256']:raise ValueError('registration_changed')
    for p,h in reg['source_bindings'].items():
        if sha(ROOT/p)!=h:raise ValueError('source_changed:'+p)
    return reg

def evaluate(out=OUT):
    import fcntl
    import research194_cases as cases
    import research194_ibex as ibex
    from research194_active_search import combine_candidates,project_measurement
    from research194_metrics import temporal_detection
    out=Path(out);reg=validate(out)
    if (out/'evaluation_started.json').exists():raise ValueError('no_automatic_retry')
    dump(out/'evaluation_started.json',dict(registration_sha256=sha(out/'registration.json'),model_calls=0))
    plan=read(CAM/'independent/plan.json');ibex.register();index={};cost=[];bindings={}
    for case,versions in reg['candidates'].items():
        old=read(CAM/'independent'/case/'version_mapping.json');known=set(old['keys']);missing=[h for h in versions if h not in known]
        for h in known & set(versions):
            n=old['keys'].index(h)
            for fault in plan[case]['faults']:
                p=CAM/'independent'/case/fault/f'projection{n}.json';bindings[str(p.relative_to(ROOT))]=sha(p)
                index[case+'/'+h+'/'+fault]=dict(path=str(p.relative_to(ROOT)),reuse='identical_candidate_and_original_test_plan',sha256=sha(p))
        if not missing:continue
        combined,mapping=combine_candidates([versions[h] for h in missing])
        for fault in plan[case]['faults']:
            with (D/'research195_active_native_execution.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                m=cases.evaluate(case,combined,out/'native'/case/fault,queries=plan[case]['queries'],split='independent',fault=fault,_trusted_bundle=True)
            cost.append(dict(case_id=case,fault=fault,**m['cost']))
            for n,h in enumerate(missing):
                projected=project_measurement(m,versions[h],mapping,n);projected.update(temporal_detection(projected))
                p=out/'native'/case/fault/f'projection{n}.json';dump(p,projected)
                index[case+'/'+h+'/'+fault]=dict(path=str(p.relative_to(ROOT)),reuse=False,sha256=sha(p))
            dump(out/'physical_cost.json',cost);print('COST_SECTION_NATIVE',case,fault,len(missing),flush=True)
    dump(out/'projection_index.json',index);dump(out/'physical_cost.json',cost)
    dump(out/'evaluation_bindings.json',dict(original_plan_sha256=sha(CAM/'independent/plan.json'),reused_projection_bindings=bindings))
    validate(out)
    dump(out/'evaluation_outcome.json',dict(status='completed',model_calls=0,projection_units=len(index),
        new_native_executions=sum(x['native_execution_attempts'] for x in cost),new_native_compiles=sum(x['native_compile_attempts'] for x in cost)))

def analyze(out=OUT):
    from research194_refinement_independent_pairs import fine_fp
    out=Path(out);reg=validate(out)
    if read(out/'evaluation_outcome.json',{}).get('status')!='completed':raise ValueError('evaluation_incomplete')
    index=read(out/'projection_index.json');plan=read(CAM/'independent/plan.json');cache={};cells=[]
    def load(case,h,fault):
        k=case+'/'+h+'/'+fault;p=ROOT/index[k]['path']
        if k not in cache:
            if sha(p)!=index[k]['sha256']:raise ValueError('projection_changed')
            cache[k]=read(p)
        return cache[k]
    for s in reg['sections']:
        rows=[]
        for fault in plan[s['case_id']]['faults']:
            ms={a:load(s['case_id'],p['candidate_sha256'],fault) for a,p in s['checkpoints'].items()}
            targets=[set(m['targets']) for m in ms.values()]
            reasons=[]
            if any(not m['native_complete'] or not m['reference_complete'] or m['critical_unknown'] for m in ms.values()):reasons.append('unknown_or_incomplete')
            if not all(targets):reasons.append('unexposed')
            if any(t!=targets[0] for t in targets):reasons.append('target_mismatch')
            row=dict(fault=fault,eligible=not reasons,reasons=reasons,unknown_counts={a:len(m['critical_unknown']) for a,m in ms.items()})
            if not reasons:
                row['metrics']={a:dict(transaction_rate=len(m['transaction_detected_ids'])/len(m['targets']),timely_rate=len(m['detected_ids'])/len(m['targets']),legal_fp_contexts=len(fine_fp(m))) for a,m in ms.items()}
            rows.append(row)
        valid=[r for r in rows if r['eligible']]
        cell=dict(**s,faults=rows,eligible=bool(valid),complete_fault_population=len(valid)==len(rows))
        if valid:cell['mean_metrics']={a:{k:statistics.mean(r['metrics'][a][k] for r in valid) for k in valid[0]['metrics'][a]} for a in s['checkpoints']}
        cells.append(cell)
    summary=[]
    for group in GROUPS:
        for b in [str(x) for x in BUDGETS]+['minimum_observed_total']:
            selected=[c for c in cells if c['group']==group and c['budget_label']==b]
            parents=[]
            for case in ('arbiter','counter','uart','ibex_flush'):
                cc=[c for c in selected if c['case_id']==case and c['eligible']]
                if len(cc)==2:
                    parents.append(dict(case_id=case,common_observed_support=all(c['common_observed_support'] for c in cc),
                        means={a:{k:statistics.mean(c['mean_metrics'][a][k] for c in cc) for k in cc[0]['mean_metrics'][a]} for a in GROUPS[group]}))
            for arm in GROUPS[group]:
                summary.append(dict(group=group,budget=b,arm=arm,paired_parents=len(parents),supported_parents=sum(p['common_observed_support'] for p in parents),
                    parent_macro_transaction_rate=statistics.mean(p['means'][arm]['transaction_rate'] for p in parents) if parents else None,
                    parent_macro_timely_rate=statistics.mean(p['means'][arm]['timely_rate'] for p in parents) if parents else None,
                    parent_macro_legal_fp_contexts=statistics.mean(p['means'][arm]['legal_fp_contexts'] for p in parents) if parents else None))
    dump(out/'analysis.json',dict(status='completed',cells=cells,summary=summary,model_calls=0,
        qualification='Equal eligible fault weights, two seeds per parent, then equal parent weights. Unknown faults excluded identically across arms and listed. All tables retain early stops; supported_parents identifies common observed token support. No full acceptance claim.',limitations=reg['limitations']))
    body=['<h1>实际模型 tokens 共同成本截面</h1><p>只分析已完成调用的前缀；超预算调用的响应和修改不进入该截面。无新模型调用。原194验收输入已被查看，本分析是回顾性复核，不是新的独立泛化实验。</p>']
    body+=['<p>'+html.escape(x)+'</p>' for x in reg['limitations']]
    for group in GROUPS:
        rows=[r for r in summary if r['group']==group]
        body.append('<h2>'+group+'</h2><div class="scroll"><table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in rows[0])+'</tr>')
        body+=['<tr>'+''.join('<td>'+html.escape(str(round(v,5) if isinstance(v,float) else v))+'</td>' for v in r.values())+'</tr>' for r in rows]
        body.append('</table></div>')
    body.append('<p><a href="analysis.json">逐截面、故障、未知与实际花费</a> · <a href="registration.json">在验收映射前封存的成本选择规则</a> · <a href="physical_cost.json">新增原生执行成本</a></p>')
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>REGuard共同成本分析</title><style>body{font:15px/1.6 system-ui;max-width:1300px;margin:30px auto;padding:20px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px}.scroll{overflow:auto}</style>'+''.join(body),encoding='utf-8')
    print(json.dumps(dict(status='completed',sections=len(cells),summary_rows=len(summary))))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','evaluate','analyze']);p.add_argument('--out',type=Path,default=OUT)
    a=p.parse_args();globals()[a.action](a.out)
