#!/usr/bin/env python3
"""Reproducible actual-RTL contract audit; all verdicts derive from saved logs.

Commands: pilot, freeze, model-pool, experiments, methods, report, audit.
No credentials, remote services, generated historical claims, or source mutation.
"""
import argparse,csv,hashlib,itertools,json,os,re,shlex,shutil,subprocess,sys,time,urllib.request,functools
from pathlib import Path
from repair_contract_cases import ROOT,NAT,IDS,definition,sources,schedule,oracle,controlled_candidate
OUT=ROOT/'deliverables/repair_contract_20261009'
SEED=20261009
MODEL='qwen2.5-coder:7b-instruct'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return str(Path(p).relative_to(ROOT))
def append(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
def command(cmd,d,name,timeout=45):
 t=time.perf_counter(); result={'argv':list(map(str,cmd)),'cwd':str(d),'timeout_seconds':timeout}
 try:
  p=subprocess.run(result['argv'],cwd=d,capture_output=True,text=True,timeout=timeout)
  result.update(exit_code=p.returncode,status='ok' if p.returncode==0 else 'tool_error');stdout,stderr=p.stdout,p.stderr
 except subprocess.TimeoutExpired as e:
  result.update(exit_code=None,status='timeout');stdout,stderr=e.stdout or '',e.stderr or ''
 except OSError as e:result.update(exit_code=None,status='tool_error');stdout,stderr='',str(e)
 for n,v in [('stdout',stdout),('stderr',stderr)]:
  p=d/(name+'.'+n);p.write_text(v.decode(errors='replace') if isinstance(v,bytes) else v);result[n]=rel(p)
 result['wall_seconds']=time.perf_counter()-t;dump(d/(name+'.command.json'),result)
 return result

@functools.lru_cache(maxsize=None)
def natural(k):
 out=[];parent=NAT/IDS[k]
 for p in sorted(parent.glob('slot_*/attempt_01/evidence.json')):
  e=read(p);a=e['ast'];s=a['antecedent_signal'];v=a['consequent_signal']
  ant=s if a['antecedent_polarity']=='high' else '!'+s
  if e['slot']==8:ant=f'({s} && !{s})'
  cons={'high':v,'low':'!'+v,'equal':f'({v} == {s})','not_equal':f'({v} != {s})'}[a['relation']]
  out.append({'id':f'slot_{e["slot"]:02d}','antecedent':ant,'consequent':cons,'delay':int(a['implication']=='|=>'),'original_sva':e['sva'],'evidence':rel(p),'sha256':sha(p),'provenance':'synthetic_contradiction_control' if e['slot']==8 else 'legacy_natural_model_output','legacy_model':read(p.parent/'request.json')['model']})
 return out

def sva(d,c):
 # pN_ are explicit reset-to-zero observation registers in checker_tb.sv,
 # not native $past (whose reset semantics would differ).
 def cv(s):return s
 implication='|->' if c['delay']==0 else '|=>' if c['delay']==1 else '|-> ##'+str(c['delay'])
 return c.get('original_sva') or f'assert property (@(posedge {d["clk"]}) disable iff (!{d["rst"]}) ({cv(c["antecedent"])}) {implication} ({cv(c["consequent"])}));'

def tb_text(d,rows,candidates,param=None):
 clk,rst=d['clk'],d['rst'];inputs=dict(d['inputs']);outputs=dict(d['outputs']);k=d['key']
 if param and k=='fifo':inputs['data_i']=outputs['data_o']=param['DataWidth']
 if param and k=='filter':inputs['thresh_i']=param['CntWidth']
 def decl(typ,n,w):return f'{typ} '+(f'[{w-1}:0] ' if w>1 else '')+n+';'
 lines=['`timescale 1ns/1ps','module tb;',f'reg {clk}=0; always #5 {clk}=~{clk};',f'reg {rst}=0;', 'integer cycle=0;']
 lines += [decl('reg',n,w) for n,w in inputs.items()]+[decl('reg' if k=='intr' and n=='reg2hw_intr_state_q_i' else 'wire',n,w) for n,w in outputs.items()]
 aliases={'q_o':'valid_o'} if k=='spill' else {}
 for a,b in aliases.items():lines.append(f'wire {a}={b};')
 ports=[clk,rst]+list(inputs)+list(outputs)
 if k=='intr':ports.remove('sw_clear');lines.append(f'always @(posedge {clk} or negedge {rst}) if(!{rst}) reg2hw_intr_state_q_i<=0; else if(sw_clear) reg2hw_intr_state_q_i<=0; else if(hw2reg_intr_state_de_o) reg2hw_intr_state_q_i<=hw2reg_intr_state_d_o;')
 parameters=f'#(.DataWidth({inputs["data_i"]}),.Depth(0))' if k=='fifo' else ''
 lines.append(f'{d["module"]} {parameters} dut('+','.join(f'.{n}({n})' for n in ports)+');')
 allsignals={**inputs,**outputs,**{a:outputs[b] for a,b in aliases.items()}}
 for depth in (1,2,3):
  for n,w in allsignals.items():lines.append(decl('reg',f'p{depth}_{n}',w))
 lines.append(f'always @(posedge {clk}) begin')
 for n in allsignals:
  for depth in (1,2,3):lines.append(f'p{depth}_{n} <= !{rst} ? 0 : '+(n if depth==1 else f'p{depth-1}_{n}')+';')
 lines.append('end')
 names=[rst]+list(inputs)+list(outputs)
 lines.append(f'always @(posedge {clk}) begin $display("TRACE %0d '+ ' '.join(n+'=%0d' for n in names)+'",cycle,'+','.join(names)+'); cycle<=cycle+1; end')
 for j,c in enumerate(candidates):
  a,b=c['antecedent'],c['consequent'];ante=f'ad{j}' if c['delay'] else f'({a})'
  lines += [f'reg ad{j}=0;',f'always @(posedge {clk} or negedge {rst}) begin if(!{rst}) ad{j}<=0; else begin',f'$display("CHECK {j} %0d %0d %0d",cycle, (({a}) ? 1 : 0), (({ante}) && !({b})) ? 1 : 0);',f"ad{j}<=(({a}) ? 1'b1 : 1'b0); end end"]
 lines += ['initial begin','$dumpfile("wave.vcd"); $dumpvars(0,tb);']
 for n in inputs:lines.append(f'{n}=0;')
 # Initialize at time zero then every following negedge; end after a full final edge.
 for i,r in enumerate(rows):
  if i:lines.append(f'@(negedge {clk});')
  for n in [rst]+list(inputs):lines.append(f'{n}={r[n]};')
 lines += [f'@(negedge {clk}); $finish; end','endmodule']
 return '\n'.join(lines)+'\n'

def execute_run(d,rows,candidates,label,variant='correct',param=None,rewrite=False,invalid_bus_variant=False,controlled_mutation=None):
 rd=OUT/'runs'/label/d['key']/variant;rd.mkdir(parents=True,exist_ok=True)
 if (rd/'result.json').exists():
  previous=read(rd/'result.json')
  if previous['status']=='ok':return previous
  archive=OUT/'failed_attempts'/(label.replace('/','_')+'_'+d['key']+'_'+variant+'_'+str(time.time_ns()))
  archive.parent.mkdir(parents=True,exist_ok=True)
  assert rd.resolve().is_relative_to(OUT.resolve()) and archive.resolve().is_relative_to(OUT.resolve())
  shutil.move(str(rd),str(archive));rd.mkdir(parents=True,exist_ok=True)
 dump(rd/'input.json',rows);dump(rd/'candidates.json',candidates);dump(rd/'definition.json',d)
 (rd/'assertions.sva').write_text('\n'.join(sva(d,c) for c in candidates)+'\n')
 src=sources(d)[variant=='buggy' and not controlled_mutation];text=src.read_text()
 if controlled_mutation=='spill_valid_only':
  assert d['key']=='spill';text=text.replace('else if(flush_i) begin valid_o<=0;data_o<=0; end','else if(flush_i) begin valid_o<=push_i;data_o<=0; end')
 elif controlled_mutation=='stat_drop_valid':
  assert d['key']=='stat';text=text.replace('assign stat_valid_o=valid_pipe[1];',"assign stat_valid_o=1'b0;")
 elif controlled_mutation=='stat_corrupt_length':
  assert d['key']=='stat';text=text.replace('if(frame_done_i) stat_len_o<=frame_len_i;','if(frame_done_i) stat_len_o<=0;')
 if param and d['key']=='filter':
  text=text.replace('logic [1:0] thresh_i','logic [2:0] thresh_i').replace('.CntWidth(2)',f'.CntWidth({param["CntWidth"]})')
 if param and d['key']=='onehot' and 'StrictCheck' in param:
  text=text.replace('.StrictCheck(1)',f'.StrictCheck({param["StrictCheck"]})')
 if rewrite:
  # Alpha-renaming an internal identifier is a structural equivalence control.
  target={'onehot':'err_tree','filter':'diff_ctr_q','fifo':'cc_fifo','spill':'cc_spill_register_flushable','stat':'valid_pipe','intr':'status'}[d['key']]
  if target==d['module']:text=text.replace('endmodule','wire structure_control_unused=1\'b0; endmodule')
  else:text=re.sub(r'\b'+target+r'\b',target+'_renamed',text)
 if invalid_bus_variant:
  assert d['key']=='spill';text=text.replace('else if(flush_i) begin valid_o<=0;data_o<=0; end','else if(flush_i) begin valid_o<=0;data_o<=8\'ha5; end')
 (rd/'rtl.v').write_text(text);(rd/'checker_tb.sv').write_text(tb_text(d,rows,candidates,param))
 build=command(['iverilog','-g2012','-s','tb','-I',str(src.parent),'-I',str(ROOT/'external/common_cells/include'),'-o','sim.out','rtl.v','checker_tb.sv'],rd,'compile')
 syntax_invalid=any(c.get('syntax_status')=='unsupported_syntax' for c in candidates)
 if build['status']=='tool_error':
  err=(rd/'compile.stderr').read_text()
  if re.search(r'syntax error|Unable to bind|No function|not a valid|elaboration',err,re.I):build['status']='unsupported_syntax'
 sim=command(['vvp','sim.out'],rd,'simulate',15) if build['status']=='ok' and not syntax_invalid else None
 result={'run_id':rel(rd),'parent_bug_id':d['parent_bug_id'],'case':d['key'],'variant':variant,'input':rel(rd/'input.json'),'checker':rel(rd/'checker_tb.sv'),'assertions':rel(rd/'assertions.sva'),'source_rtl':rel(src),'rtl_sha256':sha(rd/'rtl.v'),'input_sha256':sha(rd/'input.json'),'checker_sha256':sha(rd/'checker_tb.sv'),'parameters':param,'rewrite':rewrite,'legal_behavior_variant':invalid_bus_variant,'compile':build,'simulate':sim,'status':build['status'] if not sim else sim['status'],'candidates':[]}
 result['controlled_mutation']=controlled_mutation
 if syntax_invalid:result['status']='unsupported_syntax'
 trace=[];checks={j:[] for j in range(len(candidates))}
 if sim and sim['status']=='ok':
  for line in (rd/'simulate.stdout').read_text().splitlines():
   if line.startswith('TRACE '):
    parts=line.split();t={'cycle':int(parts[1])}
    for s in parts[2:]:n,v=s.split('=');t[n]=int(v) if re.fullmatch(r'-?\d+',v) else None
    trace.append(t)
   if line.startswith('CHECK '):
    _,j,cycle,a,f=line.split();checks[int(j)].append({'cycle':int(cycle),'trigger':int(a) if a.isdigit() else None,'fail':int(f) if f.isdigit() else None})
  if len(trace)!=len(rows) or any(t[n] is None for t in trace if t[d['rst']] for n in t):result['status']='unknown_values_or_incomplete_trace'
  else:
   obligations=oracle(d,trace);dump(rd/'trace.json',trace);dump(rd/'obligation_cycles.json',obligations)
   violations=[t['cycle'] for t in obligations if t['violations']]
   result.update(obligation_violation_cycles=violations,obligation_trigger_cycles=[t['cycle'] for t in obligations if t['trigger']],independent_violation_count='unknown',trace=rel(rd/'trace.json'),obligations=rel(rd/'obligation_cycles.json'))
   for j,c in enumerate(candidates):
    cc=checks[j];fails=[t['cycle'] for t in cc if t['fail']==1];ants=[t['cycle'] for t in cc if t['trigger']==1]
    unknown=any(t['fail'] is None or t['trigger'] is None for t in cc)
    fps=[x for x in fails if x not in violations] if variant=='correct' else [];miss=[x for x in violations if x not in fails]
    result['candidates'].append({'id':c['id'],'provenance':c['provenance'],'trigger_count':len(ants),'fail_hit':len(fails),'first_failure_cycle':fails[0] if fails else None,'first_failure_stimulus':rows[fails[0]]['stimulus_id'] if fails else None,'failure_cycles':fails,'trigger_cycles':ants,'false_positive_cycles':fps,'missed_violation_cycles':miss,'covered_violation_cycles':sorted(set(fails)&set(violations)),'status':'unknown' if unknown else 'measured','nonempty':bool(ants),'classification':'unknown' if unknown else ('false_positive' if fps else 'miss' if miss else 'not_triggered' if not ants else 'passes_observed_obligations')})
    dump(rd/f'checker_{j}_cycles.json',cc)
 result['validation_wall_seconds']=build['wall_seconds']+(sim['wall_seconds'] if sim else 0)
 (rd/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd '+shlex.quote(str(rd))+'\n'+shlex.join(build['argv'])+'\n'+('vvp sim.out\n' if sim else ''))
 dump(rd/'result.json',result);append(OUT/'run_index.jsonl',{'run_id':result['run_id'],'status':result['status'],'result':rel(rd/'result.json')})
 print('RUN',label,d['key'],variant,result['status'],flush=True)
 return result

def pilot():
 out=[]
 for k in ['onehot','filter','fifo']:
  d=definition(k);cs=natural(k) or [controlled_candidate(k)]
  for v in ['correct','buggy']:out.append(execute_run(d,schedule(d),cs,'pilot',v))
 dump(OUT/'pilot.json',{'runs':[r['run_id'] for r in out],'all_executable':all(r['status']=='ok' for r in out),'fixed_oracle_violations':{r['case']:r.get('obligation_violation_cycles') for r in out if r['variant']=='correct'},'buggy_oracle_violations':{r['case']:r.get('obligation_violation_cycles') for r in out if r['variant']=='buggy'}})

def freeze():
 p=read(OUT/'pilot.json');assert p['all_executable'] and all(not v for v in p['fixed_oracle_violations'].values()),'pilot must be repaired first'
 if (OUT/'freeze.json').exists():print('already frozen');return
 versions={}
 for cmd in [['iverilog','-V'],['vvp','-V'],['yosys','-V'],['ollama','--version'],['git','rev-parse','HEAD']]:
  r=command(cmd,OUT,'version_'+cmd[0]);versions[cmd[0]]=r
 cases=[]
 for k in IDS:
  d=definition(k);cs=natural(k);folder=OUT/'frozen'/k;folder.mkdir(parents=True,exist_ok=True)
  for v,src in zip(['correct','buggy'],sources(d)):shutil.copyfile(src,folder/(v+'.v'))
  dump(folder/'legacy_candidates.json',cs);dump(folder/'obligation.json',d)
  for c in cs:
   src=ROOT/c['evidence'];dest=folder/c['id'];dest.mkdir(exist_ok=True)
   for n in ['evidence.json','candidate.sva','checker.sv','request.json','raw_response.json']:
    if (src.parent/n).exists():shutil.copyfile(src.parent/n,dest/n)
  for kind in ['train','held','regression','reset']:dump(folder/(kind+'_inputs.json'),schedule(d,kind,seed=SEED+sum(map(ord,kind))))
  cases.append({'parent_bug_id':IDS[k],'case':k,'natural_candidates':len([c for c in cs if c['provenance']=='legacy_natural_model_output']),'control_candidates':len([c for c in cs if c['provenance']=='synthetic_contradiction_control']),'historical_fix':'unknown','source_hashes':{rel(s):sha(s) for s in sources(d)}})
 for name in ['pairs.jsonl','repair_obligations.json']:shutil.copyfile(ROOT/'deliverables/feedback_collision_reaudit_20261002'/name,OUT/'frozen'/name)
 hashes={rel(p):sha(p) for p in (OUT/'frozen').rglob('*') if p.is_file()}
 config={'seed':SEED,'model':MODEL,'temperature':0.2,'num_predict':256,'num_ctx':4096,'generation_candidates':3,'max_repair_calls':2,'call_timeout_seconds':180,'validation_timeout_seconds':45,'H':24,'case_count':len(cases),'legacy_pool_model':'qwen3-8b-pilot:q4_K_M (not installed locally)','natural_cohort_scope':'five existing slot-pool parents plus filter-counter pilot without old slot pool; six parent bugs total','model_comparison_pool':'new frozen qwen2.5 pool, separate from legacy collision pool','initial_observation':'listed external signals, p1/p2/p3 history prohibited; delay=1 allowed','refined_observation':'same ports plus p1/p2/p3 register copies','unknown_rule':'exclude unknown from numerator AND denominator; report count separately','legal_variant':'spill invalid payload may differ while valid=0; this interpretation is scoped explicitly','independent_violation_counts':'unknown; per-cycle obligation violations are not independent bug samples'}
 dump(OUT/'config.json',config);dump(OUT/'freeze.json',{'timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'cases':cases,'hashes':hashes,'versions':versions,'config_sha256':sha(OUT/'config.json'),'git_version':'unknown: .git contains no usable HEAD','AGENTS':'searched repository and parent directories; none found','pilot':p})

def valid_candidate(c,d,history):
 assert isinstance(c,dict)
 assert set(c)>={'antecedent','consequent','delay'} and type(c['delay']) is int and c['delay'] in (0,1)
 allowed=set(d['observation_base'])
 if history:allowed|={f'p{j}_{n}' for j in (1,2,3) for n in d['observation_base']}
 for key in ['antecedent','consequent']:
  s=c[key];assert isinstance(s,str) and len(s)<1200 and not re.search(r'[;`@$"\\]|//|/\*',s),'unsupported_expression'
  words=set(re.findall(r'\b[A-Za-z_]\w*',re.sub(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+",'0',s)))
  assert words<=allowed, 'signal_or_history_not_allowed:'+str(words-allowed)
 return {key:c[key] for key in ['antecedent','consequent','delay']}

def call_model(d,prompt,call_id,history=False):
 folder=OUT/'model_calls'/call_id;folder.mkdir(parents=True,exist_ok=True)
 if (folder/'result.json').exists():
  result=read(folder/'result.json')
  # Retain safe, structurally valid but unsupported model expressions so that
  # feedback arms can actually attempt syntax repair instead of dropping them.
  if result['candidate'] is None and result['status']=='unsupported_syntax' and (folder/'response.raw.json').exists():
   try:
    env=read(folder/'response.raw.json');c=json.loads(env['message']['content'])
    if safe_raw_candidate(c):
     c.update(id=call_id.replace('/','_'),provenance='new_model_generated',syntax_status='unsupported_syntax');result['candidate']=c
     result['prompt_tokens']=env.get('prompt_eval_count');result['completion_tokens']=env.get('eval_count');dump(folder/'result.json',result)
   except (ValueError,KeyError,TypeError):pass
  return result
 req={'model':MODEL,'stream':False,'format':'json','messages':[{'role':'system','content':'Generate one assertion represented by JSON with exactly keys antecedent (SystemVerilog expression string), consequent (SystemVerilog expression string), delay (integer 0 for same sample or 1 for next sample). No prose. Use expressions, not statements. Do not use $ functions. History references use p1_SIGNAL, p2_SIGNAL, p3_SIGNAL ONLY if permitted. Numeric unsized decimal literals allowed.'},{'role':'user','content':prompt}],'options':{'seed':SEED,'temperature':0.2,'num_predict':192,'num_ctx':4096,'num_gpu':0,'num_thread':8}}
 dump(folder/'request.json',req);(folder/'prompt.txt').write_text(prompt);t=time.perf_counter()
 result={'call_id':call_id,'request':rel(folder/'request.json'),'model':MODEL,'status':'unknown','candidate':None}
 try:
  request=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(req).encode(),headers={'Content-Type':'application/json'})
  raw=urllib.request.urlopen(request,timeout=180).read();(folder/'response.raw.json').write_bytes(raw);env=json.loads(raw);result.update(prompt_tokens=env.get('prompt_eval_count'),completion_tokens=env.get('eval_count'));c=valid_candidate(json.loads(env['message']['content']),d,history)
  c.update(id=call_id.replace('/','_'),provenance='new_model_generated');result.update(status='generated',candidate=c,prompt_tokens=env.get('prompt_eval_count'),completion_tokens=env.get('eval_count'),total_duration_ns=env.get('total_duration'))
 except urllib.error.HTTPError as e:
  (folder/'error_response.txt').write_bytes(e.read());result.update(status='tool_error',error=repr(e))
 except (AssertionError,KeyError,TypeError,ValueError) as e:
  result.update(status='unsupported_syntax',error=repr(e))
  try:
   c=json.loads(env['message']['content'])
   if safe_raw_candidate(c):c.update(id=call_id.replace('/','_'),provenance='new_model_generated',syntax_status='unsupported_syntax');result['candidate']=c
  except (KeyError,ValueError,TypeError,UnboundLocalError):pass
 except Exception as e:result.update(status='timeout' if isinstance(e,TimeoutError) else 'tool_error',error=repr(e))
 result['wall_seconds']=time.perf_counter()-t;dump(folder/'result.json',result);print('MODEL',call_id,result['status'],round(result['wall_seconds'],2),flush=True);return result

def safe_raw_candidate(c):
 return (isinstance(c,dict) and set(c)>={'antecedent','consequent','delay'} and type(c['delay']) is int and 0<=c['delay']<=16
  and all(isinstance(c[k],str) and len(c[k])<1200 and not re.search(r'[;`@$"\\]|//|/\*',c[k]) for k in ['antecedent','consequent']))

def base_prompt(d,history=False):
 return 'Generate an assertion protecting this contract. Signals: '+', '.join(d['observation_base'])+'. '+('History p1_, p2_, p3_ copies are available, e.g. p1_'+d['observation_base'][0]+'.' if history else 'No history copies are available; delay 0 or 1 is available.')+'\nClock/reset are supplied by harness. Observe before the rising-edge state update. No functions such as popcount exist in this expression language; use arithmetic, bitwise and comparison operators.\nContract: '+d['obligation']

def model_pool():
 assert (OUT/'freeze.json').exists()
 for k in IDS:
  d=definition(k);pool=[]
  for i in range(3):
   r=call_model(d,base_prompt(d)+f'\nCandidate {i+1} of 3. Produce a complete useful property.','pool/'+k+'/'+str(i))
   if r['candidate']:pool.append(r['candidate'])
  dump(OUT/'frozen'/k/'model_pool.json',pool)
 dump(OUT/'model_pool_freeze.json',{'model':MODEL,'files':{rel(p):sha(p) for p in (OUT/'frozen').glob('*/model_pool.json')},'calls':[rel(p) for p in (OUT/'model_calls/pool').rglob('result.json')]})

def experiments():
 for k in IDS:
  d=definition(k);cs=natural(k) or [controlled_candidate(k)]
  for kind in ['held','hold','more']:
   horizons=[24,48,96] if kind in ['hold','more'] else [24]
   for h in horizons:
    for v in ['correct','buggy']:execute_run(d,schedule(d,kind,h),cs,f'e12/{kind}_{h}',v)
  # Native concurrency syntax is separately parsed, not claimed executed by Icarus.
  for v in ['correct','buggy']:execute_run(d,schedule(d,'regression',seed=SEED+11),cs,'legacy_regression',v)
 observation_experiment()

def observation_experiment():
 # Actual RTL pair: same observed inputs but differing hidden error output.
 # This establishes impossibility ONLY for input-only observation at this horizon.
 found=[]
 for k in IDS:
  a=OUT/'runs/e12/hold_24'/k/'correct';b=OUT/'runs/e12/hold_24'/k/'buggy'
  if not (a/'trace.json').exists() or not (b/'trace.json').exists():continue
  ta,tb=read(a/'trace.json'),read(b/'trace.json');oa,ob=read(a/'obligation_cycles.json'),read(b/'obligation_cycles.json');d=definition(k)
  signals=list(d['inputs'])+[d['rst']];history_equal=all(all(x[s]==y[s] for s in signals) for x,y in zip(ta,tb)) and len(ta)==len(tb)
  label_a=any(x['violations'] for x in oa);label_b=any(x['violations'] for x in ob)
  extra=[s for s in d['outputs'] if s!='second_new_sample_dbg']
  enriched_equal=all(all(x[s]==y[s] for s in signals+extra) for x,y in zip(ta,tb))
  r={'case':k,'parent_bug_id':IDS[k],'status':'found' if history_equal and label_a!=label_b else 'not_found_in_checked_pair','allowed_signals':signals,'initialization':'reset asserted for first two samples','history':'complete trace from reset through H=24','full_history_equal':history_equal,'labels':[label_a,label_b],'execution_a':rel(a/'result.json'),'execution_b':rel(b/'result.json'),'after_add_signals':extra,'after_add_signals_equal':enriched_equal,'history_only_refinement':'cannot separate identical full input histories','cost_bits':sum(d['outputs'][s] for s in extra),'unsat_scope':'any deterministic classifier of identical observed history on THIS pair only; no claim about untested executions'}
  found.append(r)
 # Finite grammar exhaustive check for onehot with only Boolean truth of vector.
 # Rows obtained by running all 16 actual input vectors on both actual RTLs.
 d=definition('onehot');rows=schedule(d)[:2]
 for oh in range(16):
  rows.append({'cycle':len(rows),'stimulus_id':f'exhaustive:{oh}','rst_n':1,'oh_i':oh,'addr_i':(oh & -oh).bit_length()-1 if oh else 0,'en_i':int(bool(oh))})
 c=controlled_candidate('onehot');runs=[execute_run(d,rows,[c],'e3_exhaustive',v) for v in ['correct','buggy']]
 samples=[]
 for r in runs:
  if r['status']=='ok':
   tr=read(ROOT/r['trace']);ob=read(ROOT/r['obligations'])
   samples += [{'oh':t['oh_i'],'err':t['err_o'],'violation':bool(o['violations']),'run':r['run_id'],'cycle':t['cycle']} for t,o in zip(tr[2:],ob[2:])]
 groups={}
 for s in samples:groups.setdefault((bool(s['oh']),s['err']),[]).append(s)
 conflicts=[v for v in groups.values() if len({x['violation'] for x in v})>1]
 grammar=[]
 # Enumerate all 16 truth functions over two Boolean inputs, not just candidates.
 for mask in range(16):
  errors=sum(bool(mask & (1 << (2*bool(s['oh'])+s['err'])))!=s['violation'] for s in samples)
  grammar.append({'mask':mask,'errors':errors})
 dump(OUT/'observation.json',{'actual_pairs':found,'controlled_abstraction':{'provenance':'controlled_observation_abstraction_of_natural_RTL','signals':['boolean(oh_i)','err_o'],'history':0,'samples':samples,'conflicts':conflicts,'grammar_checked':grammar,'status':'finite_grammar_unsat' if all(g['errors'] for g in grammar) else 'solution_found','refinement':'observe full 4-bit oh_i; rule popcount(oh_i)>1 && !err_o labels all checked rows','refinement_errors':sum((s['oh'].bit_count()>1 and not s['err'])!=s['violation'] for s in samples),'additional_observation_bits':3},'global_expressibility':'unknown'})

def evaluate(d,candidates,tag,kinds=('train','held'),history=False):
 results=[]
 for kind in kinds:
  rows=read(OUT/'frozen'/d['key']/(kind+'_inputs.json'))
  for variant in ['correct','buggy']:results.append(execute_run(d,rows,candidates,tag+'/'+kind,variant))
 scores={c['id']:{'fp':0,'miss':0,'trigger':0,'covered':0,'unknown':0,'violations':0} for c in candidates}
 for r in results:
  if r['status']!='ok':
   for s in scores.values():s['unknown']+=1
   continue
  for x in r['candidates']:
   s=scores[x['id']];s['fp']+=len(x['false_positive_cycles']);s['miss']+=len(x['missed_violation_cycles']);s['trigger']+=x['trigger_count'];s['covered']+=len(x['covered_violation_cycles']);s['violations']+=len(r['obligation_violation_cycles']);s['unknown']+=x['status']=='unknown'
 return scores,results

def methods():
 assert (OUT/'model_pool_freeze.json').exists()
 arms=['first','equal_budget_select','existing_feedback','obligation_loop','generic_diff','no_fp_check','no_observation_refinement','equal_information_control']
 selected_keys=globals().get('CASE_FILTER') or list(IDS)
 methodrows=[read(p) for p in (OUT/'methods').glob('*/*/freeze.json') if p.parent.parent.name not in selected_keys]
 for k in IDS:
  if k not in selected_keys:continue
  d=definition(k);pool=read(OUT/'frozen'/k/'model_pool.json')
  if not pool:
   for arm in arms:methodrows.append({'case':k,'parent_bug_id':IDS[k],'arm':arm,'status':'unknown_no_generated_candidate'})
   continue
  scores={};initial_runs=[]
  for c in pool:
   ss,rr=evaluate(d,[c],'methods/pool/'+c['id']);scores.update(ss);initial_runs+=rr
  def rank(c,scores,ignore_fp=False):
   s=scores[c['id']];return(s['unknown'],0 if ignore_fp else s['fp'],s['miss'],not s['trigger'])
  for arm in arms:
   target=OUT/'methods'/k/arm/'freeze.json'
   if target.exists():methodrows.append(read(target));continue
   best=pool[0] if arm in ['first','existing_feedback','obligation_loop','generic_diff','no_fp_check','no_observation_refinement','equal_information_control'] else min(pool,key=lambda c:rank(c,scores))
   accepted=[best];rounds=[];call_paths=[];runs=[];history=False
   # Selection evaluates each frozen candidate once; feedback arms evaluate
   # initial + two proposed candidates on exactly the same four RTL/scenario cells.
   if arm=='equal_budget_select':runs=list(initial_runs)
   else:
    current,rs=evaluate(d,[best],f'methods/{arm}/initial');runs+=rs
   if arm not in ['first','equal_budget_select']:
    for step in range(2):
     s=current[best['id']]
     # Every round rechecks both initial and accumulated held witness inputs.
     if arm in ['obligation_loop','generic_diff','no_fp_check'] and step==1:history=True
     if arm=='equal_information_control':history=True
     feedback={'false_positive_cycles':s['fp'],'missed_obligation_cycles':s['miss'],'trigger_count':s['trigger'],'unknown_runs':s['unknown']}
     if arm=='no_fp_check':feedback.pop('false_positive_cycles')
     if arm=='existing_feedback':
      feedback={'fixed_fail_hit':sum(sum(x['fail_hit'] for x in r['candidates']) for r in rs if r['variant']=='correct'),'buggy_fail_hit':sum(sum(x['fail_hit'] for x in r['candidates']) for r in rs if r['variant']=='buggy'),'antecedent_hits':s['trigger']}
     # Generic diff replaces the obligation in the repair message, retaining equal input access.
     if arm=='generic_diff':
      import difflib
      correct,buggy=sources(d);prompt='Repair the assertion using generic RTL differences. Signals: '+','.join(d['observation_base'])+'\n'+('History p1/p2/p3 available.\n' if history else 'No history copies.\n')+'\n'.join(list(difflib.unified_diff(buggy.read_text().splitlines(),correct.read_text().splitlines()))[-45:])
      feedback={'fixed_fail_hit':sum(sum(x['fail_hit'] for x in r['candidates']) for r in rs if r['variant']=='correct'),'buggy_fail_hit':sum(sum(x['fail_hit'] for x in r['candidates']) for r in rs if r['variant']=='buggy'),'trigger_count':s['trigger']}
     else:prompt=base_prompt(d,history)
     evidence=[]
     for r in rs:
      if r['status']!='ok':continue
      tr=read(ROOT/r['trace']);ob=read(ROOT/r['obligations']);x=r['candidates'][0]
      cycles=sorted(set(x['missed_violation_cycles']+([] if arm=='no_fp_check' else x['false_positive_cycles'])))[:3]
      if arm in ['existing_feedback','generic_diff']:cycles=x['failure_cycles'][:3]
      for cycle in cycles:evidence.append({'rtl':r['variant'],'history':tr[max(0,cycle-3):cycle+1],'obligation':ob[cycle] if arm not in ['existing_feedback','generic_diff'] else 'not_supplied'})
     diagnostics=[]
     for r in rs:
      if r['status']!='ok':
       diagnostics.append({'status':r['status'],'compiler':(ROOT/r['compile']['stderr']).read_text()[:1800]})
     allowed=d['observation_base']+([f'p{j}_{n}' for j in [1,2,3] for n in d['observation_base']] if history else [])
     prompt+='\nCurrent property: '+json.dumps({n:best[n] for n in ['antecedent','consequent','delay']})+'\nFeedback: '+json.dumps(feedback)+'\nObserved evidence: '+json.dumps(evidence)+'\nCompiler diagnostics: '+json.dumps(diagnostics)+'\nEXACT permitted identifiers: '+', '.join(allowed)+'. No namespace prefixes, function calls, clocks, resets, or unlisted identifiers. Replace unsupported functions with primitive operators. The string p2_SIGNAL is not a signal.\nReturn one revised property; repair misses, legal-behavior false alarms, and empty triggers within allowed signals.'
     call=call_model(d,prompt,f'repair/{k}/{arm}/{step}',history);call_paths.append(call['request'])
     if call['candidate']:
      new=call['candidate'];new_scores,new_runs=evaluate(d,[new],f'methods/{arm}/{step}/recheck');runs+=new_runs
      accepted.append(new)
      # Old feedback selects using the old binary/fail-hit view only.
      if arm in ['existing_feedback','generic_diff']:
       def oldrank(rr):return(sum(x['fail_hit'] for r in rr if r['variant']=='correct' for x in r['candidates']),-sum(x['fail_hit'] for r in rr if r['variant']=='buggy' for x in r['candidates']))
       accept=oldrank(new_runs)<=oldrank(rs)
      else:accept=rank(new,new_scores,arm=='no_fp_check')<=rank(best,current,arm=='no_fp_check')
      rounds.append({'step':step,'feedback':feedback,'candidate':new,'score':new_scores[new['id']],'accepted':accept,'history_permission':history,'recheck_run_ids':[r['run_id'] for r in new_runs]})
      if accept:best=new;current=new_scores;rs=new_runs
     else:rounds.append({'step':step,'model_status':call['status']})
   # Exact consumed costs are recorded; first/selection and repair are NOT silently equalized.
   pool_calls=3 if arm=='equal_budget_select' else 1
   rec={'case':k,'parent_bug_id':IDS[k],'arm':arm,'status':'frozen','candidate':best,'rounds':rounds,'repair_model_calls':len(call_paths),'pool_generation_calls_consumed':pool_calls,'total_generation_calls_consumed':pool_calls+len(call_paths),'model_requests':call_paths,'validation_runs':[r['run_id'] for r in runs],'validation_seconds':sum(r['validation_wall_seconds'] for r in runs),'additional_history_bits_permission':3*sum({**d['inputs'],**d['outputs']}[s] for s in d['observation_base']),'history_permission':history,'budget_comparability':'selection: 3 generation calls and 12 candidate/RTL/scenario checks; repair: 1 initial + 2 repair calls and 12 checks if outputs supported. Actual tokens and time differ and are reported. First-candidate uses 1 call and 4 checks. Shared initial generation charged once per arm conceptually, physically executed once.'}
   if not history:rec['additional_history_bits_permission']=0
   dump(target,rec);methodrows.append(rec)
 dump(OUT/'method_freeze.json',{'rows':methodrows,'hashes':{rel(p):sha(p) for p in (OUT/'methods').glob('*/*/freeze.json')}})
 regression(selected_keys)

def regression(selected_keys=None):
 methodrows=read(OUT/'method_freeze.json')['rows']
 selected_keys=selected_keys or list(IDS)
 # Only now expose hidden scenario results, with frozen assertions.
 for rec in methodrows:
  if rec['case'] not in selected_keys:continue
  if rec['status']!='frozen':continue
  d=definition(rec['case']);arm=rec['arm'];c=rec['candidate']
  evaluate(d,[c],f'hidden/{arm}',kinds=('regression','reset'))
  for v in ['correct','buggy']:
   rows=schedule(d,'regression',seed=SEED+99)
   param={'DataWidth':4} if d['key']=='fifo' else {'CntWidth':3} if d['key']=='filter' else None
   if param:
    if d['key']=='fifo':
     for row in rows:row['data_i'] &=15
    else:
     for row in rows:row['thresh_i']=5
    execute_run(d,rows,[c],f'parameters/{arm}',v,param=param)
  execute_run(d,schedule(d,'regression',seed=SEED+333),[c],f'equivalent_rewrite/{arm}',rewrite=True)
  if d['key']=='spill':execute_run(d,schedule(d,'held'),[c],f'legal_variant/{arm}',invalid_bus_variant=True)

def report():
 runs=[read(p) for p in (OUT/'runs').rglob('result.json')];details=[]
 for r in runs:
  for c in r['candidates']:details.append({**{key:r.get(key) for key in ['run_id','parent_bug_id','case','variant','status','validation_wall_seconds']},**c})
 dump(OUT/'all_runs.json',runs);dump(OUT/'candidate_results.json',details)
 def csvfile(p,rows):
  if not rows:return
  keys=list(dict.fromkeys(k for r in rows for k in r))
  with p.open('w',newline='') as f:
   w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows([{k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in r.items()} for r in rows])
 csvfile(OUT/'candidate_results.csv',details)
 pairs=[]
 for p in read_lines(OUT/'frozen/pairs.jsonl'):
  k=next((k for k,v in IDS.items() if v==p['parent_id']),None)
  if not k:continue
  a='slot_'+p['candidate_A'][-2:];b='slot_'+p['candidate_B'][-2:];ev=[]
  for r in runs:
   if r['case']!=k or '/e12/' not in r['run_id'] or r['status']!='ok':continue
   ca=next((c for c in r['candidates'] if c['id']==a),None);cb=next((c for c in r['candidates'] if c['id']==b),None)
   if ca and cb and (ca['false_positive_cycles']!=cb['false_positive_cycles'] or ca['missed_violation_cycles']!=cb['missed_violation_cycles']):
    ev.append({'run':r['run_id'],'a':ca,'b':cb,'controlled_mutation':r.get('controlled_mutation'),'interpretation':'different legal-acceptance/obligation coverage sets; no total quality order inferred'})
  pairs.append({'pair_id':p['pair_id'],'parent_bug_id':p['parent_id'],'a':a,'b':b,'assertion_a':p['assertion_A'],'assertion_b':p['assertion_B'],'old_signature':p['feedback_signature'],'natural_pair':a!='slot_08' and b!='slot_08','obligation':rel(OUT/'frozen'/k/'obligation.json'),'evidence':ev,'status':'distinguished_on_checked_legal_inputs' if ev else 'not_found_in_checked_inputs','interpretation':'Different independently labelled rejection or missed-violation cycle sets; both may still be defective. A total ordering needs all obligations and legal behaviors. See controlled_partial_coverage for isolated misses.','legality_scope':'Depth=0 compatibility contract only' if k=='fifo' else 'spill payload interpretation unresolved; held-flush valid_o and zeroed-data reference witness remains concrete' if k=='spill' else 'frozen input and obligation contract'})
 dump(OUT/'collision_pairs.json',pairs)
 windows=[]
 for k in IDS:
  for v in ['correct','buggy']:
   rr=[next((r for r in runs if r['run_id'].endswith(f'e12/hold_{h}/{k}/{v}')),None) for h in [24,48,96]]
   if all(r and r['status']=='ok' for r in rr):
    ranks=[[c['id'] for c in sorted(r['candidates'],key=lambda x:(-x['fail_hit'],x['id']))] for r in rr]
    windows.append({'parent_bug_id':IDS[k],'variant':v,'runs':[r['run_id'] for r in rr],'rankings':ranks,'ranking_changed':ranks[0]!=ranks[1] or ranks[1]!=ranks[2],'independent_violations':'unknown','tail_constant_verified':all(all({n:row[n] for n in definition(k)['inputs']}=={n:read(ROOT/rr[0]['input'])[-1][n] for n in definition(k)['inputs']} for row in read(ROOT/r['input'])[24:]) for r in rr[1:])})
 dump(OUT/'window_results.json',windows)
 parents=[]
 if (OUT/'method_freeze.json').exists():
  for m in read(OUT/'method_freeze.json')['rows']:
   selected=[r for r in runs if r['case']==m['case'] and any('/'+phase+'/'+m['arm']+'/' in r['run_id'] for phase in ['hidden','parameters','equivalent_rewrite','legal_variant','boundary'])]
   unknown=m['status']!='frozen' or not selected or any(r['status']!='ok' for r in selected)
   contract_ambiguity=m['case']=='spill'
   if contract_ambiguity:unknown=True
   observations=[c for r in selected if r['status']=='ok' for c in r['candidates']];fp=sum(len(c['false_positive_cycles']) for c in observations);miss=sum(len(c['missed_violation_cycles']) for c in observations);ants=sum(c['trigger_count'] for c in observations);covered=sum(len(c['covered_violation_cycles']) for c in observations);total=sum(len(r.get('obligation_violation_cycles',[])) for r in selected)
   unknown=unknown or any(c['status']=='unknown' for c in observations)
   parents.append({'parent_bug_id':m['parent_bug_id'],'case':m['case'],'method':m['arm'],'status':'unknown' if unknown else 'complete_pass' if not fp and not miss and ants and total else 'false_positive' if fp else 'miss' if miss else 'not_triggered_or_no_target','unknown_reason':'payload_not_exposed does not independently specify invalid-data observability; validity-gated oracle is conditional' if contract_ambiguity else 'unsupported or incomplete verification' if unknown else None,'false_positive_cycles':fp,'missed_cycles':miss,'covered_violation_cycles':covered,'total_violation_cycles':total,'nonempty':bool(ants),'complete_pass':None if unknown else bool(not fp and not miss and ants and total),'runs':[r['run_id'] for r in selected],'model':MODEL,'aggregation_unit':'parent_bug','selection_scope':'first_candidate' if m['arm']=='first' else 'selected_candidate','k':1,'historical_fix':'unknown','mutation_class':'artificial','obligation_coverage':covered/total if total else None})
 dump(OUT/'parent_results.json',parents);csvfile(OUT/'parent_results.csv',parents)
 calls=[read(p) for p in (OUT/'model_calls').rglob('result.json')]
 summary={'rtl_runs':len(runs),'run_status':{s:sum(r['status']==s for r in runs) for s in sorted({r['status'] for r in runs})},'parent_bugs':len({r['parent_bug_id'] for r in runs}),'candidate_observations':len(details),'legacy_tied_pairs_checked':len(pairs),'natural_tied_pairs_distinguished':sum(p['natural_pair'] and bool(p['evidence']) for p in pairs),'window_comparisons':len(windows),'window_rank_changed':sum(r['ranking_changed'] for r in windows),'model_calls':len(calls),'generated_calls':sum(c['status']=='generated' for c in calls),'model_status_counts':{s:sum(c['status']==s for c in calls) for s in {c['status'] for c in calls}},'model_wall_seconds':sum(c['wall_seconds'] for c in calls),'validation_wall_seconds':sum(r['validation_wall_seconds'] for r in runs),'formal_solver_seconds':None,'formal_solver_status':'not_run: simulation and finite exhaustive truth tables only','historical_fix_parents':0,'budget_claim':'Selection and repair budget: 3 model calls, 12 candidate/RTL/scenario checks; unsupported outputs may consume fewer checks. Actual tokens and seconds recorded, not identical. First candidate uses 1 call, 4 checks.'}
 summary['methods']={arm:{'pass':sum(p['complete_pass'] is True for p in parents if p['method']==arm),'known':sum(p['status']!='unknown' for p in parents if p['method']==arm),'unknown':sum(p['status']=='unknown' for p in parents if p['method']==arm),'parents':sum(p['method']==arm for p in parents)} for arm in sorted({p['method'] for p in parents})}
 dump(OUT/'summary.json',summary);print(json.dumps(summary,indent=2))

def read_lines(p):return [json.loads(s) for s in p.read_text(encoding='utf-8-sig').splitlines() if s.strip()]

def audit():
 checks=[];f=read(OUT/'freeze.json')
 for name,h in f['hashes'].items():checks.append({'check':'frozen_hash','path':name,'pass':sha(ROOT/name)==h})
 for case in f['cases']:
  for name,h in case['source_hashes'].items():checks.append({'check':'original_RTL_unchanged','path':name,'pass':sha(ROOT/name)==h})
 for freeze_name in ['model_pool_freeze.json','method_freeze.json']:
  if (OUT/freeze_name).exists():
   sealed=read(OUT/freeze_name)
   for name,h in sealed.get('hashes',sealed.get('files',{})).items():checks.append({'check':freeze_name,'path':name,'pass':sha(ROOT/name)==h})
 for k in ['onehot','filter','fifo','spill']:
  path=OUT/'runs'/('pilot' if k!='spill' else 'e12/held_24')/k/'buggy'
  if not (path/'result.json').exists():continue
  before=read(path/'result.json');replay=command(['sh','reproduce.sh'],path,'audit_replay',60)
  log=(path/'audit_replay.stdout').read_text();old=(path/'simulate.stdout').read_text()
  # Ignore compilation warnings; compare all trace and checker lines exactly.
  extract=lambda s:[x for x in s.splitlines() if x.startswith(('TRACE ','CHECK '))]
  checks.append({'check':'command_replay','path':rel(path),'pass':replay['status']=='ok' and extract(log)==extract(old),'replay':replay})
 for p in (OUT/'runs').rglob('result.json'):
  r=read(p)
  checks.append({'check':'checker_hash','path':r['checker'],'pass':sha(ROOT/r['checker'])==r['checker_sha256']})
  if r['status']=='ok':
   text=(p.parent/'simulate.stdout').read_text()
   for j,c in enumerate(r['candidates']):
    fail=[int(m[1]) for m in re.finditer(r'^CHECK '+str(j)+r' (\d+) \d+ 1$',text,re.M)]
    checks.append({'check':'fail_cycle_recount','run':r['run_id'],'candidate':c['id'],'pass':fail==c['failure_cycles'] and len(fail)==c['fail_hit']})
 dump(OUT/'audit.json',{'checks':checks,'all_pass':all(c['pass'] for c in checks),'count':len(checks)});print('AUDIT',len(checks),all(c['pass'] for c in checks))

if __name__=='__main__':
 OUT.mkdir(exist_ok=True)
 p=argparse.ArgumentParser();p.add_argument('action',choices=['pilot','freeze','model-pool','experiments','methods','regression','report','audit']);p.add_argument('--cases',default='');a=p.parse_args();CASE_FILTER=a.cases.split(',') if a.cases else None
 globals()[a.action.replace('-','_')]()
