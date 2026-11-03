"""Offline research57 audit reusing actual-response and native-evidence checks."""
import argparse
from pathlib import Path
from unittest.mock import patch
import research56_result_audit as base
import research57_legal_refinement as current


def run(prep,root,out):
    with patch.object(base.fresh,'payload',current.payload):
        base.run(prep,root,out)
    report=current.read(out/'audit.json');checks=report['checks']
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    preserved=current.read(prep/'target_preservation.private.json')
    check('target_inventory_420_270',len(preserved['op_bit28_illegal'])==420 and len(preserved['illegal_branch_persists'])==270)
    for folder in sorted(root.glob('v[0-9]*')):
        req=current.read(folder/'model_call/request.json')
        check(folder.name+'/local_request_byte_budget',sum(len(m['content'].encode()) for m in req['messages'])<=current.MAX_MESSAGE_BYTES)
        if (folder/'history/result.json').exists() and (folder/'search/result.json').exists():
            ledger=sum([current.read(folder/cohort/'result.json')['ledger'] for cohort in ('history','search')],[])
            info=current.old.acceptance.inspect(ledger)
            lost={ob:sorted(set(keys)-info['detections']) for ob,keys in preserved.items()}
            current.dump(out/(folder.name+'_preservation.json'),dict(lost=lost,preserved={ob:len(keys)-len(lost[ob]) for ob,keys in preserved.items()}))
            if current.read(folder/'decision.json')['accepted']:check(folder.name+'/all690_preserved',not any(lost.values()))
    report['scope']='Research57 compact real feedback, exact model predicates, native alignment and full151 acceptance when reached.'
    current.dump(out/'audit.json',report)
    print('LEGAL_RESULT_AUDIT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
