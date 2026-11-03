"""One real, short grammar-support probe; never a FIFO repair candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import urllib.request
import research17_model as base
from research24_model import lexical_schema
from research_native_model import invoke


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--service-log',type=Path,required=True)
    p.add_argument('--cooperative',action='store_true');a=p.parse_args()
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=False)
    tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=10))
    name='qwen2.5-coder:7b-instruct';digest=next(m['digest'] for m in tags['models'] if m['name']==name)
    schema=lexical_schema()
    request=dict(model=name,stream=True,format=schema,
        options=dict(temperature=0,seed=2026102001,num_predict=256 if a.cooperative else 512,num_ctx=16384,num_gpu=0,num_thread=8),
        messages=[dict(role='user',content=(json.dumps(dict(
            instruction='Generate ONE short syntactically valid SystemVerilog implication. Choose one permitted signal on each side and exactly one |-> or |=> operator. Do not concatenate signal names. Return the JSON edit schema, with one assertion and a three-word reason. This is only a syntax transport probe, not a FIFO correctness task.',
            signals=list(base.SIGNALS),obligation_names=list(base.SPECS),schema=schema)) if a.cooperative else
            'Return exactly NOT_JSON. This is a structured-output enforcement probe, not a hardware repair task.'))])
    offset=a.service_log.stat().st_size
    result,content=invoke(request,out/'model_call',base.dump,digest,timeout=180)
    segment=a.service_log.read_bytes()[offset:];(out/'backend.log').write_bytes(segment)
    errors=[line for line in segment.decode(errors='replace').splitlines()
        if 'error parsing grammar' in line or 'failed to parse grammar' in line]
    checks=[]
    try:
        value=json.loads(content)
        prop=schema['properties']['assertions']['items']['properties']['property']['pattern']
        checks=[set(value)=={'reason','operation','assertions'},value['operation']=='add',
            len(value['assertions'])==1,all(set(x)=={'property','obligation'} and
                re.fullmatch(prop,x['property']) is not None and 1<=len(x['obligation'])<=2
                and set(x['obligation'])<=set(base.SPECS) for x in value['assertions'])]
    except (ValueError,KeyError,TypeError):checks=[False]
    passed=result['status']=='response_received' and bool(segment) and not errors and all(checks)
    record=dict(passed=passed,checks=checks,backend_errors=errors,backend_log_sha256=hashlib.sha256(segment).hexdigest(),
        model_calls=result['model_calls'],prompt_tokens=result['prompt_tokens'],completion_tokens=result['completion_tokens'],
        native_execution_calls=0,compile_calls=0,formal_calls=0,
        probe_kind='cooperative_syntax' if a.cooperative else 'conflicting_text',
        scope='Actual schema transport probe. Generated diagnostic expression is not a repair, not used in FIFO candidates or model feedback.')
    base.dump(out/'qualification.json',record)
    for path in (Path(__file__),base.ROOT/'scripts/research24_model.py'):
        shutil.copy2(path,out/path.name)
    print(json.dumps(record))
    if not passed:raise SystemExit(1)


if __name__=='__main__':main()
