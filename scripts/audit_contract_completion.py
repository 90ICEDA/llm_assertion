"""Read-only audit of sealed experiments; replays run in separate copied directories."""
import collections, hashlib, json, shutil, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'deliverables/repair_contract_20261009'
OUT = ROOT / 'deliverables/repair_contract_completion_audit_20261009'
OUT.mkdir(parents=True, exist_ok=True)
def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(name, value): (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

manifest = read(SRC/'artifact_manifest.json')
mismatches=[]
for i,(name,expected) in enumerate(manifest.items(),1):
    p=ROOT/name
    if not p.exists() or digest(p)!=expected: mismatches.append(name)
    if i%10000==0: print('Hash checked',i,flush=True)
write('manifest_check.json',{'checked':len(manifest),'mismatches':mismatches})

runs=read(SRC/'all_runs.json'); parents=read(SRC/'parent_results.json')
budgets=read(SRC/'budgets.json'); methods=read(SRC/'method_freeze.json')['rows']
byid={r['run_id']:r for r in runs}
facts={'sealed_hashes_checked':len(manifest),'sealed_hash_mismatches':mismatches,
       'runs':len(runs),'run_status':dict(collections.Counter(r['status'] for r in runs)),
       'parent_count':len({p['parent_bug_id'] for p in parents}),
       'parent_cells':len(parents),'parent_status':dict(collections.Counter(p['status'] for p in parents)),
       'summary_matches_run_count':read(SRC/'summary.json')['rtl_runs']==len(runs)}
facts['methods']={arm:{'pass':[p['case'] for p in parents if p['method']==arm and p['complete_pass'] is True],
                       'unknown':[p['case'] for p in parents if p['method']==arm and p['complete_pass'] is None]}
                  for arm in sorted({p['method'] for p in parents})}
costs=[]
for b in budgets:
    rr=[byid[x] for x in b['run_ids']]
    costs.append({k:b[k] for k in ['case','method','logical_generation_calls','prompt_tokens','completion_tokens','actual_candidate_rtl_checks','additional_history_bits_permission']}|
                 {'executed_simulations':sum(r.get('simulate') is not None for r in rr),
                  'successful_simulations':sum(r['status']=='ok' for r in rr)})
write('budget_recount.json',costs)
facts['charged_checks_range']=sorted({x['actual_candidate_rtl_checks'] for x in costs})
facts['executed_simulations_range']=sorted({x['executed_simulations'] for x in costs})

mixed=[]
for p in parents:
    if p['false_positive_cycles'] and p['missed_cycles']: mixed.append({'case':p['case'],'method':p['method'],'reported_status':p['status'],'fp':p['false_positive_cycles'],'miss':p['missed_cycles']})
facts['parents_with_both_fp_and_miss']=mixed
facts['slots_06_07']=[{'parent':p['parent_bug_id'],'status':p['status'],'evidence_count':len(p['evidence'])}
    for p in read(SRC/'collision_pairs.json') if {p['a'],p['b']}=={'slot_06','slot_07'}]

prefix_issues=[]; witness_count=0
for item in read(SRC/'history_refinement.json'):
    for level in item['levels']:
        for w in level['witnesses']:
            witness_count+=1; a=w['legal'];r=byid[a['run']]
            trace=read(ROOT/r['trace']);definition=read(ROOT/r['run_id']/'definition.json')
            reset_cycles=[t['cycle'] for t in trace if t['cycle']<=a['cycle'] and not t[definition['rst']]]
            reset_cycle=max(reset_cycles,default=-1)
            earlier=[c for c in r['obligation_violation_cycles'] if reset_cycle<c<a['cycle']]
            if earlier:prefix_issues.append({'parent':item['parent_bug_id'],'depth':level['history_depth'],
                                           'legal_sample':a,'earlier_violation_cycles':earlier})
write('observation_prefix_audit.json',{'witnesses':witness_count,'legal_sample_with_earlier_violation':prefix_issues,
    'meaning':'These labels prove only current-cycle compliance, not legality of the whole execution prefix.'})
facts['observation_witnesses']=witness_count
facts['legal_sample_witnesses_with_earlier_violation']=len(prefix_issues)

prompt_exposure=[]
for p in (SRC/'model_calls/repair/filter').glob('*/*/prompt.txt'):
    if '"second_new_sample_dbg"' in p.read_text(): prompt_exposure.append(str(p.relative_to(ROOT)))
facts['filter_prompts_containing_unallowed_debug_signal']=prompt_exposure

unsupported_accepted=[]
for m in methods:
    for step in m.get('rounds',[]):
        if step.get('accepted') and step.get('score',{}).get('unknown'):
            unsupported_accepted.append({'case':m['case'],'method':m['arm'],'step':step['step'],'score':step['score']})
facts['accepted_rounds_with_unknown_checks']=unsupported_accepted

window=[]
for item in read(SRC/'window_results.json'):
    rr=[byid[x] for x in item['runs']];rows=[read(ROOT/r['input']) for r in rr]
    strip=lambda x:{k:v for k,v in x.items() if k not in ['cycle','stimulus_id']}
    window.append({'parent':item['parent_bug_id'],'variant':item['variant'],
                   'same_prefix':all([strip(x) for x in q[:24]]==[strip(x) for x in rows[0]] for q in rows[1:]),
                   'accepted_transactions':[r['accepted_transactions'] for r in rr],
                   'ranking_changed':item['ranking_changed']})
write('window_prefix_audit.json',window)

replays=[]
for case in ['onehot','filter','fifo']:
    folder=SRC/'runs/e12/held_24'/case/'correct'; target=OUT/'replays'/case
    target.mkdir(parents=True,exist_ok=True)
    for name in ['rtl.v','checker_tb.sv','input.json','candidates.json','assertions.sva']:
        shutil.copy2(folder/name,target/name)
    script=(folder/'reproduce.sh').read_text().replace(str(folder),str(target))
    (target/'reproduce.sh').write_text(script)
    start=time.perf_counter()
    try:
        p=subprocess.run(['sh',str(target/'reproduce.sh')],cwd=target,capture_output=True,text=True,timeout=60)
        (target/'stdout.log').write_text(p.stdout);(target/'stderr.log').write_text(p.stderr)
        lines=lambda s:sorted(x for x in s.splitlines() if x.startswith(('TRACE ','CHECK ')))
        original=(folder/'simulate.stdout').read_text()
        replays.append({'case':case,'exit_code':p.returncode,'same_trace_and_checks':lines(original)==lines(p.stdout),
                        'same_checker':digest(folder/'checker_tb.sv')==digest(target/'checker_tb.sv'),
                        'same_rtl':digest(folder/'rtl.v')==digest(target/'rtl.v'),
                        'command':['sh',str(target/'reproduce.sh')],'elapsed_seconds':time.perf_counter()-start})
    except subprocess.TimeoutExpired:
        replays.append({'case':case,'status':'timeout','elapsed_seconds':time.perf_counter()-start})
write('replay_checks.json',replays)
facts['fresh_replays']=replays
write('facts.json',facts)
print(json.dumps(facts,ensure_ascii=False,indent=2),flush=True)
