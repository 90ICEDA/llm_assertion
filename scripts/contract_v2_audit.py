"""Independent artifact checks, expression interpreter, and real copied-directory replay."""
import collections,json,re,shutil,subprocess,time
from pathlib import Path
from run_contract_v2 import OUT,OLD,ROOT,engine,read,dump,sha,rel,definition,check_freeze,stamp
from contract_v2_spec import adjudicate,legality
from contract_v2_observations import strict_prefix

class Expression:
    """Small independent evaluator for the primitive grammar actually executed.

    Reject unsupported syntax rather than quietly translating it. The checked
    expressions use only nonnegative interface values, comparisons and Boolean
    operators; arithmetic/bit-vector sizing is deliberately outside this audit.
    """
    prec={'||':1,'&&':2,'==':3,'!=':3,'<':4,'<=':4,'>':4,'>=':4}
    def __init__(self,text):
        pattern=r"\s*(\d+'[bBdDhH][0-9a-fA-F_]+|\d+|[A-Za-z_]\w*|&&|\|\||==|!=|<=|>=|[!<>()])"
        tokens=[];pos=0
        while pos<len(text):
            if not text[pos:].strip():break
            m=re.match(pattern,text[pos:])
            if not m:raise ValueError('outside_independent_audit_grammar:'+text[pos:])
            tokens.append(m.group(1));pos+=m.end()
        self.tokens=tokens;self.i=0;self.tree=self.parse(0)
        if self.i!=len(tokens):raise ValueError('unconsumed_expression')
    def parse(self,minp):
        tok=self.tokens[self.i];self.i+=1
        if tok=='!':left=('!',self.parse(5))
        elif tok=='(':
            left=self.parse(0);assert self.tokens[self.i]==')';self.i+=1
        elif tok[0].isdigit():
            if "'" in tok:
                w,value=tok.split("'");left=('const',int(value[1:].replace('_',''),{'b':2,'d':10,'h':16}[value[0].lower()]))
            else:left=('const',int(tok))
        else:left=('name',tok)
        while self.i<len(self.tokens) and self.tokens[self.i] in self.prec and self.prec[self.tokens[self.i]]>=minp:
            op=self.tokens[self.i];self.i+=1;left=(op,left,self.parse(self.prec[op]+1))
        return left
    def __call__(self,env):
        def ev(n):
            op=n[0]
            if op=='const':return n[1]
            if op=='name':return env[n[1]]
            if op=='!':return int(not ev(n[1]))
            a,b=ev(n[1]),ev(n[2])
            return int({'||':lambda:bool(a) or bool(b),'&&':lambda:bool(a) and bool(b),'==':lambda:a==b,'!=':lambda:a!=b,'<':lambda:a<b,'<=':lambda:a<=b,'>':lambda:a>b,'>=':lambda:a>=b}[op]())
        return ev(self.tree)

def replay(folder,name):
    target=OUT/'audit_replays'/name;target.mkdir(parents=True,exist_ok=True)
    for n in ['rtl.v','checker_tb.sv','input.json','candidates.json','assertions.sva']:shutil.copy2(folder/n,target/n)
    script=(folder/'reproduce.sh').read_text().replace(str(folder),str(target));(target/'reproduce.sh').write_text(script)
    t=time.perf_counter()
    try:
        p=subprocess.run(['sh',str(target/'reproduce.sh')],capture_output=True,text=True,timeout=60)
        (target/'stdout.log').write_text(p.stdout);(target/'stderr.log').write_text(p.stderr)
        semantic=lambda text:sorted(x for x in text.splitlines() if x.startswith(('TRACE ','CHECK ')))
        result={'source':rel(folder),'command':['sh',str(target/'reproduce.sh')],'exit_code':p.returncode,'same_trace_and_checker_records':semantic(p.stdout)==semantic((folder/'simulate.stdout').read_text()),'same_rtl':sha(folder/'rtl.v')==sha(target/'rtl.v'),'same_checker':sha(folder/'checker_tb.sv')==sha(target/'checker_tb.sv'),'wall_seconds':time.perf_counter()-t}
        dump(target/'replay.result.json',result);return result
    except subprocess.TimeoutExpired:return {'source':rel(folder),'status':'timeout','wall_seconds':time.perf_counter()-t}

def audit():
    check_freeze();checks=[]
    for filename in ['protocol_freeze.json','pool_freeze.json','method_freeze.json','independent_plan/freeze.json']:
        for p,h in read(OUT/filename)['hashes'].items():checks.append({'kind':'freeze_hash','file':p,'pass':sha(ROOT/p)==h})
    runs=read(OUT/'run_results.json');cross=[]
    for r in runs:
        folder=ROOT/r['run_id'];d=definition(r['case']);rows=read(folder/'input.json');cs=read(folder/'candidates.json')
        checks.append({'kind':'legal_inputs','run':r['run_id'],'pass':not legality(d,rows)})
        checks.append({'kind':'actual_checker_matches_candidate','run':r['run_id'],'pass':engine.tb_text(d,rows,cs,r['parameters'])==(folder/'checker_tb.sv').read_text()})
        checks.append({'kind':'checker_hash','run':r['run_id'],'pass':sha(folder/'checker_tb.sv')==r['checker_sha256']})
        if r['status']!='ok':continue
        tr=read(folder/'trace.json');raw=(folder/'simulate.stdout').read_text().splitlines();logged={}
        for line in raw:
            if line.startswith('CHECK '):
                _,j,cy,a,f=line.split();logged.setdefault(int(j),[]).append((int(cy),int(a),int(f)))
        for j,c in enumerate(cs):
            expected=r['candidates'][j];cc=logged[j]
            checks.append({'kind':'raw_log_failure_recount','run':r['run_id'],'candidate':c['id'],'pass':[x[0] for x in cc if x[2]]==expected['failure_cycles'] and [x[0] for x in cc if x[1]]==expected['trigger_cycles']})
            try:
                ae=Expression(c['antecedent']);be=Expression(c['consequent']);past=[];prev_ant=False;actual=[]
                for t in tr:
                    if not t[d['rst']]:past=[];prev_ant=False;continue
                    env={s:t[s] for s in {**d['inputs'],**d['outputs']}}
                    for dep in [1,2,3]:
                        for name in env.copy():
                            if not name.startswith(('p1_','p2_','p3_')):env[f'p{dep}_{name}']=past[-dep].get(name,0) if len(past)>=dep else 0
                    ant=bool(ae(env));fail=bool((prev_ant if c['delay'] else ant) and not be(env));actual.append((t['cycle'],int(ant),int(fail)));prev_ant=ant;past.append(t)
                cross.append({'run':r['run_id'],'candidate':c['id'],'status':'matched' if actual==cc else 'mismatch','first_differences':[(a,b) for a,b in zip(actual,cc) if a!=b][:3]})
            except (ValueError,KeyError,AssertionError,IndexError) as e:cross.append({'run':r['run_id'],'candidate':c['id'],'status':'audit_grammar_unsupported','reason':str(e)})
    witnesses=[]
    for p in (OUT/'observations/witnesses').glob('*/witness.json'):
        w=read(p);d=definition(w['case']);sidehist=[];legal_ok=False;bad_ok=False
        for side in ['legal','violation']:
            s=w[side];folder=ROOT/s['run'];tr=read(folder/'trace.json');rows=read(folder/'input.json');obs=adjudicate(d,tr,w['view']);at=s['cycle']
            st=strict_prefix(d,rows,tr,obs,at)
            if side=='legal':legal_ok=st['legal_prefix']
            else:bad_ok=bool(obs[at]['violations'])
            reset=st['reset_cycle'];hist=[tuple(t[n] for n in w['allowed_signals']) for t in tr[reset+1:at+1]]
            h=w['allowed_history_depth']
            if h!='complete':hist=hist[-h-1:];hist=[tuple(0 for _ in w['allowed_signals'])]*max(0,h+1-len(hist))+hist
            sidehist.append(hist)
        witnesses.append({'witness':rel(p),'pass':legal_ok and bad_ok and sidehist[0]==sidehist[1],'legal_prefix':legal_ok,'target_violated':bad_ok,'complete_allowed_history_equal':sidehist[0]==sidehist[1]})
    dump(OUT/'independent_expression_crosscheck.json',cross);dump(OUT/'strict_witness_audit.json',witnesses)
    perms=read(OUT/'permission_audit.json');checks += [{'kind':'actual_request_whitelist','file':x['request'],'pass':x['pass']} for x in perms]
    # Actual method requests never carry hidden schedules. Compare projected
    # transcript snippets to the whitelisted known train/held data, not substring
    # matching a filename that a leak need not contain.
    training_by_case=collections.defaultdict(set)
    for r in runs:
        if '/runs/methods/' not in r['run_id'] or r['status']!='ok':continue
        d=definition(r['case'])
        for t in read(ROOT/r['trace']):training_by_case[r['case']].add(json.dumps({s:t[s] for s in d['observation_base']},sort_keys=True))
    for p in (OUT/'model_calls/repair').rglob('visible_context.json'):
        ctx=read(p);k=p.relative_to(OUT/'model_calls/repair').parts[0];d=definition(k);permitted=training_by_case[k]
        vals=[]
        for e in ctx.get('feedback',{}).get('evidence',[]):vals+=e.get('allowed_history',[])
        for e in ctx.get('feedback',{}).get('differences',[]):vals += [e['reference'],e['changed']]
        checks.append({'kind':'feedback_values_from_seen_training_only','file':rel(p),'pass':all(json.dumps(t,sort_keys=True) in permitted for t in vals)})
    methods=list((OUT/'methods').glob('*/*/final.json'))
    for p in methods:
        m=read(p)
        if m['arm']=='no_fp_check':checks.append({'kind':'no_fp_method_skips_fixed_checks','file':rel(p),'pass':all(not r.endswith('/correct') for cp in m['checkpoints'] for r in cp['run_ids'])})
        for s in m['steps']:
            ref=s.get('refinement',{})
            if ref.get('trigger') and m['arm']!='equal_information_control':checks.append({'kind':'refinement_has_miss_and_strict_collision','file':rel(p),'pass':s['before_score']['miss']>0 and ref.get('collision_count',0)>0 and ref['new_depth']>ref['current_depth']})
    # Representative observation-level successful protection and semantic failure.
    good=next(r for r in runs if r['case']=='fifo' and r['status']=='ok' and r['variant']=='buggy' and r['candidates'][0]['covered_violation_cycles'])
    bad=next(r for r in runs if r['case']=='filter' and r['status']=='ok' and r['variant']=='correct' and r['candidates'][0]['false_positive_cycles'])
    replays=[replay(ROOT/good['run_id'],'observed_target_detection'),replay(ROOT/bad['run_id'],'legal_behavior_false_alarm')]
    if witnesses:
        w=read(ROOT/witnesses[0]['witness'])
        replays += [replay(ROOT/w[side]['run'],'conflict_'+side) for side in ['legal','violation']]
    checks += [{'kind':'independent_recompile','file':r['source'],'pass':r.get('exit_code')==0 and r.get('same_trace_and_checker_records') and r.get('same_checker')} for r in replays]
    checks += [{'kind':'strict_witness','file':r['witness'],'pass':r['pass']} for r in witnesses]
    summary=read(OUT/'summary.json');parent=read(OUT/'parent_results.json')
    checks.append({'kind':'summary_recount','pass':summary['runs']==len(runs) and summary['complete_pass_parent_cells']==sum(x['complete_pass'] is True for x in parent) and summary['unknown_parent_cells']==sum(x['unknown'] for x in parent)})
    result={'time':stamp(),'checks':checks,'pass':all(x['pass'] for x in checks) and not any(x['status']=='mismatch' for x in cross),'check_count':len(checks),'expression_crosscheck_counts':dict(collections.Counter(x['status'] for x in cross)),'witness_count':len(witnesses),'replays':replays,
            'replay_scope':'observed target-detection success is not a full-contract parent pass; semantic false alarm and both sides of a strict observation conflict separately replayed','extra_audit_replay_wall_seconds':sum(r['wall_seconds'] for r in replays)}
    dump(OUT/'audit.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='checks'},indent=2),flush=True)
    assert result['pass'],'See audit.json for failed consistency checks'

if __name__=='__main__':audit()
