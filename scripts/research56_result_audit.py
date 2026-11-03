"""Reuse the native research55 audit with research56 request/novelty semantics.

No model calls or native executions. Audits exact real responses without edits.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research55_result_audit as audit
import research56_fresh_op as fresh


def run(prep,root,out):
    original_payload=fresh.previous.payload
    original_frontend=fresh.previous.frontend
    known=fresh.read(prep/'known_rejected_sets.json')
    checks=[];index=0
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    def payload(prepared,current,feedback):
        # fresh.payload reuses the unmodified research55 context builder.
        with patch.object(fresh.previous,'payload',original_payload):
            return fresh.payload(prepared,current,feedback)
    def frontend(value,current):
        nonlocal index
        folder=root/f'v{index}'/'model_call';index+=1
        candidate,interface=original_frontend(value,current)
        if candidate is None:return None,interface
        check(folder.parent.name+'/stored_candidate_unmodified',fresh.read(folder/'candidate.json')==candidate)
        verdict=fresh.novelty(candidate,known)
        normalized=json.loads(json.dumps(verdict))
        check(folder.parent.name+'/novelty_recomputed',normalized==fresh.read(folder/'novelty_gate.json'))
        if not verdict['accepted']:
            check(folder.parent.name+'/no_native_on_duplicate',not (folder.parent/'alignment').exists())
            return None,dict(accepted=False,errors=verdict['reasons'],syntactic_interface=interface,
                             stage='order_independent_novelty',native_execution='skipped')
        known.append(dict(source=str(folder/'candidate.json'),signature=fresh.op_signature(candidate)))
        return candidate,interface
    with patch.object(fresh.previous,'payload',payload),patch.object(fresh.previous,'frontend',frontend):
        audit.run(prep,root,out)
    result=fresh.read(out/'audit.json');result['checks'].extend(checks)
    result['scope']='Exact research56 model requests, responses, novelty decisions and unchanged native acceptance.'
    fresh.dump(out/'audit.json',result)
    fresh.dump(out/'novelty_audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0))
    print('FRESH_RESULT_AUDIT',len(result['checks']),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
