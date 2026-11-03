import hashlib, json, time
from pathlib import Path
import pyslang

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"outputs/behavioral_preference_pilot_v1"
GATE=BASE/"sequential_generation_v3_gate_c"

def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""): h.update(b)
    return h.hexdigest()

result=json.loads((GATE/"gate_result.json").read_text(encoding="utf-8"))
if not result.get("pass"): raise RuntimeError("v3 gate did not pass")
manifest={
 "protocol":"v3_constrained_ast_gate_c","status":"frozen_gate_pass_before_30_parent_pilot",
 "frozen_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
 "model":{"name":"qwen3-8b-pilot:q4_K_M","digest":"033521cec2c1f3afcf19a2ced270f4fdea6390582f40e350c10ffd965e6f3a6c","temperature":0.7,"num_predict":512,"seed":20260815,"num_ctx":8192,"think":False},
 "validators":{"pyslang":pyslang.__version__,"icarus":"12.0 stable","native_sva_parse_required":True,"monitor_compile_correct_and_buggy_required":True},
 "execution_adapters":{"cases":["case438_cc_fifo_protocol_suppress_2","case441_cc_stream_mux_protocol_suppress_1"],"scope":"exact testbench parameterization","reason":"Icarus 12 lacks SystemVerilog parameter type/package support","evidence":"candidate evidence stores original and derived SHA256 plus exact compile command"},
 "gate":{"parents":3,"candidates_per_parent":8,"parent_8_of_8":result["parent_8_of_8"],"quality_modes":result["quality_modes"],"pass":True},
 "hashes":{"implementation_sha256":sha(ROOT/"src/behavioral_preference_v3_gate.py"),"request_index_sha256":sha(GATE/"request_index.json"),"gate_result_sha256":sha(GATE/"gate_result.json")}
}
target=BASE/"behavioral_preference_v3_frozen.json"; target.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8"); print(json.dumps(manifest,ensure_ascii=False))
