"""Audit real streams, unchanged predicates, native logs and preservation gate."""
import argparse
import copy
from pathlib import Path
from unittest.mock import patch
import research56_result_audit as base
import research58_preservation_refinement as g


def run(prep,root,out):
    original=g.prior.native_flow.frontend;decide=g.old.decide
    protected=g.read(prep/'target_preservation.private.json')
    def frontend(value,current):
        try:
            with patch.object(g.prior.native_flow,'frontend',original):
                candidate,labels=g.diagnostic.adapt(value,current)
        except (ValueError,TypeError,KeyError,AssertionError) as exc:
            return None,dict(accepted=False,errors=[dict(kind='label_compatible_interface',detail=str(exc))])
        clean=copy.deepcopy(value)
        for a in clean['assertions']:a.pop('id',None)
        return original(clean,current)
    with patch.object(base.fresh,'payload',g.payload),patch.object(g.prior.native_flow,'frontend',frontend),patch.object(g.old,'decide',lambda b,c:g.preserve(b,c,protected,decide)):
        base.run(prep,root,out)
    result=g.read(out/'audit.json');checks=result['checks']
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for folder in sorted(root.glob('v[0-9]*')):
        if (folder/'model_call/candidate.json').exists():
            raw=g.read(folder/'model_call/model_edit.json')
            candidate,labels=g.diagnostic.adapt(raw,g.read(prep/'shared_initial.json'))
            check(folder.name+'/exact_label_mapping',g.read(folder/'model_call/label_mapping.json')==dict(labels=labels,predicates_rewritten=False))
            check(folder.name+'/all_predicates_unchanged',g.read(folder/'model_call/candidate.json')==candidate)
        if (folder/'history/result.json').exists():
            combined=g.prior.common.combine(g.read(folder/'history/result.json'),g.read(folder/'search/result.json'))
            info=g.old.acceptance.inspect(combined['ledger'])
            lost={k:sorted(set(ids)-info['detections']) for k,ids in protected.items()}
            g.dump(out/(folder.name+'_preservation.json'),dict(lost=lost,retained={k:len(ids)-len(lost[k]) for k,ids in protected.items()}))
            if g.read(folder/'decision.json')['accepted']:check(folder.name+'/all690_retained',not any(lost.values()))
    result['scope']='Research58 real streams, optional label-only adapter, original native evidence, full151 and explicit690 preservation where reached.'
    g.dump(out/'audit.json',result)
    print('PRESERVATION_RESULT_AUDIT',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
