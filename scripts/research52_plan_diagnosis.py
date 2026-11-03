"""Classify actual plan errors without correcting responses or changing verdicts."""
import argparse
from collections import Counter
from pathlib import Path
import research52_ibex_bit_gate as g


def run(prep,root,out):
    out.mkdir(parents=True,exist_ok=True)
    expected=g.source_check(prep);truth={w['id']:w for w in expected['windows']};results=[]
    prior=None
    for folder in sorted((root/'plan').glob('v*')):
        plan=g.read(folder/'model_call/model_plan.json');gate=g.read(folder/'decision.json')
        value_errors=[];type_errors=[];inconsistent=[]
        for w in plan['windows']:
            t=truth[w['id']]
            for field in g.FIELDS-{'id'}:
                if w[field]!=t[field]:value_errors.append(dict(id=w['id'],field=field,actual=w[field],expected=t[field]))
                elif type(w[field]) is not type(t[field]):type_errors.append(dict(id=w['id'],field=field,actual=w[field],expected_type=type(t[field]).__name__))
            own_branch=w['opcode']==0x63 and w['funct3'] in (2,3)
            own_op=w['opcode']==0x33 and w['bit28']
            if w['branch_applicable']!=own_branch or w['op_applicable']!=own_op:
                inconsistent.append(w['id'])
        assert len(value_errors)+len(type_errors)==len(gate['reasons'])
        results.append(dict(version=folder.name,accepted=gate['accepted'],correct_obligation_bit=plan['op_illegal_bit']==28,
            identical_to_previous=plan==prior if prior is not None else None,
            semantic_error_count=len(value_errors),type_only_error_count=len(type_errors),
            semantic_error_windows=sorted({v['id'] for v in value_errors}),internal_inconsistent_windows=inconsistent,
            field_counts=dict(Counter(r['field'] for r in gate['reasons'])),semantic_errors=value_errors,type_only_errors=type_errors))
        prior=plan
    g.dump(out/'plan_diagnosis.json',dict(versions=results,model_calls=0,native_calls=0,
        private_answers_used_for_local_diagnosis_only=True,old_verdicts_unchanged=True))
    print([(r['version'],r['semantic_error_count'],r['type_only_error_count'],len(r['internal_inconsistent_windows'])) for r in results])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
