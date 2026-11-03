"""Record an interrupted management-only load without inventing generation."""
import hashlib
import json
from pathlib import Path
import shutil
import research17_model as base

run=base.ROOT/'deliverables/research27_closed_loop_20261020_r03'
assert base.read(run/'outcome.json')['status']=='running'
active=[]
for path in Path('/proc').glob('[0-9]*/cmdline'):
    try:
        command=path.read_bytes()
    except OSError:
        continue
    if b'research21_loop.py' in command:
        active.append(command.decode(errors='replace'))
assert not active
assert not list(run.rglob('attempt.json'))
assert not (run/'core').exists()
shutil.copy2(run/'outcome.json',run/'outcome.interrupted_original.json')
log=base.ROOT/'deliverables/research27_closed_loop_20261020_r01/service/server.log'
data=dict(status='execution_interrupted_during_model_load',generation_calls=0,
    evidence=dict(no_active_loop=True,no_generation_attempt=True,no_native_core=True,
        load_request_present=(run/'model_load/request.json').exists(),
        load_response_present=(run/'model_load/response.json').exists(),
        service_log=str(log),service_log_sha256=hashlib.sha256(log.read_bytes()).hexdigest()),
    cause='unknown; local server reported load cancellation and both loop/service were later absent. Memory pressure is a hypothesis, not established.',
    independent_executed=False,model_load_duration_and_cost=None)
base.dump(run/'recovery.json',data)
base.dump(run/'outcome.json',data)
base.dump(run/'model_cost.json',dict(calls=0,prompt_tokens=0,completion_tokens=0,usage_unavailable=0,
    formal_calls=0,management_load_cost=None))
shutil.copy2(__file__,run/'recovery_script.py')
print(json.dumps(data))
