"""Strict prefix adjudication, full allowed histories, and original signature re-use."""
import collections, copy, itertools, json
from run_contract_v2 import OUT,OLD,ROOT,read,dump,rel,sha,log,run,definition,IDS
from contract_v2_spec import adjudicate,views,legality

def strict_prefix(d,rows,tr,obs,at):
    reset=max([t['cycle'] for t in tr[:at+1] if not t[d['rst']]],default=-1)
    environment=legality(d,rows[reset+1:at+1])
    earlier=[o['cycle'] for o in obs[reset+1:at+1] if o['violations']]
    pending=obs[at]['pending'];discharges=[]
    for p in pending:
        due=p['due_cycle'];cancel=next((t['cycle'] for t in tr[at+1:min(len(tr),due+1)] if not t[d['rst']]),None)
        state='cancelled_by_effective_reset' if cancel is not None else 'outside_window' if due>=len(obs) else 'violated' if obs[due]['violations'] else 'fulfilled'
        discharges.append({**p,'status':state,'cancel_cycle':cancel})
    valid=not environment and not earlier and all(x['status'] in ['fulfilled','cancelled_by_effective_reset'] for x in discharges)
    return {'legal_prefix':valid,'reset_cycle':reset,'environment_violations':environment,'violating_cycles_in_prefix':earlier,'pending_discharge':discharges,
            'label_scope':'prefix from effective reset through observation sample; future already-recorded suffix used only to discharge pending obligations, never compared as observed history'}

def audit_original_witnesses():
    out=[]
    for item in read(OLD/'history_refinement.json'):
        k=next(k for k,v in IDS.items() if v==item['parent_bug_id']);d=definition(k)
        for level in item['levels']:
            for number,w in enumerate(level['witnesses']):
                aa=ROOT/w['legal']['run'];rr=read(aa/'result.json');tr=read(aa/'trace.json');rows=read(aa/'input.json')
                bb=ROOT/w['violation']['run'];bt=read(bb/'trace.json')
                labels={}
                for v in views(k):
                    ob=adjudicate(d,tr,v);labels[v]=strict_prefix(d,rows,tr,ob,w['legal']['cycle']);labels[v]['violation_side_violates']=bool(adjudicate(d,bt,v)[w['violation']['cycle']]['violations'])
                out.append({'parent_bug_id':IDS[k],'depth':level['history_depth'],'witness_index':number,'old_legal':w['legal'],'old_violation':w['violation'],'views':labels,
                    'disposition':'retained_strict_under_listed_views' if all(x['legal_prefix'] and x['violation_side_violates'] for x in labels.values()) else 'downgraded_to_pointwise_or_interpretation_conditional',
                    'spec_status':'unresolved' if k in ['spill','intr'] else 'scoped'})
    dump(OUT/'observations/original_20_adjudication.json',out)

def controlled_filter_rows():
    rows=[]
    for seq in itertools.product([0,1],repeat=7):
        for reset,bit in [(0,0),(0,0)]+[(1,x) for x in seq]+[(1,seq[-1])]*4:
            rows.append({'cycle':len(rows),'stimulus_id':'controlled_filter_sequence_'+''.join(map(str,seq)),'rst_n':reset,'enable_i':1,'filter_i':bit,'thresh_i':2})
    return rows

def search():
    sources=[]
    for k in IDS:
        for label in ['held_24','hold_24']:
            for variant in ['correct','buggy']:sources.append((k,OLD/'runs/e12'/label/k/variant,'reused_natural_RTL_execution'))
        for p in (OLD/'runs/legacy_regression').glob(k+'/*'):
            if (p/'trace.json').exists():sources.append((k,p,'reused_natural_RTL_execution'))
    d=definition('filter');c={'id':'observation_capture_control','antecedent':'0','consequent':'1','delay':0,'provenance':'controlled_monitor_only'}
    for v in ['correct','buggy']:
        r=run(d,c,None,'observation_control/filter_sequences',v,rows=controlled_filter_rows());sources.append(('filter',ROOT/r['run_id'],'controlled_input_enumeration_128_sequences'))
    output=[];witnessid=0
    for k in IDS:
        d=definition(k)
        for view in views(k):
            samples=[]
            for kk,folder,origin in sources:
                if kk!=k:continue
                tr=read(folder/'trace.json');rows=read(folder/'input.json');obs=adjudicate(d,tr,view);history=[]
                for t,o in zip(tr,obs):
                    if not t[d['rst']]:history=[];continue
                    history.append(tuple(t[s] for s in d['observation_base']))
                    legal=strict_prefix(d,rows,tr,obs,t['cycle'])
                    samples.append({'run':rel(folder),'cycle':t['cycle'],'history':list(history),'strict_label':legal,'violation':bool(o['violations']),'origin':origin})
            for depth in [0,1,2,3,'complete']:
                groups={}
                for s in samples:
                    hist=s['history'] if depth=='complete' else s['history'][-depth-1:]
                    if depth!='complete':hist=[tuple(0 for _ in d['observation_base'])]*max(0,depth+1-len(hist))+hist
                    group=groups.setdefault(tuple(hist),{'legal':[],'violation':[]})
                    if s['strict_label']['legal_prefix']:group['legal'].append(s)
                    if s['violation']:group['violation'].append(s)
                conflicts=[]
                for key,g in groups.items():
                    if not g['legal'] or not g['violation']:continue
                    a,b=g['legal'][0],g['violation'][0];witnessid+=1;folder=OUT/'observations/witnesses'/f'w{witnessid:04d}';folder.mkdir(parents=True,exist_ok=True)
                    for side,x in [('legal',a),('violation',b)]:
                        src=ROOT/x['run'];tr=read(src/'trace.json');obs=adjudicate(d,tr,view)
                        dump(folder/(side+'_input.json'),read(src/'input.json'))
                        dump(folder/(side+'_complete_history.json'),x['history']);dump(folder/(side+'_key_cycles.json'),tr[:x['cycle']+1]);dump(folder/(side+'_obligations.json'),obs[:x['cycle']+1])
                    rec={'id':f'w{witnessid:04d}','case':k,'view':view,'allowed_signals':d['observation_base'],'allowed_history_depth':depth,'equal_entire_allowed_history':True,'compared_history':key,'legal':a,'violation':b,
                         'legal_wave':rel(ROOT/a['run']/'wave.vcd'),'violation_wave':rel(ROOT/b['run']/'wave.vcd'),
                         'controlled':a['origin'].startswith('controlled') or b['origin'].startswith('controlled'),'spec_unresolved':k in ['spill','intr']}
                    # Compare both saved complete prefixes under successively larger allowed memories.
                    refinements=[]
                    for h in [1,2,3,'complete']:
                        ah=a['history'] if h=='complete' else a['history'][-h-1:];bh=b['history'] if h=='complete' else b['history'][-h-1:]
                        if h!='complete':
                            z=tuple(0 for _ in d['observation_base']);ah=[z]*max(0,h+1-len(ah))+ah;bh=[z]*max(0,h+1-len(bh))+bh
                        refinements.append({'depth':h,'same':ah==bh,'register_bits':None if h=='complete' else h*sum({**d['inputs'],**d['outputs']}[n] for n in d['observation_base'])})
                    rec['history_refinement']=refinements
                    rec['signal_refinement']={'status':'no_extra_public_port_authorized','extra_bits':0,'reason':'Already using every frozen public observation signal. Debug internals remain prohibited; signal-extension experiment separately uses input-only control.'}
                    dump(folder/'witness.json',rec);conflicts.append(rel(folder/'witness.json'))
                output.append({'case':k,'parent_bug_id':IDS[k],'view':view,'depth':depth,'sample_count':len(samples),'conflict_count':len(conflicts),'witnesses':conflicts,'status':'found' if conflicts else 'not_found_in_checked_executions','scope':'only saved prefixes and listed initialization/history; no unrestricted UNSAT claim'})
    dump(OUT/'observations/strict_history_search.json',output)
    # Previously executed input-only and onehot finite-grammar controls have unchanged
    # RTL/labels. Retain their exact raw evidence rather than inventing new samples.
    previous=read(OLD/'observation.json');controls=[]
    for p in previous['actual_pairs']:
        k=p['case'];d=definition(k);a=read(ROOT/p['execution_a']);b=read(ROOT/p['execution_b'])
        tr_a=read(ROOT/a['trace']);tr_b=read(ROOT/b['trace'])
        for view in views(k):
            la=adjudicate(d,tr_a,view);lb=adjudicate(d,tr_b,view)
            legal=not any(x['violations'] for x in la)
            equal=all(all(x[s]==y[s] for s in p['allowed_signals']) for x,y in zip(tr_a,tr_b)) and len(tr_a)==len(tr_b)
            controls.append({**p,'view':view,'origin':'controlled_restriction_to_inputs_only','strict_reference_legal':legal,'complete_allowed_history_equal':equal,'violation_execution_has_target':any(x['violations'] for x in lb),'status':'strict_collision' if legal and equal and any(x['violations'] for x in lb) else 'not_a_strict_pair_under_this_view'})
    dump(OUT/'observations/input_only_controls.json',controls)
    dump(OUT/'observations/finite_grammar_control_reuse.json',{'source':rel(OLD/'observation.json'),'sha256':sha(OLD/'observation.json'),'control':previous['controlled_abstraction'],'scope':'same 16 truth functions on boolean(oh_i),err_o; no general syntax solver invoked'})
    log('strict_observation_search_complete',witnesses=witnessid)

def collision_relabel():
    out=[]
    for p in read(OLD/'collision_pairs.json'):
        k=next(k for k,v in IDS.items() if v==p['parent_bug_id']);d=definition(k);items=[]
        for r in read(OLD/'all_runs.json'):
            if r['case']!=k or '/e12/' not in r['run_id'] or r['status']!='ok':continue
            cs={c['id']:c for c in r['candidates']}
            if p['a'] not in cs or p['b'] not in cs:continue
            tr=read(ROOT/r['trace']);rows=read(ROOT/r['input'])
            for view in views(k):
                obs=adjudicate(d,tr,view);viol={o['cycle'] for o in obs if o['violations']};res={}
                for name in ['a','b']:
                    c=cs[p[name]];fails=set(c['failure_cycles'])
                    res[name]={'fail_hit':c['fail_hit'],'first_failure_cycle':c['first_failure_cycle'],'fp':sorted(fails-viol) if r['variant']=='correct' else [],'miss':sorted(viol-fails),'trigger_count':c['trigger_count']}
                semantic=res['a']['fp']!=res['b']['fp'] or res['a']['miss']!=res['b']['miss']
                if semantic or res['a']['fail_hit']!=res['b']['fail_hit']:
                    items.append({'run':r['run_id'],'view':view,'input':r['input'],'wave':rel(ROOT/r['run_id']/'wave.vcd'),'legal_environment':not legality(d,rows),'result':res,'conclusion':'different_checked_acceptance_or_coverage_sets' if semantic else 'execution_difference_only','spec_unresolved':k in ['spill','intr']})
        out.append({**{n:p[n] for n in ['pair_id','parent_bug_id','a','b','assertion_a','assertion_b','old_signature','natural_pair']},'contract':rel(OUT/'frozen'/k/'contract.json'),'reused_original_checker_results':True,'evidence':items,'quality_order':'not_inferred'})
    dump(OUT/'collision_relabel.json',out)
    dump(OUT/'window_reuse.json',{'source':rel(OLD/'window_results.json'),'sha256':sha(OLD/'window_results.json'),'comparisons':12,'rank_changes':0,'reason':'fail-hit ranking, sampled input and RTL/checker unchanged; new specification interpretations affect quality labels, not this execution-only negative result','independent_violation_count':'unknown'})

if __name__=='__main__':audit_original_witnesses();search();collision_relabel()
