"""One real local refinement from the actual 12/12 but false-alarming proposal."""
import argparse
import json
from pathlib import Path
import shutil
from unittest.mock import patch
import research60_compact_local as compact
base=compact.base;g=compact.g
SOURCE=g.ROOT/'deliverables/research60_local_compact_20261023_r02'
ORIGINAL_REQUEST=compact.request


def initial_feedback():
    result=g.read(SOURCE/'v0/alignment/result.json');gate=g.read(SOURCE/'v0/alignment/alignment_gate.json')
    assert not gate['accepted'] and gate['focus12']['accepted'] and result['counts']['false_positives']>0
    return dict(actual_model_proposal=g.read(SOURCE/'v0/model_call/model_edit.json'),
        actual_native_counts=result['counts'],actual_phase_counts=gate['focus12']['phases'],
        actual_development_evidence=g.old.evidence(result),
        task='Refine this actual model proposal. Native execution detects all targets, but reports failures on legal instructions. Eliminate these observed legal false alarms while retaining all required first/held targets. Derive conditions from the confirmed OP obligation and numeric evidence, not from a mere opcode difference. No accepted OP assertion is supplied.')


def request(prep,feedback,seed):
    return ORIGINAL_REQUEST(prep,initial_feedback() if feedback is None else feedback,seed)


def run(out):
    candidate=g.read(SOURCE/'v0/model_call/candidate.json')
    assert g.prior.diagnostic.audit_native(SOURCE/'v0/alignment',candidate,base.P,'alignment')==240
    files=[SOURCE/'v0/alignment/result.json',SOURCE/'v0/alignment/alignment_gate.json',SOURCE/'v0/model_call/model_edit.json',SOURCE/'v0/model_call/response.stream.jsonl']
    try:
        with patch.object(compact,'request',request):compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'refinement_adapter_snapshot.py')
            g.dump(out/'feedback_sources.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
            protocol=g.read(out/'protocol.json');protocol['changes']='One local7B refinement from actual compact-context proposal: all12 target points detected, but78 false alarms; numeric native feedback, exact RTL excerpt lineage and all acceptance standards retained.'
            protocol['previous_generation']=SOURCE.relative_to(g.ROOT).as_posix()
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
