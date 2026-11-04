"""Read-only representative development cards selected by execution status."""
import argparse
from pathlib import Path
from research194_refinement_posthoc import read,dump,request_context


def card(call):
    rd=Path(call['record_path']).parent.parent
    _,context=request_context(rd/'model_call')
    before=read(rd/'current_measurement.json',{})
    after=read(rd/'proposal_native'/'measurement.json',{})
    gained=set(call.get('transaction_gained_ids',[]))
    ev=next((e for e in after.get('evidence',[]) if e.get('id') in gained and any(a.get('failure') for a in e.get('assertions',[]))),None)
    if ev is None:
        ev=next((e for e in before.get('evidence',[]) if e.get('label')=='violation' and e.get('status')=='confirmed' and e.get('counted_target')),None)
    waveform=[]
    if ev:
        source=after if gained else before
        job=next((j for j in source.get('executions',[]) if j.get('query_id')==ev.get('query_id') and j.get('variant')==ev.get('variant')),None)
        if job:
            cy=ev['cycle'];waveform=[r for r in job.get('trace',[]) if cy-2<=r.get('cycle',-100)<=cy+2]
    return dict(call=call,original_assertions=context.get('current_assertions'),
        raw_model_edit=read(rd/'model_edit.json'),proposed_assertions=read(rd/'proposal.json'),
        localization=read(rd/'localization.json'),edit_record=read(rd/'edit_record.json'),
        fallback_receipt=context.get('fallback_receipt'),key_evidence=ev,key_waveform=waveform,
        waveforms_from='proposal_native' if gained else 'current_baseline',
        native_proposal_executed=bool(after),before_measurement=str(rd/'current_measurement.json'),
        proposal_measurement=str(rd/'proposal_native'/'measurement.json') if after else None,
        independent_acceptance='pending; this card uses development data only',
        caution='An interface-rejected proposal has no proposal waveform. A baseline waveform is identified as such.')


def analyze(out):
    out=Path(out);calls=read(out/'calls.json',[]);cards={}
    predicates={
        'first_real_local_accept':lambda c:c['stage']=='local' and c['accepted'],
        'first_structural_composition_accept':lambda c:c['stage']=='compose' and c['accepted'] and c['fallback_authorization']=='structural_empty_domain',
        'first_local_interface_reject':lambda c:c['stage']=='local' and c['runner_status']=='interface_rejected',
        'first_measured_regeneration_failure':lambda c:c['stage']=='regenerate' and c['runner_status']=='rejected',
        'first_measured_regeneration_accept':lambda c:c['stage']=='regenerate' and c['accepted'],
        'first_actual_historical_detection_loss':lambda c:c['proposed_history_regression'],
        'first_output_budget_truncation':lambda c:c['result_status']=='response_truncated'}
    for name,p in predicates.items():
        row=next((c for c in calls if p(c)),None)
        cards[name]=card(row) if row else dict(status='not_observed')
    dump(out/'representative_development_cards.json',cards)
    print({name:row.get('call',{}).get('record_path',row.get('status')) for name,row in cards.items()})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    analyze(p.parse_args().out)
