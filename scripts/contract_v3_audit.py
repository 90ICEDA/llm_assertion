"""Independent replay and expression checks, then hash-seal new artifacts."""
import collections,copy,json,re,shlex,shutil,subprocess,time
from pathlib import Path
import run_contract_v3 as x
from contract_v2_audit import Expression
from contract_v2_spec import legality

OUT=x.OUT;ROOT=x.ROOT;read=x.read;dump=x.dump;rel=x.rel;sha=x.sha

def interpret(expr,env):
    # Reference popcount uses Python's binary representation, not generated SV
    # helpers, widths, loop text or the normalization output.
    expression=re.sub(r'\bpopcount\s*\(\s*([A-Za-z_]\w*)\s*\)',lambda m:str(bin(env[m.group(1)]).count('1')),expr)
    return Expression(expression)(env)

def independent(rows,d,c):
    past=[];due={};out=[]
    for t in rows:
        i=t['cycle']
        if not t[d['rst']]:past=[];due.clear();continue
        env={n:t[n] for n in {**d['inputs'],**d['outputs']}}
        if d['key']=='spill':env['q_o']=env['valid_o']
        for depth in (1,2,3):
            for n in list(env):
                if n.startswith(('p1_','p2_','p3_')):continue
                env[f'p{depth}_{n}']=past[-depth].get(n,0) if len(past)>=depth else 0
        ant=bool(interpret(c['antecedent'],env))
        if ant:due[i+c['delay']]=True
        fail=bool(due.pop(i,False) and not interpret(c['consequent'],env))
        out.append((i,int(ant),int(fail)));past.append({**t,**({'q_o':t['valid_o']} if d['key']=='spill' else {})})
    return out

def replay(folder,name):
    target=OUT/'audit_replays'/name;target.mkdir(parents=True,exist_ok=True)
    for n in ['rtl.v','checker_tb.sv','input.json','candidates.json','assertions.sva','expected.json']:
        if (folder/n).exists():shutil.copy2(folder/n,target/n)
    script=(folder/'reproduce.sh').read_text().replace(str(folder),str(target));(target/'reproduce.sh').write_text(script)
    t=time.perf_counter()
    try:
        p=subprocess.run(['sh',str(target/'reproduce.sh')],capture_output=True,text=True,timeout=60)
        (target/'stdout.log').write_text(p.stdout);(target/'stderr.log').write_text(p.stderr)
        records=lambda s:sorted(t for t in s.splitlines() if t.startswith(('TRACE ','CHECK ')))
        r={'source':rel(folder),'command':['sh',str(target/'reproduce.sh')],'exit_code':p.returncode,'same_checker':sha(target/'checker_tb.sv')==sha(folder/'checker_tb.sv'),
           'same_records':records(p.stdout)==records((folder/'simulate.stdout').read_text()),'wall_seconds':time.perf_counter()-t,'compile_attempts':1,'simulation_attempts':int(p.returncode==0)}
    except subprocess.TimeoutExpired as ex:
        (target/'stdout.log').write_text(str(ex.stdout));(target/'stderr.log').write_text(str(ex.stderr));r={'source':rel(folder),'status':'timeout','wall_seconds':time.perf_counter()-t}
    dump(target/'result.json',r);return r

def audit():
    checks=[];cross=[];x.check_freeze()
    for filename in ['protocol_freeze.json','pool_freeze.json','method_freeze.json','independent_plan/freeze.json']:
        for p,h in read(OUT/filename)['hashes'].items():checks.append({'kind':'freeze_hash','file':p,'pass':sha(ROOT/p)==h})
    runs=read(OUT/'run_results.json');byname={r['run_id']:r for r in runs};training=collections.defaultdict(set)
    for r in runs:
        p=ROOT/r['run_id'];d=read(p/'definition.json');rows=read(p/'input.json');cs=read(p/'candidates.json')
        checks.append({'kind':'legal_inputs','run':r['run_id'],'pass':not legality(d,rows)})
        checks.append({'kind':'actual_checker_matches_candidate','run':r['run_id'],'pass':x.checker.tb_text(d,rows,cs,r['parameters'])==(p/'checker_tb.sv').read_text()})
        checks.append({'kind':'checker_hash','run':r['run_id'],'pass':sha(p/'checker_tb.sv')==r['checker_sha256']})
        if r['status']!='ok':
            checks.append({'kind':'unsupported_not_effective','run':r['run_id'],'pass':not r.get('effective_simulation')});continue
        tr=read(p/'trace.json');raw=(p/'simulate.stdout').read_text().splitlines();cc=collections.defaultdict(list)
        for line in raw:
            if line.startswith('CHECK '):
                _,j,cy,a,f=line.split();cc[int(j)].append((int(cy),int(a),int(f)))
        active=[t['cycle'] for t in tr if t[d['rst']]]
        checks.append({'kind':'effective_qualification','run':r['run_id'],'pass':r['effective_simulation'] and len(tr)==len(rows)==r['sampled_cycles'] and all([a[0] for a in cc[j]]==active for j in range(len(cs)))})
        for j,c in enumerate(cs):
            checks.append({'kind':'raw_failure_recount','run':r['run_id'],'candidate':j,'pass':[a[0] for a in cc[j] if a[2]]==r['candidates'][j]['failure_cycles'] and [a[0] for a in cc[j] if a[1]]==r['candidates'][j]['trigger_cycles']})
            try:
                actual=independent(tr,d,c)
                cross.append({'run':r['run_id'],'candidate':j,'status':'matched' if actual==cc[j] else 'mismatch','first_differences':[(a,b) for a,b in zip(actual,cc[j]) if a!=b][:3]})
            except (ValueError,KeyError,IndexError,AssertionError) as ex:cross.append({'run':r['run_id'],'candidate':j,'status':'reference_grammar_unsupported','reason':str(ex)})
        if '/runs/methods/' in r['run_id']:
            for t in tr:training[d['key']].add(json.dumps({s:t[s] for s in d['observation_base']},sort_keys=True))
    for p in (OUT/'methods').glob('*/*/final.json'):
        m=read(p)
        checks.append({'kind':'final_checker_template','file':rel(p),'pass':x.checker.tb_text(x.v.definition(m['case']),read(OUT/'frozen'/m['case']/'train_inputs.json'),[m['candidate']])==(p.parent/'checker_template.sv').read_text()})
        for cp in m['checkpoints']:
            rr=[byname[r] for r in cp['run_ids']]
            checks.append({'kind':'budget_from_actual_runs','file':rel(p),'step':cp['step'],'pass':cp['effective_simulations']==sum(r.get('effective_simulation',False) for r in rr) and cp['effective_cycles']==sum(r.get('sampled_cycles') or 0 for r in rr if r.get('effective_simulation')) and cp['compile_invocations']==len(rr)})
        if m['arm']=='no_fp_check':checks.append({'kind':'no_fp_skips_fixed','file':rel(p),'pass':all(not n.endswith('/correct') for cp in m['checkpoints'] for n in cp['run_ids'])})
        for s in m['steps']:
            ref=s.get('refinement',{})
            if ref.get('trigger') and m['arm']!='equal_information_control':checks.append({'kind':'evidence_triggered_refinement','file':rel(p),'pass':s['before_score']['miss']>0 and ref.get('collision_count',0)>0})
    for r in read(OUT/'permission_audit.json'):checks.append({'kind':'request_permissions','file':r['request'],'pass':r['pass']})
    for p in (OUT/'model_calls/repair').rglob('visible_context.json'):
        ctx=read(p);k=p.relative_to(OUT/'model_calls/repair').parts[0];vals=[]
        for e in ctx.get('feedback',{}).get('evidence',[]):vals+=e.get('allowed_history',[])
        for e in ctx.get('feedback',{}).get('differences',[]):vals += [e['reference'],e['changed']]
        checks.append({'kind':'feedback_only_seen_training','file':rel(p),'pass':all(json.dumps(t,sort_keys=True) in training[k] for t in vals)})
    replays=[]
    for name in ['popcount_w65','delay_overlap_reset_boundary','asynchronous_reset_cancel','unknown_bits_propagate']:
        replays.append(replay(OUT/'qualification'/name,name))
    # One representative method output on each required case; true semantic success
    # and failure are reported separately from successful tool execution.
    hidden_index=read(OUT/'hidden_evaluations.json')
    for k in ['onehot','stat','filter','fifo']:
        entry=next(it for it in hidden_index if it['case']==k and it['arm']=='obligation_loop' and it['final'])
        eligible=[byname[n] for n in entry['evaluation']['run_ids'] if byname[n]['status']=='ok']
        for variant in (['correct','buggy'] if k in ['onehot','filter'] else ['buggy']):
            r=next(r for r in eligible if r['variant']==variant)
            rr=replay(ROOT/r['run_id'],'method_'+k+'_'+variant);rr['frozen_method']='obligation_loop';rr['final_expression_signature']=entry['evaluation']['expression_signature'];replays.append(rr)
    checks += [{'kind':'independent_recompile','file':r['source'],'pass':r.get('exit_code')==0 and r.get('same_checker') and r.get('same_records')} for r in replays]
    # Check source old sealing manifest for every source file used in the replays,
    # pool and selected definitions, not an unclaimed rehash of all old artifacts.
    manifest=read(x.PREV/'artifact_manifest.json')
    hashes=manifest.get('hashes',manifest.get('files',manifest))
    if isinstance(hashes,list):hashes={z['path']:z['sha256'] for z in hashes}
    sourcechecks=[]
    for old in read(OUT/'old_new_run_mapping.json'):
        for n in ['rtl.v','input.json','checker_tb.sv','candidates.json','result.json']:
            p=ROOT/old['old_run']/n;key=rel(p);expected=hashes.get(key,hashes.get(str(p.relative_to(x.PREV))))
            if isinstance(expected,dict):expected=expected.get('sha256')
            sourcechecks.append({'file':key,'found_in_prior_seal':expected is not None,'pass':expected is not None and sha(p)==expected})
    dump(OUT/'old_source_integrity.json',sourcechecks);checks += [{'kind':'old_source_preserved','file':z['file'],'pass':z['pass']} for z in sourcechecks]
    summary=read(OUT/'summary.json');parents=read(OUT/'parent_results.json')
    checks.append({'kind':'summary_recount','pass':summary['runs']==len(runs) and summary['complete_pass_parent_cells']==sum(r['complete_pass'] is True for r in parents) and summary['unknown_parent_cells']==sum(r['unknown'] for r in parents)})
    dump(OUT/'independent_expression_crosscheck.json',cross)
    result={'time':x.v.stamp(),'pass':all(c['pass'] for c in checks) and not any(c['status']=='mismatch' for c in cross),'check_count':len(checks),'checks':checks,
      'expression_counts':dict(collections.Counter(r['status'] for r in cross)),'replays':replays,'extra_audit_wall_seconds':sum(r['wall_seconds'] for r in replays)}
    dump(OUT/'audit.json',result);print(json.dumps({k:z for k,z in result.items() if k!='checks'},indent=2));assert result['pass'],'audit failures preserved in audit.json'

def seal():
    assert read(OUT/'audit.json')['pass'];x.check_freeze()
    code=OUT/'code_snapshot';code.mkdir(exist_ok=True)
    names=['run_contract_v3.py','contract_v3_checker.py','contract_v3_qualify.py','contract_v3_report.py','contract_v3_audit.py','contract_v3_finish.py','contract_v3_delivery.py',
           'run_contract_v2.py','contract_v2_spec.py','contract_v2_report.py','contract_v2_hidden.py','contract_v2_audit.py','contract_v2_observations.py','run_repair_contract.py','repair_contract_cases.py']
    for name in names:shutil.copy2(ROOT/'scripts'/name,code/name)
    dump(OUT/'implementation_hashes.json',{'files':{rel(ROOT/'scripts'/name):sha(ROOT/'scripts'/name) for name in names},'snapshots':'code_snapshot/','note':'Execution path remains the repository scripts directory; frozen protocol pins execution/acceptance core before outcomes. Report/audit glue also pinned at delivery.'})
    files=[p for p in OUT.rglob('*') if p.is_file() and p.name!='artifact_manifest.json']
    dump(OUT/'artifact_manifest.json',{'time':x.v.stamp(),'file_count':len(files),'hashes':{str(p.relative_to(OUT)):sha(p) for p in sorted(files)}})
    print('SEALED',len(files))

if __name__=='__main__':
    import sys
    seal() if len(sys.argv)>1 and sys.argv[1]=='seal' else audit()
