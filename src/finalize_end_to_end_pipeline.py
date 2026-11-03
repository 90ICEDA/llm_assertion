from __future__ import annotations
import argparse,hashlib,html,json
from pathlib import Path
import pandas as pd

def truth(d,n):return d[n].astype(str).str.lower().isin(['true','1','yes'])
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);ap.add_argument('--seed',type=int,default=20260721);args=ap.parse_args();r=Path(args.run_dir).resolve();raw=r/'multi_model_results_raw.csv';prompts=r/'multi_model_prompt_log.csv';d=pd.read_csv(raw,encoding='utf-8-sig')
 d['compile_fail']=~truth(d,'compile_ok');d['vacuity']=truth(d,'compile_ok')&(~truth(d,'antecedent_hit_buggy')|~truth(d,'non_vacuous_buggy'));d['too_strong']=truth(d,'compile_ok')&~truth(d,'correct_pass');d['too_weak']=truth(d,'compile_ok')&truth(d,'correct_pass')&~truth(d,'buggy_fail');d['false_positive']=~truth(d,'heldout_correct_pass');d['missed_detection']=truth(d,'heldout_correct_pass')&~truth(d,'heldout_buggy_fail');d['strict_success']=truth(d,'compile_ok')&truth(d,'correct_pass')&truth(d,'buggy_fail')&truth(d,'antecedent_hit_buggy')&truth(d,'non_vacuous_buggy')&truth(d,'heldout_correct_pass')&truth(d,'heldout_buggy_fail')&truth(d,'heldout_antecedent_hit')&truth(d,'heldout_non_vacuous');d['generated_table']=True
 detail=r/'failure_classification.csv';d.to_csv(detail,index=False,encoding='utf-8-sig');metrics=['compile_fail','vacuity','too_strong','too_weak','false_positive','missed_detection','trace_overfit','strict_success'];rows=[]
 for (model,method),g in d.groupby(['model_label','method']):
  row={'model':model,'method':method,'k':int(g.groupby('case_id').size().max()),'candidate_count':len(g),'case_count':g.case_id.nunique(),'generated_table':True};
  for m in metrics:row[m+'_count']=int(truth(g,m).sum());row[m+'_rate']=float(truth(g,m).mean())
  rows.append(row)
 s=pd.DataFrame(rows);summary=r/'results_table.csv';s.to_csv(summary,index=False,encoding='utf-8-sig')
 # Dependency-free, deterministic SVG grouped bar chart.
 labels=[f"{x.model}:{x.method.replace('spec_rtl_','')}" for x in s.itertuples()];vals=s.strict_success_rate.tolist();w=max(900,90*len(vals));h=520;bars=[]
 for i,(label,val) in enumerate(zip(labels,vals)):
  x=55+i*((w-90)/len(vals));bh=340*val;y=400-bh;bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="38" height="{bh:.1f}" fill="#2563eb"/><text x="{x+19:.1f}" y="{y-8:.1f}" text-anchor="middle" font-size="12">{val:.3f}</text><text transform="translate({x+19:.1f},420) rotate(55)" font-size="10">{html.escape(label)}</text>')
 svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}"><rect width="100%" height="100%" fill="white"/><text x="30" y="28" font-size="18">Strict success by model and method</text><line x1="45" y1="400" x2="{w-20}" y2="400" stroke="black"/><line x1="45" y1="60" x2="45" y2="400" stroke="black"/>{"".join(bars)}</svg>';plot=r/'strict_success.svg';plot.write_text(svg,encoding='utf-8')
 prompt_hashes=[]
 if prompts.exists():
  p=pd.read_csv(prompts,encoding='utf-8-sig');
  for x in p.itertuples():prompt_hashes.append({'model':x.model_label,'case_id':x.case_id,'method':x.method,'prompt_sha256':hashlib.sha256(str(x.prompt_text).encode()).hexdigest()})
 ph=r/'prompt_hashes.json';ph.write_text(json.dumps(prompt_hashes,indent=2),encoding='utf-8');outputs=[raw,prompts,detail,summary,plot,ph];freeze={'status':'frozen_generated_outputs','random_seed':args.seed,'manual_edit_policy':'tables and plots are generated only; any edit invalidates SHA-256','sha256':{str(p):sha(p) for p in outputs if p.exists()}};(r/'result_freeze.json').write_text(json.dumps(freeze,indent=2),encoding='utf-8');print(summary)
if __name__=='__main__':main()
