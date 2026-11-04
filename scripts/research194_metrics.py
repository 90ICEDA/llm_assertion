"""Read-only timing versus transaction detection, from actual native markers."""


def temporal_detection(measurement):
    targets=set(measurement.get('targets',[]));first={};alarms={}
    for ev in measurement.get('evidence',[]):
        if ev.get('status')!='confirmed' or ev.get('label')!='violation':continue
        eid=ev.get('evidence_id',ev.get('id'))
        if eid not in targets:continue
        if ev.get('counted_target'):first[eid]=min(first.get(eid,ev['cycle']),ev['cycle'])
        if any(a.get('failure') is True and ev['obligation'] in a.get('obligations',[]) for a in ev.get('assertions',[])):
            alarms[eid]=min(alarms.get(eid,ev['cycle']),ev['cycle'])
    timely=set(measurement.get('detected_ids',[]));detected=set(alarms)
    return dict(timely_detected_ids=sorted(timely),transaction_detected_ids=sorted(detected),
        late_detected_ids=sorted(detected-timely),transaction_missed_ids=sorted(targets-detected),
        detection_delay_cycles={eid:alarms[eid]-first[eid] for eid in detected if eid in first},
        detection_scope='Targets collapse each oracle transaction and obligation. Timely requires an alarm at its first violating sample; transaction detection permits a matching alarm at any independently violating sample in the same transaction. No cross-obligation or legal-cycle alarm receives credit.')
