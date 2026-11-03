"""Capability-corrected experiment. Old artifacts are immutable read-only sources."""
import argparse,collections,copy,hashlib,json,re,shutil,time,urllib.request
from pathlib import Path
import run_contract_v2 as v
import contract_v3_checker as checker
from contract_v2_spec import hidden_schedule,legality,views,adjudicate

PREV=v.OUT
OUT=v.ROOT/'deliverables/repair_contract_v3_20261010'
ROOT=v.ROOT;read=v.read;dump=v.dump;sha=v.sha;rel=v.rel
ORIGINAL_EXECUTE=v.engine.execute_run
OLD_CHECKPOINT=v.checkpoint
v.OUT=OUT;v.engine.OUT=OUT
v.engine.tb_text=checker.tb_text

def validated(c,d,depth):
    checker.normalize(c,d,depth)
    return {n:c[n] for n in ['antecedent','consequent','delay']}

def base_context(d,depth):
    return {'contract':d['obligation'],'allowed_identifiers':v.allowed(d,depth),
      'sampling':'pre-NBA posedge; active-low reset cancels all pending checks. delay d samples antecedent now, consequent exactly d samples later. Consequent data are NOT captured at trigger. Authorized pN copies are sampled history, zero-filled on reset.',
      'language':'JSON antecedent/consequent SystemVerilog expression strings, delay integer 0,1,2. Arithmetic/bitwise/comparison/boolean operators. popcount(SIGNAL) counts set bits of a permitted unsigned packed signal, unsigned 32-bit result. No other functions, namespaces, statements, clock/reset references. History identifiers only when explicitly listed.'}

def execute(d,rows,candidates,label,variant='correct',**kw):
    cs=[];records=[]
    for c in candidates:
        z=copy.deepcopy(c);depth=z.get('authorized_history_depth',0)
        try:
            assert 'placeholder' not in z.get('provenance',''),'parse:missing_candidate'
            norm,rules=checker.normalize(c,d,depth,kw.get('param'))
            z.pop('syntax_status',None);records.append({'original':c,'normalized':norm,'rules':rules,'supported':True})
        except (AssertionError,TypeError,KeyError) as ex:
            z['syntax_status']='unsupported_syntax';records.append({'original':c,'normalized':None,'rules':[],'supported':False,'reason':str(ex)})
        cs.append(z)
    r=ORIGINAL_EXECUTE(d,rows,cs,label,variant,**kw)
    p=ROOT/r['run_id'];dump(p/'original_candidates.json',candidates);dump(p/'normalization.json',records)
    effective=False;reason=r['status'];cycles=active=transactions=None
    if r['status']=='ok':
        tr=read(p/'trace.json');cc=[read(p/f'checker_{j}_cycles.json') for j in range(len(cs))]
        expected=[x['cycle'] for x in tr if x[d['rst']]]
        complete=all([x['cycle'] for x in checks]==expected and all(x['trigger'] is not None and x['fail'] is not None for x in checks) for checks in cc)
        if not complete:r['status']='incomplete_or_unknown_checker';reason=r['status']
        else:effective=True;reason='complete_trace_and_checker_executed';cycles=len(tr);active=len(expected)
        transaction_pred={
          'onehot':lambda x:True,'filter':lambda x:True,'fifo':lambda x:bool(x['push_i'] and x['pop_i']),
          'spill':lambda x:bool(x['push_i'] or x['flush_i']),'stat':lambda x:bool(x['frame_done_i']),
          'intr':lambda x:bool(x['event_intr_i'] or x['reg2hw_intr_test_qe_i'] or x['sw_clear'])}[d['key']]
        transactions=sum(transaction_pred(x) for x in tr if x[d['rst']])
        # Track pending assertion obligations as well as independent target obligations.
        pending=[]
        for j,c in enumerate(cs):
            last_reset=max((x['cycle'] for x in tr if not x[d['rst']]),default=-1)
            pending += [{'candidate':j,'trigger_cycle':x['cycle'],'due_cycle':x['cycle']+c['delay']} for x in cc[j] if x['trigger']==1 and x['cycle']>last_reset and x['cycle']+c['delay']>=len(tr)]
        dump(p/'pending_assertion_obligations.json',pending)
    r.update(effective_simulation=effective,effective_reason=reason,sampled_cycles=cycles,active_cycles=active,transactions=transactions,
             transaction_unit='active sampled stimulus' if d['key'] in ['onehot','filter'] else 'accepted transfers' if d['key']=='fifo' else 'input events, not independent violations')
    dump(p/'result.json',r)
    return r

def checkpoint(d,arm,step,c,rr,calls,pool_slots,depth):
    result=OLD_CHECKPOINT(d,arm,step,c,rr,calls,pool_slots,depth)
    result.update(effective_simulations=sum(r.get('effective_simulation',False) for r in rr),
      effective_cycles=sum(r.get('sampled_cycles') or 0 for r in rr if r.get('effective_simulation')),
      active_cycles=sum(r.get('active_cycles') or 0 for r in rr if r.get('effective_simulation')),
      transactions=sum(r.get('transactions') or 0 for r in rr if r.get('effective_simulation')))
    return result

def check_freeze():
    for name,h in read(OUT/'protocol_freeze.json')['hashes'].items():assert sha(ROOT/name)==h,('frozen_changed',name)

# All arm implementations share these same functions and exact model options.
v.validated=validated;v.base_context=base_context;v.checkpoint=checkpoint;v.check_freeze=check_freeze;v.engine.execute_run=execute
ORIGINAL_REQUEST=v.request_model
def request_model(d,context,uid,depth):
    r=ORIGINAL_REQUEST(d,context,uid,depth)
    r['candidate']['authorized_history_depth']=depth
    dump(OUT/'model_calls'/uid/'result.json',r)
    return r
v.request_model=request_model
# The base temporal checker now retains two bits of antecedent history; the
# collision refinement search must use at least two full port samples of memory.
import inspect
_source=inspect.getsource(v.train_observability).replace('max(depth,1)','max(depth,2)')
exec(compile(_source,'v3_train_observability_adapter','exec'),v.__dict__)

def hidden_rows(d,kind):
    rows=hidden_schedule(d,kind,seed=2026101003)
    # Extra independent episode gives new bytes even for deterministic templates.
    # No result-dependent generation: all choices fixed here before method calls.
    b=copy.deepcopy(rows[-1]);rst=d['rst'];k=d['key']
    def add(n=1,**kw):
        b.update(kw)
        for _ in range(n):rows.append({**b,'cycle':len(rows),'stimulus_id':f'v3_hidden_{kind}:{len(rows)}'})
    add(2,**{rst:0});add(1,**{rst:1})
    if k=='onehot':
        for x in [6,9,10,5,12,3,0,8]:add(1,oh_i=x,en_i=1,addr_i=(x+1)%4)
    elif k=='filter':
        for x in [1,0,1,1,0,0,1]:add(3,filter_i=x,enable_i=1)
        add(7,filter_i=0)
    elif k=='fifo':
        add(3,push_i=1,pop_i=0,data_i=173);add(1,pop_i=1);add(2,push_i=0)
    elif k=='spill':add(1,push_i=1,flush_i=1,data_i=173);add(4,push_i=0,flush_i=0)
    elif k=='stat':
        for n in [173,42,0]:add(1,frame_done_i=1,frame_len_i=n)
        add(5,frame_done_i=0)
    else:add(3,event_intr_i=1,reg2hw_intr_enable_q_i=0);add(4,event_intr_i=0,reg2hw_intr_enable_q_i=1,reg2hw_intr_test_qe_i=0,sw_clear=0)
    for i,r in enumerate(rows):r['cycle']=i;r['stimulus_id']=f'v3_hidden_{kind}:{i}'
    assert not legality(d,rows)
    return rows

def prior_permissions():
    permissions={}
    for p in (PREV/'model_calls').rglob('result.json'):
        result=read(p);candidate=result.get('candidate');permission=p.parent/'permission_check.json'
        if candidate and permission.exists():permissions[candidate['id']]=read(permission)['history_depth']
    for ent in read(PREV/'pool_freeze.json')['entries']:permissions[ent['candidate']['id']]=0
    return permissions

def inventory():
    rows=[];permissions=prior_permissions()
    for p in sorted((PREV/'runs').rglob('result.json')):
        r=read(p)
        if r['status']=='ok':continue
        d=read(p.parent/'definition.json');cs=read(p.parent/'candidates.json');reasons=[]
        for c in cs:
            try:checker.normalize(c,d,permissions.get(c['id'],0));reasons.append('newly_implemented_popcount_or_delay' if ('popcount' in str(c) or c['delay']==2) else 'old_status_requires_log_review')
            except Exception as ex:reasons.append(str(ex))
        err=p.parent/'compile.stderr'
        rows.append({'old_run':r['run_id'],'old_status':r['status'],'case':r['case'],'parent_bug_id':r['parent_bug_id'],
          'candidate':cs,'candidate_sha256':sha(p.parent/'candidates.json'),'reasons':reasons,'raw_error':err.read_text() if err.exists() else None,'raw_result':rel(p),
          'method':next((a for a in v.ARMS if '/'+a+'/' in r['run_id']),None)})
    dump(OUT/'unknown_inventory.json',rows)
    dump(OUT/'unknown_reason_counts.json',dict(collections.Counter(x for r in rows for x in r['reasons'])))
    return rows

def freeze():
    if (OUT/'protocol_freeze.json').exists():check_freeze();return
    OUT.mkdir(parents=True,exist_ok=True)
    qualification=read(OUT/'qualification.json');assert qualification['passed'];assert qualification['checker_sha256']==sha(Path(checker.__file__))
    inventory()
    for k in v.IDS:
        folder=OUT/'frozen'/k;folder.mkdir(parents=True,exist_ok=True)
        for name in ['correct.v','buggy.v','definition.json','contract.json','train_inputs.json','held_inputs.json']:
            shutil.copy2(PREV/'frozen'/k/name,folder/name)
        shutil.copytree(PREV/'frozen'/k/'spec_sources',folder/'spec_sources',dirs_exist_ok=True)
        for kind in ['transactions','reset','boundary']:dump(folder/f'hidden_{kind}.json',hidden_rows(v.definition(k),kind))
    entries=[]
    for ent in read(PREV/'pool_freeze.json')['entries']:
        k,i=ent['case'],ent['slot'];folder=OUT/'pool_provenance'/k/str(i);folder.mkdir(parents=True,exist_ok=True)
        origin=ROOT/ent['call'];original_dir=origin.parent
        for name in ['request.json','response.raw.json','result.json','permission_check.json']:
            if (original_dir/name).exists():shutil.copy2(original_dir/name,folder/name)
        raw=read(folder/'response.raw.json');rr=read(folder/'result.json');req=read(folder/'request.json')
        assert 'second_new_sample_dbg' not in json.dumps(req) and len(req['messages'])==2 and 'tools' not in req
        c=copy.deepcopy(ent['candidate']);c['authorized_history_depth']=0
        try:checker.normalize(c,v.definition(k),0);c.pop('syntax_status',None)
        except (AssertionError,TypeError,KeyError):c['syntax_status']='unsupported_syntax'
        entries.append({**ent,'candidate':c,'call':rel(folder/'result.json'),'reuse':True,'prompt_tokens':raw.get('prompt_eval_count'),'completion_tokens':raw.get('eval_count'),
          'original_wall_seconds':rr['wall_seconds'],'original_candidate':ent['candidate'],'original_call':ent['call'],'new_physical_generation_cost':0})
    for k in v.IDS:dump(OUT/'frozen'/k/'model_pool_v2.json',[e['candidate'] for e in entries if e['case']==k])
    dump(OUT/'pool_freeze.json',{'time':v.stamp(),'entries':entries,'hashes':{rel(p):sha(p) for p in (OUT/'frozen').glob('*/model_pool_v2.json')},'policy':'same 18 original slots, same order, zero regenerated candidates; old syntax flags revalidated only'})
    versions={}
    for cmd in [['python3','--version'],['iverilog','-V'],['vvp','-V'],['ollama','--version']]:versions[cmd[0]]=v.engine.command(cmd,OUT,'version_'+cmd[0],15)
    try:tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
    except Exception:
        import subprocess
        fh=(OUT/'ollama_server.log').open('a');p=subprocess.Popen(['ollama','serve'],stdout=fh,stderr=fh,start_new_session=True);time.sleep(3)
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5));dump(OUT/'server.json',{'pid':p.pid})
    prior=read(PREV/'protocol.json');tag=next(x for x in tags['models'] if x['name']==v.MODEL);assert tag['digest']==prior['model_digest']
    dump(OUT/'model_tags.json',tags)
    protocol={**prior,'version':'3.0','frozen_at':v.stamp(),'seed':20261009,'hidden_seed':2026101003,'options':v.OPTIONS,'versions':versions,
       'capabilities':checker.CAPABILITIES,'qualification':'qualification.json','previous':rel(PREV),
       'primary_budget':'effective simulation: one candidate x RTL x scenario x parameter x exact input/window, exit zero plus complete TRACE and all active-cycle CHECK records without unknowns. Nontrigger remains effective and a semantic result.',
       'budget_limits':{'pool_slots':3,'repair_calls':2,'max_compile_attempts':12,'max_effective_simulations':12,'model_timeout_seconds':180,'num_predict':192,'retries':0},
       'checkpoints':{'effective_simulations':[2,4,6,8,12],'effective_cycles':[48,96,144,192,288],
         'rule':'first completed candidate evaluation at EXACT cumulative resource checkpoint; no interpolation, padding, or after-budget lookahead. Missing checkpoints explicitly unreached. Additional cycle/transaction/parameter workloads and all costs reported. no_fp skips fixed and therefore has different workload mix, disclosed.'},
       'refinement':'same strict training collision criterion as v2, starting at max(authorized_depth,2) because delay=2 is now base memory; minimum resolving p depth <=3; equal-information from first repair',
       'hidden_access':'v3 schedules frozen before new calls. Only train/held are loaded by methods; all v1/v2 inputs/results considered investigator-seen and excluded from model requests. Hidden runner after global method freeze. No hidden feedback into methods.',
       'reuse':'same v2 initial candidate expressions and provenance; direct replay old outputs separately from fresh 72 repair requests; no new pool generation',
       'controlled_mutants':'same independent component definitions, new scenario bytes; attached to their original parent',
       'additional_parents':'none this round: resources prioritized to all six existing parents/eight arms plus exhaustive saved-run replay; no outcome-dependent additions',
       'specification':'unchanged independent v2 obligations; spill and intr remain spec_unresolved',
       'unknowns':['unsupported_syntax','tool_error','timeout','unknown_values_or_incomplete_trace','incomplete_or_unknown_checker','spec_unresolved','missing_required_witness','pending_out_of_window']}
    dump(OUT/'protocol.json',protocol)
    paths=[p for p in (OUT/'frozen').rglob('*') if p.is_file()]+[OUT/'protocol.json',OUT/'pool_freeze.json',OUT/'qualification.json']
    paths += [Path(__file__),Path(checker.__file__),ROOT/'scripts/contract_v3_qualify.py',ROOT/'scripts/run_contract_v2.py',ROOT/'scripts/run_repair_contract.py',ROOT/'scripts/contract_v2_spec.py',ROOT/'scripts/repair_contract_cases.py',ROOT/'scripts/contract_v2_hidden.py',ROOT/'scripts/contract_v2_report.py']
    dump(OUT/'protocol_freeze.json',{'time':v.stamp(),'hashes':{rel(p):sha(p) for p in paths}})
    print('V3 FROZEN',flush=True)

def replay(pilot=False):
    check_freeze();mapping=[];permissions=prior_permissions()
    import contract_v2_hidden as hidden
    paths=sorted((PREV/'runs').rglob('result.json'))
    if pilot:
        paths=[p for p in paths if '/methods/first/initial/train/' in str(p) and read(p)['case'] in ['onehot','filter','fifo','stat']]
    for p in paths:
        r=read(p);d=read(p.parent/'definition.json');rows=read(p.parent/'input.json');cs=read(p.parent/'candidates.json')
        for c in cs:
            # Replay precisely the previously frozen final/engineering permission, never import into clean pool.
            c['authorized_history_depth']=permissions.get(c['id'],0)
        ident=hashlib.sha256(r['run_id'].encode()).hexdigest()[:16];label=f'replay/{ident}'
        # Source is already rewritten/parameterized in old run, so do not apply transforms twice.
        source=p.parent/'rtl.v';v.engine.sources=lambda dd:(source,source)
        nr=execute(d,rows,cs,label,r['variant'],param=r.get('parameters'))
        folder=ROOT/nr['run_id']
        if nr['status']=='ok':
            dump(folder/'contract_views.json',{view:adjudicate(d,read(folder/'trace.json'),view) for view in views(d['key'])});nr['contract_views']=rel(folder/'contract_views.json')
        nr['replay_of']=r['run_id'];nr['component_control']=r.get('component_control');dump(folder/'result.json',nr)
        same_trace=None;same_checks=None
        if r['status']==nr['status']=='ok':
            same_trace=read(p.parent/'trace.json')==read(folder/'trace.json')
            same_checks=all(read(p.parent/f'checker_{j}_cycles.json')==read(folder/f'checker_{j}_cycles.json') for j in range(len(cs)))
        mapping.append({'old_run':r['run_id'],'new_run':nr['run_id'],'case':r['case'],'old_status':r['status'],'new_status':nr['status'],
          'effective_simulation':nr['effective_simulation'],'same_original_input':sha(p.parent/'input.json')==sha(folder/'input.json'),
          'same_rtl':sha(source)==sha(folder/'rtl.v'),'old_supported_trace_identical':same_trace,'old_supported_checks_identical':same_checks,
          'old_candidate':rel(p.parent/'candidates.json'),'normalization':rel(folder/'normalization.json'),'new_semantics':nr['candidates']})
    dump(OUT/('pilot_replay.json' if pilot else 'old_new_run_mapping.json'),mapping)
    assert all(r['same_rtl'] and r['same_original_input'] for r in mapping)
    assert all(r['old_supported_trace_identical'] is not False and r['old_supported_checks_identical'] is not False for r in mapping)
    print('REPLAY',len(mapping),dict(collections.Counter(r['new_status'] for r in mapping)),flush=True)

def methods():v.methods()
def hidden():
    import contract_v2_hidden as h
    h.hidden()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['inventory','freeze','pilot','replay','methods','hidden']);args=parser.parse_args()
    (lambda:replay(True))() if args.action=='pilot' else globals()[args.action]()
