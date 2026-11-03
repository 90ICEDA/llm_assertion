"""Reuse raw stream/native audit with the sealed research53 interface hooks."""
import argparse
import copy
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import research52_result_audit as base
import research53_decoded_applicability as interface


def run(prep,root,out):
    with ExitStack() as stack:
        for name in ('source_check','validate','verified_plan','plan_payload','sva_payload'):
            stack.enter_context(patch.object(base.g,name,getattr(interface,name)))
        base.run(prep,root,out)
    context=interface.source_check(prep);expected=interface.fixture(context)
    versions=[];previous=None
    for folder in sorted((root/'plan').glob('v*')):
        value=interface.read(folder/'model_call/model_plan.json')
        verdict=interface.validate(value,context)
        labels={w['id']:w['obligations'] for w in value['windows']}
        wanted={w['id']:w['obligations'] for w in expected['windows']}
        correct=sum(labels.get(k)==v for k,v in wanted.items())
        versions.append(dict(version=folder.name,accepted=verdict['accepted'],
            branch_rule_correct=value['rules']['illegal_branch_persists']==expected['rules']['illegal_branch_persists'],
            op_rule_correct=value['rules']['op_bit28_illegal']==expected['rules']['op_bit28_illegal'],
            actual_rules=value['rules'],sample_labels_correct=correct,sample_labels_total=len(wanted),
            identical_to_previous=value==previous if previous is not None else None,reasons=verdict['reasons']))
        previous=value
    outcome=interface.read(root/'outcome.json')
    assert outcome['status']==('accepted_development_only' if outcome['accepted_candidate_sha256'] else 'no_accepted_sva' if (root/'accepted_plan.json').exists() else 'plan_not_accepted')
    interface.dump(out/'plan_diagnosis.json',dict(versions=versions,local_answer_table_not_sent=True,
        old_verdicts_unchanged=True,model_calls=0,native_calls=0))
    interface.dump(out/'parent_result.json',dict(parent_bug='lowRISC/ibex#166',
        origin='Original upstream decoder RTL, no injected fault',status=outcome['status'],
        new_sva_accepted=bool(outcome['accepted_candidate_sha256']),independent_test='not_run',
        scope='Finite module development evidence. Program supplies decoded fields; model selects rules and labels. No autonomous bit-decoding or formal-proof claim.'))
    print('DECODED_PLAN_DIAGNOSIS',versions,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
