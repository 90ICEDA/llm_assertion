"""Explicit short real-model grammar probe. Never run on module import.

No SVA research-success credit; output is a backend format diagnostic only.
Run serially after other model calls to attribute new server log errors.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

from research17_model_schema import schema
from research_native_model import invoke

ROOT = Path(__file__).resolve().parents[1]
SERVER_LOG = ROOT/'deliverables/research15_native_20261015_r01/service/server.log'


def dump(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')


def make_schema(kind):
    result = copy.deepcopy(schema())
    if kind == 'reason-unbounded':
        # Decoder grammar limit only. Research AST normalizer still enforces
        # reason<=4096 and rejects malformed output; no predicate is replaced.
        result['properties']['reason'].pop('maxLength')
    elif kind == 'tiny':
        result = dict(type='object', additionalProperties=False,
                      required=['marker'], properties=dict(
                          marker=dict(type='string', enum=['schema_active'])))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema', choices=['original', 'reason-unbounded', 'tiny'], required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--tokens', type=int, default=128)
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--prepare-only', action='store_true', help='Write request without a model call')
    parser.add_argument('--minimal-object', action='store_true', help='Request a complete minimal AST edit object; diagnostic only')
    args = parser.parse_args()
    if not 16 <= args.tokens <= 512:
        parser.error('tokens must be 16..512')
    out=args.out.resolve();out.mkdir(parents=True, exist_ok=False)
    request=dict(model='qwen2.5-coder:7b-instruct', stream=True,
        format=make_schema(args.schema),
        options=dict(seed=20261018, temperature=0, num_predict=args.tokens,
                     num_ctx=16384, num_gpu=0, num_thread=8),
        messages=[dict(role='user', content='This is only a format-control probe. Output exactly UNCONSTRAINED with no JSON, braces or other text.')])
    if args.minimal_object:
        request['messages'][0]['content']='Format-control probe only, no SVA task. Return a JSON object with operation keep, assertions an empty array, and reason a short explanation that this is a format probe. No markdown.'
    dump(out/'planned_request.json', request)
    dump(out/'protocol.json', dict(schema_variant=args.schema, purpose='backend grammar enforcement diagnostic',
        not_sva_generation_evidence=True, native_executions=0, formal_calls=0,
        command=sys.argv, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        run_serially=True, max_model_calls=0 if args.prepare_only else 1,
        modifications='Only reason.maxLength is removed from transmitted schema in reason-unbounded variant.'))
    if args.prepare_only:
        print(json.dumps(dict(status='prepared_not_executed', model_calls=0, out=str(out))))
        return
    tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=10))
    version=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/version',timeout=10))
    digest=next(item['digest'] for item in tags['models'] if item['name']==request['model'])
    dump(out/'model_tags.json',tags);dump(out/'api_version.json',version)
    log_before=SERVER_LOG.stat().st_size if SERVER_LOG.exists() else None
    result,content=invoke(request,out/'model_call',dump,digest,timeout=args.timeout)
    log=''
    if log_before is not None and SERVER_LOG.exists():
        with SERVER_LOG.open('rb') as handle:
            handle.seek(log_before);log=handle.read().decode(errors='replace')
        (out/'server_new.log').write_text(log,encoding='utf-8')
    parsed=None;error=None;schema_validation='unavailable'
    try:
        parsed=json.loads(content)
        try:
            import jsonschema
            jsonschema.validate(parsed,request['format']);schema_validation='passed'
        except ImportError:
            schema_validation='validator_unavailable'
        except Exception as exc:
            schema_validation='failed:'+str(exc)
    except Exception as exc:
        error=repr(exc)
    grammar_error=any(message in log for message in ('error parsing grammar','failed to parse grammar'))
    result.update(schema_variant=args.schema,json_parse_error=error,
        output_is_json_object=isinstance(parsed,dict),schema_validation=schema_validation,
        new_server_grammar_error=grammar_error if log_before is not None else None,
        server_log_attribution='Requires no concurrent model requests; log append interval only.',
        output_prefix=content[:120],
        interpretation='Format behavior only; no RTL compilation, SVA validity or semantic repair claim.')
    dump(out/'result.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    main()
