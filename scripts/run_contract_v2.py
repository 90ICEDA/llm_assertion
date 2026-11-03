#!/usr/bin/env python3
"""Corrected, isolated supplement. Commands: freeze, pool, methods, hidden, report, audit.

The original sealed directory is read-only input. Model requests are stateless,
two-message API calls with no tools/files, and their complete bytes are retained.
"""
import argparse, collections, copy, csv, hashlib, json, re, shlex, shutil, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path
import run_repair_contract as engine
from contract_v2_spec import definition, contract, components, branches, trigger_branches, views, adjudicate, legality, hidden_schedule, IDS, ROOT, sources, SEED

OLD=ROOT/'deliverables/repair_contract_20261009'
OUT=ROOT/'deliverables/repair_contract_v2_20261009'
MODEL=engine.MODEL
ARMS=['first','equal_budget_select','existing_feedback','obligation_loop','generic_diff','no_fp_check','no_observation_refinement','equal_information_control']
OPTIONS={'seed':SEED,'temperature':0.2,'num_predict':192,'num_ctx':4096,'num_gpu':0,'num_thread':8}
engine.OUT=OUT
read=engine.read;dump=engine.dump;sha=engine.sha;rel=engine.rel

def stamp():return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def log(event,**kw):engine.append(OUT/'events.jsonl',{'time':stamp(),'event':event,**kw})
def allowed(d,depth=0):return d['observation_base']+[f'p{j}_{s}' for j in range(1,depth+1) for s in d['observation_base']]
def project(d,rows):return [{s:r[s] for s in d['observation_base']} for r in rows]
def unknown_candidate(uid):return {'id':uid,'provenance':'unsupported_model_output_placeholder_NOT_a_generated_assertion','antecedent':'0','consequent':'1','delay':0,'syntax_status':'unsupported_syntax'}

def freeze():
    if (OUT/'protocol_freeze.json').exists():check_freeze();return
    OUT.mkdir(parents=True,exist_ok=True)
    versions={}
    for cmd in [['python3','--version'],['iverilog','-V'],['vvp','-V'],['ollama','--version'],['git','rev-parse','HEAD']]:
        r=engine.command(cmd,OUT,'version_'+cmd[0],15);versions[cmd[0]]=r
    try:tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
    except Exception:
        fh=(OUT/'ollama_server.log').open('a');p=subprocess.Popen(['ollama','serve'],stdout=fh,stderr=fh,start_new_session=True);dump(OUT/'server.json',{'pid':p.pid});time.sleep(3)
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
    dump(OUT/'model_tags.json',tags)
    tag=next(x for x in tags['models'] if x['name']==MODEL)
    prior=next(x for x in read(OLD/'model_tags.json')['models'] if x['name']==MODEL)
    assert tag['digest']==prior['digest'],'model_digest_changed'
    inventory=[]
    for k in IDS:
        d=definition(k);ct=contract(k);folder=OUT/'frozen'/k;folder.mkdir(parents=True,exist_ok=True)
        for name in ct['sources']:
            p=ROOT/name
            assert p.exists(),name
            dest=folder/'spec_sources'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
        dump(folder/'contract.json',ct);dump(folder/'definition.json',d)
        for variant,src in zip(['correct','buggy'],sources(d)):shutil.copy2(src,folder/(variant+'.v'))
        for kind in ['train','held']:
            rows=read(OLD/'frozen'/k/(kind+'_inputs.json'));assert not legality(d,rows)
            dump(folder/(kind+'_inputs.json'),rows)
        for kind in ['transactions','reset','boundary']:
            dump(folder/('hidden_'+kind+'.json'),hidden_schedule(d,kind))
        inventory.append({'case':k,'parent_bug_id':IDS[k],'spec_status':ct['status'],'views':views(k),'source':'existing_artificial_mutation','pool_policy':'regenerate_due_to_contract_revision' if k in ['spill','intr'] else 'reuse_permission_audited_initial_pool_only'})
    protocol={'version':'2.0','frozen_at':stamp(),'cases':inventory,'model':MODEL,'model_digest':tag['digest'],'options':OPTIONS,'seed':SEED,
       'model_access':{'messages':2,'tools':[],'files':[],'conversation_history':False,'server_side_context_ids':False,'rtl_or_comments':False,'waveforms':'only projected allowed interface values','diagnostics':'normalized category only; raw compiler diagnostics not sent','candidate_history':'current accepted property only if its identifiers are permitted','independent_evaluator':'full trace, independent contract labels, hidden scenarios; never sent wholesale'},
       'arms':ARMS,'primary_budget':'actual compiler invocations on candidate/RTL/scenario cells; unsupported output still consumes a real compile attempt when safely representable',
       'budget_limits':{'initial_pool_size':3,'repair_calls':2,'total_logical_model_calls':3,'max_compile_invocations':12,'max_completion_tokens_per_call':192,'context_tokens':4096,'model_timeout_seconds':180,'retry_count':0},
       'checkpoints':{'exact_compiles':[2,4,6,8,12],'token_envelopes':[2048,4096,8192,12864],'simulation_envelopes':[0,2,4,8,12],'rules':'record after each complete candidate evaluation; compare exact common observed compiler-count checkpoints when available, plus last completed output within each common token/simulation envelope. No padding; unused resources and token/time differences reported. First baseline may terminate earlier. Exact positive-simulation intersection may be empty.'},
       'validation':'each proposed candidate rechecked on all train/held witnesses; no_fp arm does not simulate fixed RTL or compute legal FP during method decisions; independent final evaluator does',
       'acceptance':'same lexicographic (unknown, FP unless no_fp, miss, missing per-obligation branch triggers); generic_diff changes ONLY serialized feedback, not rank/update/refinement/budget. Existing_feedback uses its sealed v1 fixed/buggy fail-hit rule with unknown first.',
       'existing_feedback_identity':'the prior sealed experiment existing_feedback arm in scripts/run_repair_contract.py lines 333-364, adapted to enforce the corrected whitelist; not claimed equivalent to every historical repository repair pipeline',
       'refinement':'trigger only if current candidate has an observed miss and a strict legal-prefix/violation-prefix collision exists at current depth on train/held traces. Choose minimum resolving depth from 1..3. No extra signals. Same algorithm for obligation/generic/no_fp; no_observation disables only this action. Equal_information uses obligation arm final authorization depth from its first repair call; this entitlement is logged, without passing its candidates or feedback.',
       'pool_cost':'old unpolluted initial generation charged logically by original request/response token counts; copied evidence has zero new physical inference cost. New spill/intr pool physical cost shared once and charged per consumed slot logically.',
       'hidden_access':'inputs presealed; methods only load train/held. Hidden runner refuses execution until all final outputs and actual checker templates are hashed. Hidden seeds/schedules never in model requests. Prior v1 traces all declared seen to investigator; new hidden files are not sent to methods.',
       'acceptance_scope':'finite frozen scenarios. For full pass require no unknown/spec ambiguity, no FP/FN, every scenario branch witnessed; assertion trigger required only on listed target-condition branches, not negative/legal controls or reset cancellation. Every target component must be activated and detected. Missing witness is unknown, not pass. Independent labels for multiple unresolved interpretations remain separate.',
       'unknowns':['timeout','tool_error','unsupported_syntax','spec_unresolved','missing_required_witness','pending_out_of_window'],
       'controlled_mutants':'final candidates also checked against frozen component-isolating mutants; these are controls attached to same parent, never new parent samples',
       'reuse':'E2 original 12 window comparisons retained; raw traces for E1/E3 relabelled without changing RTL/checker. Old repaired candidates are never reused.',
       'versions':versions,'AGENTS':'rg search of repository outside caches plus parent/root checks found no applicable AGENTS.md','git':'no valid HEAD; content hashes pin code and design'}
    dump(OUT/'protocol.json',protocol)
    paths=list((OUT/'frozen').rglob('*'))+[OUT/'protocol.json',OUT/'model_tags.json',Path(__file__),ROOT/'scripts/contract_v2_spec.py',ROOT/'scripts/run_repair_contract.py',ROOT/'scripts/repair_contract_cases.py']
    dump(OUT/'protocol_freeze.json',{'time':stamp(),'hashes':{rel(p):sha(p) for p in paths if p.is_file()}})
    log('protocol_frozen',parents=len(IDS));print('PROTOCOL FROZEN',flush=True)

def check_freeze():
    for name,h in read(OUT/'protocol_freeze.json')['hashes'].items():assert sha(ROOT/name)==h,('frozen_changed',name)

def validated(c,d,depth):
    z=engine.valid_candidate(c,d,depth>0)
    for field in ['antecedent','consequent']:
        names=set(re.findall(r'\b[A-Za-z_]\w*',re.sub(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+",'0',z[field])))
        assert names<=set(allowed(d,depth)),'identifier_not_permitted'
    return z

def base_context(d,depth):
    return {'contract':d['obligation'],'allowed_identifiers':allowed(d,depth),'sampling':'pre-NBA posedge; active-low reset guard supplied by harness; explicit history copies reset to zero','language':'JSON antecedent/consequent SystemVerilog expressions; delay integer 0 or 1. No functions, namespaces, clock/reset references, or statements. Arithmetic/bitwise/comparison/boolean operators only. History names must appear verbatim in allowed_identifiers.'}

def request_model(d,context,uid,depth):
    folder=OUT/'model_calls'/uid;folder.mkdir(parents=True,exist_ok=True)
    if (folder/'result.json').exists():return read(folder/'result.json')
    assert set(context)<=set(['contract','allowed_identifiers','sampling','language','candidate_index','current_property','feedback','task'])
    text=json.dumps(context,ensure_ascii=False)
    assert 'second_new_sample_dbg' not in text
    req={'model':MODEL,'stream':False,'format':'json','messages':[{'role':'system','content':'Return exactly one JSON object with antecedent, consequent and delay. Follow the provided interface whitelist. No tools, file access, or earlier conversation is available.'},{'role':'user','content':text}],'options':OPTIONS}
    dump(folder/'request.json',req);dump(folder/'visible_context.json',context)
    dump(folder/'permission_check.json',{'pass':True,'request_sha256':sha(folder/'request.json'),'messages':2,'tools':False,'files':False,'all_context_in_request':True,'allowed_identifiers':allowed(d,depth),'protected_debug_signal_absent':True,'history_depth':depth})
    t=time.perf_counter();result={'id':uid,'status':'unknown','candidate':None,'request':rel(folder/'request.json'),'cached_reuse':False,'fresh_context':True}
    log('model_request',id=uid,request=result['request'],request_sha256=sha(folder/'request.json'))
    try:
        raw=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'}),timeout=180).read()
        (folder/'response.raw.json').write_bytes(raw);env=json.loads(raw)
        result.update(prompt_tokens=env.get('prompt_eval_count'),completion_tokens=env.get('eval_count'),model_total_duration_ns=env.get('total_duration'),model_load_duration_ns=env.get('load_duration'))
        c=json.loads(env['message']['content'])
        z=validated(c,d,depth);z.update(id=uid.replace('/','_'),provenance='v2_fresh_model_generated');result.update(status='generated',candidate=z)
    except (AssertionError,ValueError,KeyError,TypeError) as e:
        result.update(status='unsupported_syntax',error=str(e))
        try:
            if engine.safe_raw_candidate(c):result['candidate']={**c,'id':uid.replace('/','_'),'provenance':'v2_fresh_unsupported_model_output','syntax_status':'unsupported_syntax'}
        except UnboundLocalError:pass
    except urllib.error.HTTPError as e:
        (folder/'http_error.txt').write_bytes(e.read());result.update(status='tool_error',error=str(e))
    except Exception as e:result.update(status='timeout' if isinstance(e,TimeoutError) else 'tool_error',error=repr(e))
    result['wall_seconds']=time.perf_counter()-t
    if result['candidate'] is None:result['candidate']=unknown_candidate(uid.replace('/','_'))
    dump(folder/'result.json',result);log('model_response',id=uid,status=result['status']);print('MODEL',uid,result['status'],round(result['wall_seconds'],2),flush=True)
    return result

def pool():
    check_freeze();manifest=[]
    for k in IDS:
        d=definition(k);cs=[]
        oldcs={c['id']:c for c in read(OLD/'frozen'/k/'model_pool.json')}
        for i in range(3):
            if k in ['spill','intr']:
                r=request_model(d,{**base_context(d,0),'candidate_index':i,'task':'Generate a candidate for the stated repair target; unresolved interpretations are not silently resolved.'},f'pool/{k}/{i}',0)
                c=r['candidate'];entry={'case':k,'slot':i,'candidate':c,'call':rel(OUT/f'model_calls/pool/{k}/{i}/result.json'),'reuse':False}
            else:
                origin=OLD/f'model_calls/pool/{k}/{i}';req=read(origin/'request.json')
                assert len(req['messages'])==2 and 'tools' not in req and 'second_new_sample_dbg' not in json.dumps(req)
                assert req['options']==OPTIONS
                raw=read(origin/'response.raw.json');rr=read(origin/'result.json')
                c=oldcs.get(f'pool_{k}_{i}',rr.get('candidate')) or unknown_candidate(f'pool_{k}_{i}')
                folder=OUT/f'pool_provenance/{k}/{i}';folder.mkdir(parents=True,exist_ok=True)
                for name in ['request.json','response.raw.json','result.json']:shutil.copy2(origin/name,folder/name)
                dump(folder/'permission_check.json',{'pass':True,'request_sha256':sha(folder/'request.json'),'two_messages_no_tools':True,'debug_absent':True,'source':'initial pool, not polluted repair candidates','allowed_assertion_signals':d['observation_base'],'physical_inference_reused':True})
                entry={'case':k,'slot':i,'candidate':c,'call':rel(folder/'result.json'),'reuse':True,'prompt_tokens':raw.get('prompt_eval_count'),'completion_tokens':raw.get('eval_count'),'original_wall_seconds':rr['wall_seconds']}
            cs.append(c);manifest.append(entry)
        dump(OUT/'frozen'/k/'model_pool_v2.json',cs)
    dump(OUT/'pool_freeze.json',{'time':stamp(),'entries':manifest,'hashes':{rel(p):sha(p) for p in (OUT/'frozen').glob('*/model_pool_v2.json')}})
    log('pool_frozen',slots=len(manifest))

def frozen_sources(d):return OUT/'frozen'/d['key']/'correct.v',OUT/'frozen'/d['key']/'buggy.v'

def run(d,c,kind,label,variant='correct',rows=None,param=None,rewrite=False,mutation=None):
    rows=rows if rows is not None else read(OUT/'frozen'/d['key']/(kind+'_inputs.json'))
    assert not legality(d,rows),legality(d,rows)
    engine.sources=frozen_sources
    r=engine.execute_run(d,rows,[c],label,variant,param=param,rewrite=rewrite,controlled_mutation=mutation)
    folder=ROOT/r['run_id']
    dump(folder/'legality.json',{'valid':True,'scope':contract(d['key'])['environment'],'violations':[]})
    if r['status']=='ok':
        tr=read(ROOT/r['trace']);vv={v:adjudicate(d,tr,v) for v in views(d['key'])};dump(folder/'contract_views.json',vv)
        r['contract_views']=rel(folder/'contract_views.json')
    dump(folder/'result.json',r)
    return r

def assessment(d,rr,check_fp=True):
    score={'unknown':0,'fp':0,'miss':0,'missing_branch_triggers':0,'branch_witnesses':{},'activated_components':{},'fixed_fail_hit':0,'buggy_fail_hit':0,'trigger_count':0}
    for r in rr:
        if r['status']!='ok':score['unknown']+=1;continue
        c=r['candidates'][0];fails=set(c['failure_cycles']);ants=set(c['trigger_cycles']);score['trigger_count']+=len(ants)
        score['fixed_fail_hit' if r['variant']=='correct' else 'buggy_fail_hit']+=len(fails)
        vv=read(ROOT/r['contract_views']);definitions=read(ROOT/r['run_id']/'candidates.json');delay=definitions[0]['delay']
        for view,obs in vv.items():
            violations={o['cycle'] for o in obs if o['violations']}
            if check_fp and r['variant']=='correct':score['fp']+=len(fails-violations)
            score['miss']+=len(violations-fails)
            for o in obs:
                for b in o['branches']:
                    key=view+':'+b
                    # Branch witness and antecedent must overlap its trigger/due window.
                    hit=any(j in ants for j in range(max(0,o['cycle']-2),o['cycle']+1))
                    if hit:score['branch_witnesses'].setdefault(key,[]).append({'run':r['run_id'],'cycle':o['cycle']})
                for name in o['violations']:score['activated_components'][view+':'+name]=True
    score['missing_branch_triggers']=sum(v+':'+b not in score['branch_witnesses'] for v in views(d['key']) for b in trigger_branches(d['key']))
    return score

def rank(s,no_fp=False,old=False):
    if old:return(s['unknown'],s['fixed_fail_hit'],-s['buggy_fail_hit'])
    return(s['unknown'],0 if no_fp else s['fp'],s['miss'],s['missing_branch_triggers'])

def evaluate(d,c,tag,no_fp=False):
    return [run(d,c,kind,f'methods/{tag}/{kind}',v) for kind in ['train','held'] for v in (['buggy'] if no_fp else ['correct','buggy'])]

def train_observability(d,depth):
    # Only original train/held histories, never hidden scenarios or old repaired candidates.
    histories=[]
    for kind,label in [('train','hold_24'),('held','held_24')]:
        for variant in ['correct','buggy']:
            folder=OLD/'runs/e12'/label/d['key']/variant
            tr=read(folder/'trace.json');rows=read(folder/'input.json')
            assert not legality(d,rows)
            for view in views(d['key']):
                obs=adjudicate(d,tr,view);past=[];clean=True
                for t,o in zip(tr,obs):
                    if not t[d['rst']]:past=[];clean=True;continue
                    past.append(tuple(t[s] for s in d['observation_base']));clean=clean and not o['violations']
                    histories.append({'view':view,'obs':list(past),'legal':clean,'violation':bool(o['violations']),'run':rel(folder),'cycle':t['cycle']})
    def conflicts(h):
        groups={}
        for x in histories:
            hist=x['obs'][-h-1:];hist=[tuple(0 for _ in d['observation_base'])]*max(0,h+1-len(hist))+hist
            g=groups.setdefault((x['view'],tuple(hist)),{'legal':[],'bad':[]})
            if x['legal']:g['legal'].append(x)
            if x['violation']:g['bad'].append(x)
        return [{'legal':g['legal'][0],'violation':g['bad'][0]} for g in groups.values() if g['legal'] and g['bad']]
    # Delay=1 already retains one antecedent bit. Full one-cycle port history is
    # a conservative superset of that base capability, avoiding false claims of
    # insufficiency based on a memoryless projection alone.
    search_depth=max(depth,1)
    base=conflicts(search_depth)
    if not base:return {'trigger':False,'current_depth':depth,'reason':'no_strict_collision_in_training','new_depth':depth}
    levels={str(h):len(conflicts(h)) for h in range(search_depth+1,4)}
    chosen=next((h for h in range(search_depth+1,4) if levels[str(h)]==0),None)
    return {'trigger':chosen is not None,'current_depth':depth,'new_depth':chosen if chosen is not None else depth,'collision_count':len(base),'witness':base[0],'remaining_conflicts_by_depth':levels,'reason':'strict_training_collision_resolved_by_history' if chosen else 'no_resolving_depth_in_1_to_3'}

def feedback(d,rr,s,mode):
    if mode=='generic_diff':
        items=[]
        for kind in ['train','held']:
            a=next((r for r in rr if r['variant']=='correct' and '/'+kind+'/' in r['run_id']),None)
            b=next((r for r in rr if r['variant']=='buggy' and '/'+kind+'/' in r['run_id']),None)
            if a and b and a['status']==b['status']=='ok':
                aa=project(d,read(ROOT/a['trace']));bb=project(d,read(ROOT/b['trace']))
                items.extend({'reference':x,'changed':y} for x,y in zip(aa,bb) if x!=y)
        return {'type':'generic_RTL_interface_execution_differences','differences':items[:4],'unsupported_runs':s['unknown']}
    if mode=='existing_feedback':return {'fixed_fail_hit':s['fixed_fail_hit'],'buggy_fail_hit':s['buggy_fail_hit'],'antecedent_hits':s['trigger_count'],'unsupported_runs':s['unknown']}
    out={n:s[n] for n in ['unknown','miss','missing_branch_triggers']}
    if mode!='no_fp_check':out['fp']=s['fp']
    evidence=[]
    for r in rr:
        if r['status']!='ok':continue
        tr=read(ROOT/r['trace']);c=r['candidates'][0];ff=set(c['failure_cycles'])
        for v,obs in read(ROOT/r['contract_views']).items():
            points=[o for o in obs if (o['violations'] and o['cycle'] not in ff) or (mode!='no_fp_check' and r['variant']=='correct' and not o['violations'] and o['cycle'] in ff)]
            for o in points[:2]:evidence.append({'variant':r['variant'],'interpretation':v,'allowed_history':project(d,tr[max(0,o['cycle']-3):o['cycle']+1]),'violated_components':o['violations'],'required_branches':o['branches']})
    out['evidence']=evidence[:4];out['missing_required_branches']=[v+':'+b for v in views(d['key']) for b in trigger_branches(d['key']) if v+':'+b not in s['branch_witnesses']]
    return out

def checkpoint(d,arm,step,c,rr,calls,pool_slots,depth):
    entries=read(OUT/'pool_freeze.json')['entries'];gen=[x for x in entries if x['case']==d['key'] and x['slot'] in pool_slots]
    costs=[]
    for x in gen:
        if x['reuse']:costs.append({'prompt_tokens':x['prompt_tokens'],'completion_tokens':x['completion_tokens'],'wall_seconds':x['original_wall_seconds'],'physical_new':False})
        else:costs.append({**read(ROOT/x['call']),'physical_new':True})
    costs += [read(ROOT/p) for p in calls]
    return {'case':d['key'],'arm':arm,'step':step,'candidate':c,'depth':depth,'pool_slots':pool_slots,'calls':calls,
      'compile_invocations':len(rr),'simulation_invocations':sum(r.get('simulate') is not None for r in rr),'successful_simulations':sum(r['status']=='ok' for r in rr),
      'prompt_tokens':sum(x.get('prompt_tokens') or 0 for x in costs),'completion_tokens':sum(x.get('completion_tokens') or 0 for x in costs),'unknown_token_calls':sum(x.get('prompt_tokens') is None for x in costs),
      'logical_model_calls':len(costs),'logical_model_wall_seconds':sum(x['wall_seconds'] for x in costs),
      'validation_wall_seconds':sum(r['validation_wall_seconds'] for r in rr),'solver_calls':0,'solver_seconds':None,'solver_status':'not_used',
      'cached_initial_generation_calls':sum(x['reuse'] for x in gen),'run_ids':[r['run_id'] for r in rr],
      'history_bits_permission':depth*sum({**d['inputs'],**d['outputs']}[s] for s in d['observation_base'])}

def methods():
    check_freeze();poolf=read(OUT/'pool_freeze.json')
    for p,h in poolf['hashes'].items():assert sha(ROOT/p)==h
    for k in IDS:
        d=definition(k);poolcs=read(OUT/'frozen'/k/'model_pool_v2.json')
        for arm in ARMS:
            folder=OUT/'methods'/k/arm
            if (folder/'final.json').exists():continue
            best=poolcs[0];depth=0;no_fp=arm=='no_fp_check';rr=evaluate(d,best,f'{arm}/initial',no_fp);total=list(rr);s=assessment(d,rr,not no_fp);calls=[];steps=[];slots=[0]
            checkpoints=[checkpoint(d,arm,0,best,total,calls,slots,depth)]
            if arm=='equal_budget_select':
                for j,c in enumerate(poolcs[1:],1):
                    newrr=evaluate(d,c,f'{arm}/slot{j}');total+=newrr;ns=assessment(d,newrr)
                    accepted=rank(ns)<=rank(s)
                    if accepted:best,s,rr=c,ns,newrr
                    slots.append(j);steps.append({'step':j,'accepted':accepted,'score':ns})
                    checkpoints.append(checkpoint(d,arm,j,best,total,calls,slots,depth))
            elif arm!='first':
                for step in range(2):
                    refinement={'trigger':False,'reason':'disabled_or_no_observed_miss','new_depth':depth}
                    if arm in ['obligation_loop','generic_diff','no_fp_check'] and s['miss']>0:refinement=train_observability(d,depth)
                    if arm=='equal_information_control':
                        reference=read(OUT/'methods'/k/'obligation_loop/final.json');refinement={'trigger':reference['depth']>depth,'new_depth':reference['depth'],'reason':'same_additional_permission_as_obligation_arm_from_first_repair','authorization_source':rel(OUT/'methods'/k/'obligation_loop/final.json')}
                    depth=refinement['new_depth']
                    ctx=base_context(d,depth)
                    try:current=validated(best,d,depth)
                    except (AssertionError,TypeError,KeyError):current={'status':'unsupported expression; replace using only permitted identifiers'}
                    ctx.update(current_property=current,feedback=feedback(d,rr,s,arm),task='Repair the candidate. Produce one complete JSON property; satisfy the repair target within permitted information.')
                    call=request_model(d,ctx,f'repair/{k}/{arm}/{step}',depth);calls.append(rel(OUT/f'model_calls/repair/{k}/{arm}/{step}/result.json'))
                    new=call['candidate'];newrr=evaluate(d,new,f'{arm}/step{step}',no_fp);total+=newrr;ns=assessment(d,newrr,not no_fp)
                    accept=rank(ns,no_fp,arm=='existing_feedback')<=rank(s,no_fp,arm=='existing_feedback')
                    steps.append({'step':step,'refinement':refinement,'before_score':s,'proposal':new,'proposal_score':ns,'accepted':accept,'new_runs':[r['run_id'] for r in newrr]})
                    if accept:best,s,rr=new,ns,newrr
                    checkpoints.append(checkpoint(d,arm,step+1,best,total,calls,slots,depth))
            final={'case':k,'parent_bug_id':IDS[k],'arm':arm,'candidate':best,'depth':depth,'score':s,'steps':steps,'checkpoints':checkpoints,'frozen_at':stamp()}
            dump(folder/'final.json',final)
            # Freeze actual checker templates before hidden execution, not just assertion strings.
            rows=read(OUT/'frozen'/k/'train_inputs.json');(folder/'checker_template.sv').write_text(engine.tb_text(d,rows,[best]));(folder/'assertion.sva').write_text(engine.sva(d,best)+'\n')
            log('method_frozen',case=k,arm=arm,candidate=best['id']);print('FINAL',k,arm,s['fp'],s['miss'],s['unknown'],flush=True)
    paths=[p for p in (OUT/'methods').rglob('*') if p.is_file()]
    dump(OUT/'method_freeze.json',{'time':stamp(),'hashes':{rel(p):sha(p) for p in paths}})

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['freeze','pool','methods']);args=parser.parse_args();globals()[args.action]()
