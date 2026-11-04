"""Posthoc legal-alarm history audit. Reads development artifacts only.

This never changes the sealed controller, dispatches models, or reruns RTL.
Fine identity excludes assertion labels and preserves full correct trace context.
"""
import argparse
from collections import defaultdict
from pathlib import Path
import re
import time
from research194_refinement_posthoc import read, dump, digest, identity


def alarm_set(measurement, candidate):
    jobs = defaultdict(list)
    for job in measurement.get('executions', []):
        if job.get('variant') == 'correct':
            ref = job.get('reference', {})
            result = job.get('result', {})
            if (result.get('compile_status') == 'passed' and
                    result.get('execution_status') == 'completed' and
                    not ref.get('unknown') and ref.get('checks') and
                    all(c.get('passed') is True for c in ref['checks'])):
                jobs[job['query_id']].append(job)
    contexts = {q: {digest(j['trace']) for j in rows} for q, rows in jobs.items()}
    indices = {a['label']: i for i, a in enumerate(candidate)}
    events = {}; unresolved = []
    for ev in measurement.get('evidence', []):
        if not (ev.get('variant') == 'correct' and ev.get('status') == 'confirmed' and ev.get('label') == 'legal'):
            continue
        failed = [a for a in ev.get('assertions', []) if a.get('failure') is True]
        if not failed:
            continue
        q = ev.get('query_id'); cycle = ev.get('cycle')
        for a in failed:
            # Pooled acquisition prefixes are projected to original names. The
            # current candidate is always pool index zero in sealed acquisition.
            label = a['assertion']; labels = {label}
            if label in indices: labels.add('c0_a' + str(indices[label]))
            matched = []
            for j in jobs.get(q, []):
                if ev.get('source_log') and Path(ev['source_log']).parent != Path(j['folder']):
                    continue
                for marker in j['result'].get('failures', []):
                    match = re.search(r'cycle=(\d+)', marker.get('detail', ''))
                    if marker.get('id') in labels and match and int(match[1]) == cycle:
                        matched.append(j)
            if not matched:
                unresolved.append(dict(query_id=q, cycle=cycle, assertion=label,
                    reason='No corresponding completed native marker on wholly legal correct trace'))
                continue
            obligations = [ev['obligation']] if ev.get('obligation') else a.get('obligations', [None])
            for ob in obligations:
                key = (q, 'correct', cycle, ob)
                row = events.setdefault(key, dict(query_id=q, variant='correct', cycle=cycle,
                    obligation=ob, coarse_ids=[], native_logs=[], correct_trace_sha256=[]))
                row['coarse_ids'] = sorted(set(row['coarse_ids']) | {ev.get('evidence_id', ev['id'])})
                row['native_logs'] = sorted(set(row['native_logs']) | {str(Path(j['folder'])/'execute.log') for j in matched})
                row['correct_trace_sha256'] = sorted(set(row['correct_trace_sha256']) | {digest(j['trace']) for j in matched})
    return events, contexts, unresolved


def compare(before, after, before_candidate, after_candidate):
    b, bc, bu = alarm_set(before, before_candidate)
    a, ac, au = alarm_set(after, after_candidate)
    # Same query ID alone is insufficient if a changed stimulus reused its name.
    common = {q for q in bc.keys() & ac.keys() if bc[q] == ac[q] and len(bc[q]) == 1}
    before_ids = {x['id'] for x in before.get('false_positives', [])}
    new = [dict(a[k], hidden_by_existing_coarse_id=bool(set(a[k]['coarse_ids']) & before_ids))
           for k in sorted(a.keys() - b.keys(), key=str) if k[0] in common]
    return dict(before_alarm_units=len(b), after_alarm_units=len(a),
        matched_wholly_legal_correct_queries=sorted(common),
        newly_acquired_or_unmatched_query_alarm_units=sum(k[0] not in common for k in a),
        new_legal_alarm_events_on_same_queries=new,
        coarse_id_masked_new_legal_alarm_events=[x for x in new if x['hidden_by_existing_coarse_id']],
        unresolved_native_marker_bindings=bu+au,
        query_trace_mismatch=sorted(q for q in bc.keys() & ac.keys() if bc[q] != ac[q]))


def analyze(root, out):
    root=Path(root).resolve(); rows=[]; pending=[]
    for bundle in ('base', 'augmentation'):
        for folder in sorted((root/bundle).glob('*/*/*/refinement')):
            candidate=read(folder/'initial.json')
            if candidate is None: continue
            for rd in read(folder/'rounds.json', []) or []:
                if rd.get('status') != 'accepted': continue
                path=folder/('round%02d'%rd['round'])
                before=read(path/'current_measurement.json')
                after=read(path/'proposal_native'/'measurement.json')
                proposal=read(path/'proposal.json')
                ident=dict(identity(folder,root),round=rd['round'],round_path=str(path))
                if before is None or after is None or proposal is None:
                    pending.append(ident)
                else:
                    rows.append(dict(ident,**compare(before,after,candidate,proposal)))
                if proposal is not None: candidate=proposal
    summary=dict(snapshot_unix=time.time(),scope='accepted development proposals only; immutable original verdicts',
        accepted_rounds_audited=len(rows),pending_accepted_rounds=len(pending),
        rounds_with_new_legal_alarms=sum(bool(x['new_legal_alarm_events_on_same_queries']) for x in rows),
        rounds_with_coarse_id_masked_new_legal_alarms=sum(bool(x['coarse_id_masked_new_legal_alarm_events']) for x in rows),
        new_legal_alarm_units=sum(len(x['new_legal_alarm_events_on_same_queries']) for x in rows),
        coarse_id_masked_new_legal_alarm_units=sum(len(x['coarse_id_masked_new_legal_alarm_events']) for x in rows),
        unresolved_marker_bindings=sum(len(x['unresolved_native_marker_bindings']) for x in rows),
        identity='query_id + correct variant + cycle + obligation; matching full correct trace SHA256, assertion label ignored',
        sealed_files_modified=False,new_native_executions=0,new_model_calls=0)
    dump(Path(out)/'legal_alarm_history_audit.json',dict(summary=summary,rounds=rows,pending=pending))
    print(summary,flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();analyze(a.campaign,a.out)
