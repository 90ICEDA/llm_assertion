"""Record an interrupted run from persisted evidence; never salvage an SVA."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil


def main():
    root=Path(__file__).resolve().parents[1]
    run=root/'deliverables/research26_closed_loop_20261020_r01'
    active=[]
    for cmd in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=cmd.read_bytes().split(b'\0')
            if any(b'research21_loop.py' in a for a in args):
                active.append(cmd.parent.name)
        except OSError:
            pass
    assert not active,active
    read=lambda p:json.loads(p.read_text())
    dump=lambda p,v:p.write_text(json.dumps(v,indent=2)+'\n')
    assert read(run/'outcome.json')['status']=='running'
    assert not (run/'core/freeze.json').exists()
    call=run/'core/v0/model_call'
    assert not (call/'result.json').exists()
    raw=call/'response.stream.jsonl'
    chunks=[json.loads(s) for s in raw.read_text().splitlines()]
    assert chunks and not any(c.get('done') for c in chunks)
    shutil.copy2(run/'outcome.json',run/'outcome.interrupted_original.json')
    evidence=dict(recorded_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        status='interrupted_without_terminal_response',cause='unknown',
        active_loop_processes=active,stream_chunks=len(chunks),terminal_chunk_present=False,
        raw_stream_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        final_prompt_tokens=None,final_completion_tokens=None,
        candidate_generated=False,native_proposal_evaluation=False,accepted=False,
        note='Partial text is preserved untouched; no candidate is assembled from it. Progress/cache counts are not final usage.')
    dump(run/'interruption_recovery.json',evidence)
    dump(run/'outcome.json',dict(status='execution_interrupted_cause_unknown',
        independent_executed=False,reason='No live loop; partial stream without done; no freeze or acceptance. See interruption_recovery.json.'))
    dump(run/'model_cost.json',dict(calls=1,prompt_tokens=None,completion_tokens=None,
        usage_unavailable=1,formal_calls=0,source='attempt.json and persisted stream; no final response'))
    print(json.dumps(evidence))


if __name__=='__main__':
    main()
