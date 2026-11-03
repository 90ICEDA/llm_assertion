from __future__ import annotations
import argparse,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot_dataset(root:Path,run_dir:Path,source_commit:str):
 files=[root/'case_manifest.json']
 for case in sorted(x for x in root.iterdir() if x.is_dir()):
  files.extend(sorted(p for p in case.iterdir() if p.is_file() and (p.name in {'correct.v','buggy.v'} or p.name.startswith('tb') or (p.name.startswith('waveform_') and p.suffix=='.csv'))))
 snap={'source_commit':source_commit,'file_count':len(files),'sha256':{str(p.resolve()):sha(p) for p in files}};path=run_dir/'dataset_snapshot.json';path.write_text(json.dumps(snap,indent=2),encoding='utf-8');return path
def run_stage(name,cmd,run_dir,manifest):
 attempt=1+sum(x.get('name')==name for x in manifest.get('stages',[]));log=run_dir/'logs'/f'{attempt:02d}_{name}.log';log.parent.mkdir(parents=True,exist_ok=True);start=time.time();record={'name':name,'attempt':attempt,'command':cmd,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()};manifest['stages'].append(record)
 with log.open('w',encoding='utf-8') as h:
  p=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env=os.environ.copy());
  for line in p.stdout or []:print(line,end='');h.write(line);h.flush()
  code=p.wait()
 record.update({'exit_code':code,'duration_sec':time.time()-start,'log':str(log),'log_sha256':sha(log)});(run_dir/'pipeline_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
 if code:
  log_text=log.read_text(encoding='utf-8',errors='replace');recoverable=any(x in log_text for x in ['NOT_ENOUGH_BALANCE','HTTP 429','HTTP 502','HTTP 503','HTTP 504'])
  manifest['status']='failed_recoverable' if recoverable else 'failed';manifest['failed_stage']=name;manifest['resume_supported']=True;manifest['failure_reason']='provider balance/transient error; completed cells remain cached' if recoverable else 'stage command failed';(run_dir/'pipeline_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
  raise SystemExit(f'Stage {name} failed: {code}')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',default='outputs/end_to_end_formal_v1');ap.add_argument('--seed',type=int,default=20260721);ap.add_argument('--model',action='append',default=[]);ap.add_argument('--candidates',type=int,default=2);args=ap.parse_args();run_dir=(ROOT/args.run_dir).resolve();run_dir.mkdir(parents=True,exist_ok=True);models=args.model or ['GPT','Claude'];os.environ['PYTHONHASHSEED']=str(args.seed)
 source_commit=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}/external/opentitan','-C',str(ROOT/'external/opentitan'),'rev-parse','HEAD'],text=True).strip();manifest_path=run_dir/'pipeline_manifest.json';previous=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {};manifest={'schema_version':1,'status':'running','random_seed':args.seed,'dataset_root':str((ROOT/'rtl_cases_real_scale120').resolve()),'source_commits':{'opentitan':source_commit},'model_versions':{m:next(x['model_name'] for x in __import__('run_multi_model_small_eval').MODEL_SPECS if x['model_label']==m) for m in models},'stages':previous.get('stages',[]),'resume_count':int(previous.get('resume_count',-1))+1};manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8');py=sys.executable;common=['--root','rtl_cases_real_scale120','--output-dir',str(run_dir),'--temporal-summary-json','outputs/formal_temporal_abstractions/temporal_abstractions.json','--all-cases',*sum((['--model',m] for m in models),[]),'--method','spec_rtl_raw_trace','--method','spec_rtl_naive_summary','--method','spec_rtl_event_abstraction','--method','spec_rtl_temporal_relation_abstraction','--candidates-per-cell',str(args.candidates),'--resume']
 run_stage('build_dataset_and_representations',[py,'src/build_scale120_four_trace_representations.py'],run_dir,manifest)
 snapshot=snapshot_dataset(ROOT/'rtl_cases_real_scale120',run_dir,source_commit);manifest['dataset_snapshot']=str(snapshot);manifest['dataset_snapshot_sha256']=sha(snapshot)
 external_inputs=[ROOT/'outputs/formal_four_trace_representations/trace_representations.json',ROOT/'outputs/formal_four_trace_representations/contract_audit_summary.json',ROOT/'outputs/formal_temporal_abstractions/temporal_abstractions.json'];manifest['external_input_sha256']={str(p.resolve()):sha(p) for p in external_inputs}
 # generate-only writes prompts, raw model responses, and extracted pending candidates before validation.
 run_stage('generate_prompts_run_models_extract_sva',[py,'src/run_trace_representation_ablation.py',*common,'--generate-only'],run_dir,manifest)
 run_stage('compile_visible_and_heldout_validation',[py,'src/run_trace_representation_ablation.py',*common],run_dir,manifest)
 run_stage('failure_classification_tables_and_plots',[py,'src/finalize_end_to_end_pipeline.py','--run-dir',str(run_dir),'--seed',str(args.seed)],run_dir,manifest)
 manifest['status']='complete';manifest['completed_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();manifest['artifact_sha256']={str(p):sha(p) for p in run_dir.rglob('*') if p.is_file() and p.name!='pipeline_manifest.json'};(run_dir/'pipeline_manifest.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8');subprocess.run([py,'src/verify_end_to_end_freeze.py','--run-dir',str(run_dir)],cwd=ROOT,check=True);print(run_dir/'pipeline_manifest.json')
if __name__=='__main__':main()
