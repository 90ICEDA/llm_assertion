"""Freeze final candidates and execute independent regression and component controls."""
import copy, hashlib, json
from run_contract_v2 import OUT,OLD,ROOT,engine,read,dump,rel,sha,log,stamp,run,definition,IDS,ARMS,check_freeze
from contract_v2_spec import views,adjudicate,legality,components,branches,trigger_branches

def signature(c):return hashlib.sha256(json.dumps({n:c.get(n) for n in ['antecedent','consequent','delay','syntax_status']},sort_keys=True).encode()).hexdigest()[:16]

def make_plan():
    folder=OUT/'independent_plan';folder.mkdir(exist_ok=True)
    controls=[]
    replacements=[('fifo','force_empty_when_present','assign empty_o=~push_i;',"assign empty_o=1'b1;",['nonempty_when_present'],'buggy'),
      ('spill','valid_only','else if(flush_i) begin valid_o<=0;data_o<=0; end','else if(flush_i) begin valid_o<=push_i;data_o<=0; end',['collision_empty'],'buggy'),
      ('spill','raw_payload','else if(flush_i) begin valid_o<=0;data_o<=0; end','else if(flush_i) begin valid_o<=0;data_o<=data_i; end',['payload_not_exposed'],'correct'),
      ('stat','drop_valid','assign stat_valid_o=valid_pipe[1];',"assign stat_valid_o=1'b0;",['valid_latency'],'buggy'),
      ('stat','corrupt_length','if(frame_done_i) stat_len_o<=frame_len_i;','if(frame_done_i) stat_len_o<=0;',['captured_length'],'buggy')]
    for k,name,a,b,target,variant in replacements:
        source=OUT/'frozen'/k/'correct.v';text=source.read_text();assert a in text,(k,name)
        p=folder/(k+'_'+name+'.v');p.write_text(text.replace(a,b))
        controls.append({'case':k,'name':name,'rtl':rel(p),'rtl_sha256':sha(p),'target_components':target,'variant_label':variant,
                         'provenance':'supplemental_control_mutant_not_natural_or_historical','source':rel(source),'replacement_from':a,'replacement_to':b})
    plan={'time':stamp(),'controls':controls,'scenario_inputs':'protocol-frozen hidden_transactions, hidden_reset, hidden_boundary',
          'parameters':{'fifo':{'DataWidth':4,'Depth':0},'filter':{'CntWidth':3,'thresh_i':5}},
          'legal_variant':{'case':'onehot','StrictCheck':0,'source':'upstream parameter comments; zero vector with en=1 may legally differ from StrictCheck=1'},
          'equivalent_rewrite':'internal alpha-renaming or unused wire; compare exact public port histories with same input',
          'applicability':{k:{'continuous_transactions':True,'backpressure':'applicable to Depth=0 presented-item stability' if k=='fifo' else 'not_applicable: no ready/backpressure interface in this wrapper',
                          'reset':True,'interrupt':'applicable' if k=='intr' else 'reset/flush interruption where applicable; no IRQ interface',
                          'boundary':True,'parameter_change':'actual rebuild' if k in ['fifo','filter','onehot'] else 'not_applicable: no exposed varying parameter in frozen wrapper',
                          'behavior_changing_legal_variant':'StrictCheck=0' if k=='onehot' else 'no independently specified additional variant; spill conditional raw-payload control is NOT called unconditionally legal'} for k in IDS}}
    dump(folder/'plan.json',plan)
    dump(folder/'freeze.json',{'time':stamp(),'before_hidden_results':not (OUT/'hidden_evaluations.json').exists(),'hashes':{rel(p):sha(p) for p in folder.glob('*') if p.is_file() and p.name!='freeze.json'}})
    return plan

def custom_run(d,c,rows,label,control):
    folder=OUT/'runs'/label/d['key']/control['variant_label']
    if (folder/'result.json').exists():return read(folder/'result.json')
    source=ROOT/control['rtl'];engine.sources=lambda dd:(source,source)
    r=engine.execute_run(d,rows,[c],label,control['variant_label']);r['component_control']=control
    if r['status']=='ok':
        tr=read(ROOT/r['trace']);vv={v:adjudicate(d,tr,v) for v in views(d['key'])};dump(folder/'contract_views.json',vv);r['contract_views']=rel(folder/'contract_views.json')
    dump(folder/'legality.json',{'valid':not legality(d,rows),'issues':legality(d,rows)})
    dump(folder/'result.json',r);return r

def evaluate_one(k,c,plan):
    key=signature(c);dest=OUT/'hidden_cache'/k/(key+'.json')
    if dest.exists():return read(dest)
    d=definition(k);rr=[];label=f'hidden/{key}'
    for kind in ['transactions','reset','boundary']:
        rows=read(OUT/'frozen'/k/('hidden_'+kind+'.json'))
        for v in ['correct','buggy']:rr.append(run(d,c,None,label+'/'+kind,v,rows=rows))
    rows=read(OUT/'frozen'/k/'hidden_transactions.json')
    if k in ['fifo','filter']:
        param={'DataWidth':4} if k=='fifo' else {'CntWidth':3};pr=copy.deepcopy(rows)
        for row in pr:
            if k=='fifo':row['data_i']&=15
            else:row['thresh_i']=5
        for v in ['correct','buggy']:rr.append(run(d,c,None,label+'/parameters',v,rows=pr,param=param))
    rr.append(run(d,c,None,label+'/equivalent_rewrite',rows=rows,rewrite=True))
    if k=='onehot':rr.append(run(d,c,None,label+'/legal_variant',rows=rows,param={'StrictCheck':0}))
    for control in plan['controls']:
        if control['case']!=k:continue
        cr=copy.deepcopy(rows)
        if k=='stat':
            # Use the four presealed isolated events, before the consecutive
            # segment; the unmodified fixed length-register issue must not
            # contaminate the component-isolating mutant check.
            cr=cr[:22]
        if k=='spill' and control['name']=='valid_only':
            # Nonzero payload makes valid=1,data=0 isolate the empty obligation.
            cr=cr[:2]+cr[8:14]
        for i,row in enumerate(cr):row['cycle']=i
        rr.append(custom_run(d,c,cr,label+'/component_'+control['name'],control))
    rec={'case':k,'expression_signature':key,'candidate':c,'run_ids':[r['run_id'] for r in rr],'evaluated_at':stamp(),'scope':'new presealed hidden inputs plus explicitly isolated component controls','cached_reuse':False}
    dump(dest,rec);return rec

def hidden():
    check_freeze();mf=read(OUT/'method_freeze.json')
    for p,h in mf['hashes'].items():assert sha(ROOT/p)==h
    assert len(list((OUT/'methods').glob('*/*/final.json')))==len(IDS)*len(ARMS)
    plan=read(OUT/'independent_plan/plan.json') if (OUT/'independent_plan/freeze.json').exists() else make_plan()
    planfreeze=read(OUT/'independent_plan/freeze.json')
    for p,h in planfreeze['hashes'].items():assert sha(ROOT/p)==h
    log('hidden_access_started',method_freeze_sha256=sha(OUT/'method_freeze.json'),plan_sha256=sha(OUT/'independent_plan/plan.json'))
    index=[]
    for path in sorted((OUT/'methods').glob('*/*/final.json')):
        m=read(path)
        for cp in m['checkpoints']:
            e=evaluate_one(m['case'],cp['candidate'],plan)
            index.append({'case':m['case'],'parent_bug_id':m['parent_bug_id'],'arm':m['arm'],'step':cp['step'],'checkpoint':cp,'evaluation':e,'final':cp is m['checkpoints'][-1],
                         'candidate_to_actual_checker':'physical traces may be shared only for byte-identical expressions/delay/support status; candidate identity and generation chain remain in checkpoint'})
    dump(OUT/'hidden_evaluations.json',index);log('hidden_access_finished',checkpoints=len(index),physical_unique_candidates=len({(r['case'],r['evaluation']['expression_signature']) for r in index}))

if __name__=='__main__':hidden()
