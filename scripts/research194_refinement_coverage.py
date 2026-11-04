"""Evidence-level coverage of six implemented localization families.

Implemented operations, evidence-backed hypotheses, executed repairs, and
independent policy outcomes are deliberately separate levels of support.
"""
import argparse
from pathlib import Path
from research194_refinement_posthoc import read,dump

FAMILIES={
    'trigger':{'trigger_too_narrow','trigger_too_broad'},
    'response':{'response_missing','response_too_strict'},
    'latency_window':{'latency_window','implication_alignment'},
    'transaction_matching':{'transaction_matching'},
    'legal_exception':{'legal_exception'},
    'finite_inactivity':{'finite_inactivity','insufficient_trigger'}}
OPERATIONS={'trigger':['replace_field'], 'response':['replace_field'],
    'latency_window':['set_delay','set_window','replace_field'],
    'transaction_matching':['match_transaction','replace_field'],
    'legal_exception':['except_when','replace_field'],
    'finite_inactivity':['replace_field']}


def analyze(out):
    out=Path(out);calls=read(out/'calls.json',[])
    independent=read(out/'independent_refinement_pairs.json',{})
    rows={name:dict(family=name,implementation_supported=True,operations=OPERATIONS[name],
        evidence_backed_hypothesis_rounds=[],model_local_proposal_associations=[],
        native_local_proposal_associations=[],accepted_local_proposal_associations=[],
        explicit_typed_operator_rounds=[],accepted_explicit_typed_operator_rounds=[],independent_policy_associations=[])
        for name in FAMILIES}
    for call in calls:
        rd=Path(call['record_path']).parent.parent
        findings=read(rd/'localization.json',[]) or []
        measured=read(rd/'current_measurement.json',{})
        confirmed={e['id'] for e in measured.get('evidence',[]) if e.get('status')=='confirmed'}
        raw=read(rd/'model_edit.json',{}) or {}
        if not isinstance(raw,dict):raw={}
        raw_edits=raw.get('edits',[])
        if not isinstance(raw_edits,list):raw_edits=[]
        edit_record=read(rd/'edit_record.json',{}) or {}
        edited={(e.get('assertion'),e.get('field')) for e in raw_edits if isinstance(e,dict) and isinstance(e.get('assertion'),str)}
        changed={(e.get('assertion'),e.get('field')) for e in edit_record.get('changed',[]) if isinstance(e,dict)}
        key=dict(case_id=call['case_id'],seed=call['seed'],arm=call['arm'],bundle=call['bundle'],
            round=call['round'],path=str(rd),stage=call['stage'],accepted=call['accepted'])
        associated=[]
        for family,kinds in FAMILIES.items():
            supported=[f for f in findings if f['kind'] in kinds and set(f.get('evidence_ids',[]))&confirmed]
            if not supported:continue
            rows[family]['evidence_backed_hypothesis_rounds'].append(dict(key,
                kinds=sorted({f['kind'] for f in supported}),
                confirmed_evidence_ids=sorted({eid for f in supported for eid in f.get('evidence_ids',[]) if eid in confirmed})))
            keys={(f['assertion'],f['field']) for f in supported}
            if call['stage']=='local' and edited&keys:
                associated.append(family)
                rows[family]['model_local_proposal_associations'].append(dict(key,fields=sorted(edited&keys)))
                if call['runner_status'] in ('accepted','rejected') and changed&keys:
                    rows[family]['native_local_proposal_associations'].append(dict(key,fields=sorted(changed&keys)))
                    if call['accepted']:
                        rows[family]['accepted_local_proposal_associations'].append(dict(key,fields=sorted(changed&keys),
                            timely_gained=len(call['timely_gained_ids']),any_cycle_gained=len(call['transaction_gained_ids'])))
            explicit=set(OPERATIONS[family])-{'replace_field'}
            if call['stage']=='local' and any(e.get('op') in explicit for e in raw_edits if isinstance(e,dict)):
                rows[family]['explicit_typed_operator_rounds'].append(key)
                if call['accepted'] and any(e.get('op') in explicit for e in edit_record.get('changed',[]) if isinstance(e,dict)):
                    rows[family]['accepted_explicit_typed_operator_rounds'].append(key)
        # One field can support several alternative hypotheses; association is
        # not evidence of a unique causal localization.
        for family in associated:
            rows[family]['model_local_proposal_associations'][-1]['alternative_family_associations']=associated
    matrix=[]
    for family,row in rows.items():
        for accepted in row['accepted_local_proposal_associations']:
            if accepted['bundle']!='base' or not accepted['arm'].startswith('S0_'):continue
            for pair in independent.get('pairs',[]):
                if (pair['case_id']==accepted['case_id'] and pair['seed']==accepted['seed']
                        and pair['comparison']=='R3_vs_R2'):
                    row['independent_policy_associations'].append(dict(case_id=pair['case_id'],seed=pair['seed'],
                        development_local_round=accepted['round'],
                        fault=pair['fault'],eligible=pair['eligible_comparable'],
                        strict_execution_eligible=pair['strict_execution_eligible'],
                        timely_gained=len(pair['timely']['gained_ids']),
                        timely_lost=len(pair['timely']['lost_ids']),
                        any_cycle_gained=len(pair['any_cycle']['gained_ids']),
                        any_cycle_lost=len(pair['any_cycle']['lost_ids']),
                        added_legal_alarms=len(pair['legal_alarm_pair']['added']),
                        interpretation='Frozen entire R3 policy vs R2 association; not isolated localization-family causality.'))
        row['interface_only_so_far']=not row['evidence_backed_hypothesis_rounds']
        row['has_confirmed_native_supporting_evidence']=bool(row['evidence_backed_hypothesis_rounds'])
        row['has_real_model_local_proposal']=bool(row['model_local_proposal_associations'])
        row['has_natively_executed_local_proposal']=bool(row['native_local_proposal_associations'])
        row['has_accepted_local_proposal']=bool(row['accepted_local_proposal_associations'])
        row['has_accepted_explicit_typed_operator']=bool(row['accepted_explicit_typed_operator_rounds'])
        row['cohort_counts']={bundle:{name:sum(x['bundle']==bundle for x in row[name]) for name in
            ('evidence_backed_hypothesis_rounds','model_local_proposal_associations','native_local_proposal_associations',
             'accepted_local_proposal_associations','explicit_typed_operator_rounds','accepted_explicit_typed_operator_rounds')}
            for bundle in ('base','augmentation')}
        row['independent_benefit_status']=('policy_associations_available_not_isolated_family_effect' if row['independent_policy_associations']
            else 'no_matching_S0_R3_vs_R2_association_family_effect_not_established' if independent.get('status')=='completed_read_only' else 'pending_independent_acceptance')
        row['root_cause_uniquely_confirmed']=False
        matrix.append(row)
    result=dict(status='read_only_coverage',families=matrix,
        notes=['The six families have implemented interfaces; that alone is not experimental validation.',
            'Native-confirmed evidence validates behavior labels, not a unique defect localization. Findings remain supported hypotheses.',
            'Evidence-backed family coverage here requires a saved actual localization record. Interrupted diagnostics with unmapped obligations are reported separately, not retroactively classified with the isolated next-version adapter.',
            'A replacement field may match several hypothesis families; associated counts are overlapping, not independent successful repairs.',
            'In particular a trigger range change associated with a latency hypothesis is not proof of a repaired timing window; explicit typed operators are counted separately.',
            'Byte-identical edits are excluded from natively executed/accepted changed-field associations.',
            'Independent whole-policy R3-vs-R2 benefits cannot isolate one localization family.'])
    dump(out/'localization_mechanism_coverage.json',result)
    print([{k:r[k] for k in ('family','has_confirmed_native_supporting_evidence','has_real_model_local_proposal','has_accepted_local_proposal','independent_benefit_status')} for r in matrix])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);analyze(p.parse_args().out)
