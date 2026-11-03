import json,pathlib,shutil,time
from run_repair_contract import OUT,call_model,definition,MODEL,dump
src=OUT/'model_calls'
dest=OUT/'failed_model_calls_gpu'
if not dest.exists():
 assert src.resolve().is_relative_to(OUT.resolve()) and dest.resolve().is_relative_to(OUT.resolve())
 shutil.move(str(src),str(dest))
 if (OUT/'model_pool_freeze.json').exists():shutil.move(str(OUT/'model_pool_freeze.json'),str(OUT/'failed_gpu_model_pool_freeze.json'))
dump(OUT/'runtime_amendment.json',{'reason':'18 HTTP 500 responses; server reports CUDA error: device kernel image is invalid','model':MODEL,'options':{'seed':20261009,'temperature':0.2,'num_predict':192,'num_ctx':4096,'num_gpu':0,'num_thread':8},'effective_before_any_usable_candidate':True,'original_failed_calls':'failed_model_calls_gpu','timestamp_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
r=call_model(definition('fifo'),'Signals push_i, empty_o. Contract: empty_o is inverse of push_i in same cycle. No history. Return JSON with antecedent, consequent, delay.','preflight_cpu')
print(json.dumps(r,indent=2))
