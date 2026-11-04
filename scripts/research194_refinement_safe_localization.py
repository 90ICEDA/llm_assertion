"""ISOLATED NEXT-VERSION ADAPTER. Not imported by the sealed R194 campaign.

Unmapped obligation evidence remains unchanged in the returned evidence and
must still reach native replay/FP acceptance checks. Only diagnostic permission
to modify an assertion is withheld when its obligation cannot be mapped.
"""
import copy
import research194_refinement as sealed_localizer


def safe_localize(candidate, evidence):
    original=copy.deepcopy(evidence)
    normalized=sealed_localizer.normalize_evidence(evidence)
    unmapped={r['id'] for r in normalized if not isinstance(r.get('obligation'),str) or not r['obligation'].strip()}
    diagnostic=copy.deepcopy(normalized)
    # Keep ALL samples and assertion-specific trigger facts. Dropping unmapped
    # samples could manufacture finite inactivity by losing a real trigger.
    # Empty text is a private regex input only; it is never an obligation label
    # sent to the model, oracle, gate, measurement, or original evidence.
    for row in diagnostic:
        if row['id'] in unmapped:row['obligation']=''
    candidates=sealed_localizer.localize(candidate,diagnostic)
    actionable=[];withheld=[]
    for finding in candidates:
        good=[eid for eid in finding['evidence_ids'] if eid not in unmapped]
        bad=[eid for eid in finding['evidence_ids'] if eid in unmapped]
        if good:actionable.append(dict(finding,evidence_ids=good))
        if bad:withheld.append(dict(finding,evidence_ids=bad,status='unknown_unmapped_obligation_no_edit_permission'))
    unknown=[dict(evidence_id=row['id'],obligation=copy.deepcopy(row.get('obligation')),
        status='unknown_unmapped_obligation',editable_fields=[],
        oracle_status=row['status'],oracle_label=row['label'],
        assertions=copy.deepcopy(row['assertions']),query_id=row.get('query_id'),cycle=row.get('cycle'),
        reason='The behavior label and native facts are retained; no obligation-grounded localization is authorized.')
        for row in normalized if row['id'] in unmapped]
    return dict(adapter_scope='isolated_next_version_not_used_in_sealed_campaign',
        status='partial_unknown' if unknown else 'localized',evidence=original,
        actionable_findings=actionable,unmapped_localizations=unknown,withheld_hypotheses=withheld,
        oracle_labels_modified=False,evidence_records_dropped=0,
        gate_instruction='Replay every original evidence record, including unmapped legal alarms; localization uncertainty never makes an alarm legal or irrelevant.')
