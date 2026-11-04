"""Verify/execute the exact sealed R0-R3 requests after external-transfer approval.

verify is offline and never constructs transport. run is an explicit separate
action; the request and every bound source must still match preparation.
"""
import argparse
import json
from pathlib import Path
import research192_temporal_refinement as r


def verify(prepared):
    for manifest in ('seal.json', 'source_bindings.json'):
        for name, digest in r.s.read(prepared/manifest).items():
            if r.s.sha(r.ROOT/name) != digest:
                raise ValueError('sealed_input_changed:'+name)
    entries = r.s.read(prepared/'requests.json')
    initial = r.s.read(prepared/'initial.json')
    evidence = r.s.read(prepared/'evidence.json')
    base = r.s.read(r.SOURCE/'request.preview.json')
    for item in entries:
        stored = r.s.read(r.ROOT/item['request'])
        request, _ = r.build_request(base, item['strategy'], evidence, item['seed'], initial)
        if request != stored or r.s.sha(r.ROOT/item['request']) != item['request_sha256']:
            raise ValueError('request_changed')
    if len(entries) != 8 or len({(e['strategy'],e['seed']) for e in entries}) != 8:
        raise ValueError('paired_request_population')
    return entries, initial, evidence, base


def run(prepared, out):
    entries, initial, evidence, base = verify(prepared)
    out.mkdir(parents=True, exist_ok=False)
    # Protected target IDs are the exact independently measured baseline IDs.
    protected = r.s.read(prepared/'baseline_measurement.json')['detected_ids']
    r.s.dump(out/'protocol_binding.json',dict(prepared=r.s.rel(prepared),
        seal_sha256=r.s.sha(prepared/'seal.json'), runner_sha256=r.s.sha(Path(__file__)),
        maximum_physical_model_calls=8, retries=0,
        external_transfer='Only execute after explicit approval for highwayapi.ai RTL/SVA/specification/evidence payload.'))
    rows, cache = [], {}
    for entry in entries:
        verify(prepared)
        seed, strategy = entry['seed'], entry['strategy']
        result = r.run_arm(out/f'seed{seed}'/strategy, strategy, seed,
            evidence=evidence, initial=initial, protected=protected,
            base_request=base, native_cache=cache)
        actual_request = r.s.read(out/f'seed{seed}'/strategy/'request.preview.json')
        if actual_request != r.s.read(r.ROOT/entry['request']):
            raise ValueError('dispatched_request_mismatch')
        rows.append(result)
        r.s.dump(out/'results.json', rows)
        print(json.dumps(result), flush=True)
    r.s.dump(out/'outcome.json',dict(status='completed',model_calls=sum(x['model_calls'] for x in rows),
        all_requests_match_sealed=True))
    return rows


if __name__ == '__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('action',choices=('verify','run'))
    cli.add_argument('--prepared',type=Path,required=True)
    cli.add_argument('--out',type=Path)
    args=cli.parse_args()
    if args.action=='verify':
        entries,*_=verify(args.prepared.resolve())
        print('VERIFIED '+str(len(entries))+' sealed requests; no network or model calls',flush=True)
    else:
        if args.out is None:cli.error('run requires --out')
        run(args.prepared.resolve(),args.out.resolve())
