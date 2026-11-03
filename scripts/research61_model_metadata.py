"""Read cached model manifest/template only; no inference or service startup."""
import argparse
import hashlib
import json
from pathlib import Path

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    models=Path('/home/user/.ollama/models')
    path=models/'manifests/registry.ollama.ai/library/qwen2.5-coder/7b-instruct'
    manifest=json.loads(path.read_text());items=[]
    for layer in manifest['layers']:
        if layer['mediaType'] not in ('application/vnd.ollama.image.system','application/vnd.ollama.image.template'):continue
        p=models/'blobs'/layer['digest'].replace(':','-');raw=p.read_bytes()
        digest=hashlib.sha256(raw).hexdigest();assert digest==layer['digest'].split(':')[1]
        name=layer['mediaType'].rsplit('.',1)[1];(out/(name+'.txt')).write_bytes(raw)
        items.append(dict(kind=name,sha256=digest,bytes=len(raw),contains_domain_specific_output=any(s in raw for s in (b'illegal_insn',b'bit28',b'replace_op')),
                          iterates_messages=(b'.Messages' in raw and b'.Content' in raw) if name=='template' else None))
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (out/'check.json').write_text(json.dumps(dict(model_calls=0,service_calls=0,items=items,
        transport='Repository stream_call serializes supplied request directly to local /api/chat.',
        scope='No domain-specific fixed response found in default system/template. Does not establish why inference repeats a rejected predicate, or prove internals of model weights.'),indent=2)+'\n')
    print('MODEL_METADATA_READ_ONLY',len(items),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
