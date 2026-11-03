from __future__ import annotations

import argparse, hashlib, json, re
from pathlib import Path
import pandas as pd
from build_dev_locked_score_reranker import candidate_table, score as locked_score

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/"outputs/candidate_count_cost_v1"
BASE=ROOT/"outputs/formal_compliant_raw_temporal_dual";EXT=ROOT/"outputs/candidate_portfolio_k4_extension"
PARENT=ROOT/"outputs/dev_locked_score_reranker/selected_candidates.csv";POLICY=ROOT/"outputs/dev_locked_score_reranker/score_policy_lock.json";TIMING=OUT/"validation_timing.csv"
KS=[1,2,4,8]
def truth(d,n,default=False):return d[n].astype(str).str.lower().isin(['true','1','yes']) if n in d else pd.Series(default,index=d.index)
def canon(x):return re.sub(r'\s+',' ',str(x or '')).strip()
def tok(x):return len(re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\d+'[bdhoBDHO][0-9a-fA-F_xXzZ]+|\d+|[^\s]",str(x)))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load():
 frames=[]
 for root,phase in [(BASE,'initial'),(EXT,'extension')]:
  d=pd.read_csv(root/'multi_model_results_raw.csv',encoding='utf-8-sig');d['phase']=phase;frames.append(d)
 d=pd.concat(frames,ignore_index=True);d=d[d.method.isin(['spec_rtl_raw_trace','spec_rtl_temporal_relation_abstraction'])].copy();d['rep']=d.method.map({'spec_rtl_raw_trace':'raw','spec_rtl_temporal_relation_abstraction':'temporal'});d['slot']=d.apply(lambda r:2*(int(r.candidate_index)-1)+(1 if r.rep=='raw' else 2),axis=1);d['canonical']=d.assertion_text.map(canon);d['strict']=truth(d,'compile_ok')&truth(d,'correct_pass')&truth(d,'buggy_fail')&truth(d,'antecedent_hit_buggy')&truth(d,'non_vacuous_buggy')&truth(d,'heldout_correct_pass')&truth(d,'heldout_buggy_fail')&truth(d,'heldout_antecedent_hit')&truth(d,'heldout_non_vacuous')
 features,_=candidate_table(BASE/'multi_model_results_raw.csv',EXT/'multi_model_results_raw.csv',ROOT/'rtl_cases_real_scale120');weights=json.loads((ROOT/'outputs/dev_locked_score_reranker/score_policy_lock.json').read_text())['weights'];features['seen_score']=locked_score(features,weights);features['rep']=features.representation;features['canonical']=features.assertion_text.map(canon);fs=features[['model_label','case_id','rep','candidate_index','canonical','seen_score']];d=d.merge(fs,on=['model_label','case_id','rep','candidate_index','canonical'],how='left',validate='one_to_one')
 pm=pd.read_csv(PARENT,encoding='utf-8-sig')[['case_id','parent_bug_id']].drop_duplicates();d=d.merge(pm,on='case_id',how='left');
 if d.groupby(['model_label','case_id']).slot.nunique().min()!=8:raise RuntimeError('Incomplete k=8 pool')
 return d.sort_values(['model_label','case_id','slot'])
def call_costs():
 rows=[]
 for root,phase in [(BASE,'initial'),(EXT,'extension')]:
  p=root/'multi_model_prompt_log.csv';d=pd.read_csv(p,encoding='utf-8-sig')
  for r in d.itertuples():rows.append({'model_label':r.model_label,'case_id':r.case_id,'rep':'raw' if r.method=='spec_rtl_raw_trace' else 'temporal','phase':phase,'prompt_tokens_est':tok(r.prompt_text),'output_tokens_est':tok(r.raw_generation_responses),'generation_time_sec':None,'token_count_method':'offline lexical estimate from frozen prompt/response; not provider billing usage'})
 return pd.DataFrame(rows)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out-dir',default=str(OUT));args=ap.parse_args();out=Path(args.out_dir).resolve();out.mkdir(parents=True,exist_ok=True);pool=load();cost=call_costs();detail=[];summary=[]
 timing=pd.read_csv(TIMING,encoding='utf-8-sig') if TIMING.exists() else pd.DataFrame()
 for model,md in pool.groupby('model_label'):
  prev=set();prev_tokens=0;prev_vt=0.0
  for k in KS:
   sub=md[md.slot<=k];cells=[]
   for case,g in sub.groupby('case_id'):
    g=g.sort_values('slot');first=bool(g.iloc[0].strict);anyk=bool(g.strict.any());top=g.sort_values(['seen_score','slot'],ascending=[False,True]).iloc[0];cells.append({'model':model,'case_id':case,'parent_bug_id':g.parent_bug_id.iloc[0],'k':k,'first_candidate':first,'any_of_k':anyk,'reranker_top1':bool(top.strict),'reranker_slot':int(top.slot),'duplicate_rate':1-g.canonical.nunique()/len(g)})
   c=pd.DataFrame(cells);detail.extend(c.to_dict('records'));success=set(c[c.any_of_k].case_id);new=len(success-prev);prev=success
   needed=[('raw','initial')]
   if k>=2:needed.append(('temporal','initial'))
   if k>=5:needed.extend([('raw','extension'),('temporal','extension')])
   cc=cost[(cost.model_label==model)&cost.apply(lambda r:(r.rep,r.phase) in needed,axis=1)];pt=int(cc.prompt_tokens_est.sum());ot=int(cc.output_tokens_est.sum())
   vt=None
   if not timing.empty:
    tt=timing[(timing.model_label==model)&(timing.slot<=k)];vt=float(tt.validation_time_sec.sum())
   total=pt+ot;delta_tokens=total-prev_tokens;delta_vt=None if vt is None else vt-prev_vt
   summary.append({'model':model,'k':k,'case_count':len(c),'parent_count':c.parent_bug_id.nunique(),'first_candidate_success_count':int(c.first_candidate.sum()),'first_candidate_success_rate':c.first_candidate.mean(),'any_of_k_success_count':int(c.any_of_k.sum()),'any_of_k_success_rate':c.any_of_k.mean(),'reranker_top1_success_count':int(c.reranker_top1.sum()),'reranker_top1_success_rate':c.reranker_top1.mean(),'duplicate_rate':c.duplicate_rate.mean(),'new_success_cases_vs_previous_k':new,'prompt_tokens_est':pt,'output_tokens_est':ot,'total_tokens_est':total,'incremental_tokens_est':delta_tokens,'generation_time_sec':None,'validation_time_sec':vt,'incremental_validation_time_sec':delta_vt,'incremental_tokens_per_new_success':None if new==0 else delta_tokens/new,'incremental_validation_sec_per_new_success':None if new==0 or delta_vt is None else delta_vt/new,'timing_status':'measured' if vt is not None else 'pending replay; historical generation time unavailable'});prev_tokens=total
   if vt is not None:prev_vt=vt
 detail=pd.DataFrame(detail);summary=pd.DataFrame(summary);dp=out/'candidate_count_case_results.csv';sp=out/'candidate_count_summary.csv';detail.to_csv(dp,index=False,encoding='utf-8-sig');summary.to_csv(sp,index=False,encoding='utf-8-sig');outputs={str(dp):sha(dp),str(sp):sha(sp)}
 if TIMING.exists():
  outputs[str(TIMING.resolve())]=sha(TIMING); replay=pool[['model_label','case_id','slot','compile_ok','strict']].merge(timing,on=['model_label','case_id','slot']);cm=truth(replay,'compile_ok')!=truth(replay,'compile_ok_replay');sm=replay.strict.astype(bool)!=truth(replay,'strict_success_replay');consistency={'row_count':len(replay),'compile_mismatch_count':int(cm.sum()),'strict_success_mismatch_count':int(sm.sum()),'compile_mismatches':replay.loc[cm,['model_label','case_id','slot','compile_ok','compile_ok_replay','strict','strict_success_replay']].to_dict('records')};cp=out/'validation_replay_consistency.json';cp.write_text(json.dumps(consistency,indent=2),encoding='utf-8');outputs[str(cp)]=sha(cp)
 freeze={'status':'frozen_effect_and_token_estimate_timing_pending' if not TIMING.exists() else 'frozen_with_validation_timing','candidate_order':['raw1','temporal1','raw2','temporal2','raw3','temporal3','raw4','temporal4'],'reranker':'dev-locked seen-only score policy; held-out excluded from selection','historical_batching':'initial calls returned candidates 1-2 per representation; extension calls returned candidates 3-4, so k=4 has zero incremental generation tokens versus k=2','token_count_method':'offline lexical estimate; provider usage was not recorded','generation_time_status':'not recoverable from historical runs; requires fresh API rerun','input_sha256':{str(p.resolve()):sha(p) for p in [BASE/'multi_model_results_raw.csv',EXT/'multi_model_results_raw.csv',BASE/'multi_model_prompt_log.csv',EXT/'multi_model_prompt_log.csv',PARENT,POLICY]},'output_sha256':outputs};(out/'candidate_count_freeze.json').write_text(json.dumps(freeze,indent=2,ensure_ascii=False),encoding='utf-8');print(sp)
if __name__=='__main__':main()
