"""Local read-only runner tokenization; never sends a generation request.

Use the live llama-server /apply-template and /tokenize endpoints. Ollama can
render its own Go template, so an uncalibrated count is not called exact.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
LOG=ROOT/'deliverables/research15_native_20261015_r01/service/server.log'


def http(url,payload=None):
    req=urllib.request.Request(url,data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)


def discover():
    ports=re.findall(r'starting llama-server.*?--port (\d+)',LOG.read_text(errors='replace')) if LOG.exists() else []
    # A restarted local service may log in a newer experiment directory. Read
    # only runner process arguments; no environment variables or credentials.
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            command=path.read_bytes().decode(errors='replace').replace('\x00',' ')
            if ('ollama' in command or 'llama-server' in command) and '--port ' in command:
                ports.extend(re.findall(r'--port (\d+)',command))
        except (OSError,PermissionError):pass
    errors=[]
    for port in reversed(list(dict.fromkeys(ports))):
        endpoint='http://127.0.0.1:'+port
        try:
            health=http(endpoint+'/health')
            return endpoint,health
        except Exception as exc:errors.append(dict(port=port,error=repr(exc)))
    raise RuntimeError('No live runner: '+repr(errors))


def count(request,endpoint=None):
    endpoint,health=discover() if endpoint is None else (endpoint,http(endpoint+'/health'))
    messages=request['messages']
    if any(set(message)-{'role','content'} or not isinstance(message.get('content'),str) for message in messages):
        raise ValueError('Only text-only role/content messages supported by this preflight')
    applied=http(endpoint+'/apply-template',dict(messages=messages,add_generation_prompt=True))
    prompt=applied['prompt']
    tokens=http(endpoint+'/tokenize',dict(content=prompt,add_special=False,parse_special=True))['tokens']
    content_counts=[len(http(endpoint+'/tokenize',dict(content=m['content'],add_special=False,parse_special=True))['tokens']) for m in messages]
    # This allowance handles known Go-vs-ChatML wrapper differences and boundary
    # tokenization, not arbitrary tool/image/template content. Full prompt text
    # is returned so calibration against actual completed calls is possible.
    reserve=256+64*len(messages)
    estimate=max(len(tokens),sum(content_counts))+reserve
    options=request.get('options',{})
    context=options.get('num_ctx');output=options.get('num_predict')
    supported=type(context) is int and type(output) is int and output>=0
    return dict(endpoint=endpoint,runner_health=health,prompt=prompt,
        rendered_prompt_tokens=len(tokens),message_content_tokens=content_counts,
        conservative_input_estimate=estimate,wrapper_margin_tokens=reserve,
        output_reserved_tokens=output,context_tokens=context,
        fits_with_output_reserve=(estimate+output<context) if supported else None,
        generation_calls=0,tokenization_calls=len(messages)+1,
        precision='Actual runner tokenizer; template path may differ from Ollama Go renderer. Conservative margin is an engineering allowance, not an exact guarantee.'),applied


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--request',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    request=json.loads(args.request.read_text(encoding='utf-8-sig'))
    result,applied=count(request)
    (args.out/'rendered_prompt.txt').write_text(result.pop('prompt'),encoding='utf-8')
    result.update(request_file=str(args.request),request_sha256=hashlib.sha256(args.request.read_bytes()).hexdigest())
    (args.out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
