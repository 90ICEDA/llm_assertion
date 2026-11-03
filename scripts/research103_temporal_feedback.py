"""Bind antecedent and consequent samples to raw native markers, not prose."""
import copy
import json
import re
from pathlib import Path
import research99_request_presentation as fmt
import research57_label_replay as raw

p=fmt.prior;x=p.x
read,dump,sha,ROOT=p.read,p.dump,p.sha,p.ROOT


def context(folder,candidate,records):
    """Load only explicitly allowed cohorts from an already executed version."""
    result={}
    for cohort,r in records.items():
        traces={};markers={}
        for revision in ('before','after'):
            path=folder/cohort/revision/'execute.log'
            traces[revision]=raw.g.common.trace(path)
            text=path.read_text()
            markers[revision]={kind:{(name,int(cycle)) for name,cycle in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',text,re.M)} for kind in ('TRIGGER','ASSERT_FAIL')}
        result[cohort]=dict(records=r,trace=traces,markers=markers,
            assertions={a['id']:a for a in candidate['assertions']})
    return result


def bind(ctx,cohort,evidence_id,assertion_id):
    c=ctx[cohort];rows=[r for r in c['records']['ledger'] if r['evidence_id']==evidence_id]
    if len(rows)!=1:raise ValueError('evidence_identity')
    row=rows[0];prop=c['assertions'][assertion_id];timing=prop['timing']
    delay={'same_sample':0,'next_sample':1}.get(timing)
    if delay is None or prop['delay']!=delay:raise ValueError('unsupported_or_inconsistent_delay')
    revision=row['revision'];config=row['configuration'];sid=row['sample']['sample_id'];anchor_id=sid-delay
    if anchor_id<0:raise ValueError('no_observed_anchor')
    ci=x.old.CONFIGS.index(config);name=assertion_id+f'_c{ci}'
    def sample(sample_id):
        refs=[r for r in c['records']['reference'] if r['sample_id']==sample_id and r['configuration']==config]
        if len(refs)!=1:raise ValueError('sample_configuration_binding')
        ref=refs[0];t=c['trace'][revision].get(sample_id)
        if t is None:raise ValueError('missing_native_sample')
        for field,key,base in [('instruction','instr',16),('instr_new','new',10),('transaction_id','txn',10),('phase','phase',10)]:
            if ref[field]!=int(t[key],base):raise ValueError('native_'+field)
        actual=(int(t['observed'],2)>>ci)&1
        if ref['actual'][revision]!=actual:raise ValueError('native_output')
        expected=x.old.historical.oracle(ref['instruction'],ref['instr_new'],config)
        if ref['expected']!=expected:raise ValueError('reference_expected')
        w=ref['instruction']
        return dict(sample_id=sample_id,transaction_id=ref['transaction_id'],phase_index=ref['phase'],
            instr_new=ref['instr_new'],phase_name='first' if ref['instr_new'] else 'held',
            instruction_hex=f'0x{w:08x}',opcode=w&127,bit28=(w>>28)&1,bit31=(w>>31)&1,
            expected_illegal=expected,actual_illegal=actual)
    anchor=sample(anchor_id);check=sample(sid)
    for field in ('sample_id','transaction_id','instr_new'):
        if check[field]!=row['sample'][field]:raise ValueError('ledger_'+field)
    if row['sample']['phase']!=check['phase_index'] or row['sample']['instruction']!=int(check['instruction_hex'],16):raise ValueError('ledger_phase_or_word')
    if row['expected']!=check['expected_illegal'] or row['observed']!=check['actual_illegal']:raise ValueError('ledger_outputs')
    markers=c['markers'][revision]
    triggered=(name,anchor_id) in markers['TRIGGER'];failed=(name,sid) in markers['ASSERT_FAIL']
    marks=[m for m in row['native']['assertions'] if m['id']==assertion_id]
    if len(marks)!=1 or marks[0]['trigger']!=triggered or marks[0]['failed']!=failed:raise ValueError('native_marker_binding')
    if any(row['native'][key]!=val for key,val in [('compile','ok'),('execution','ok'),('support','supported')]):raise ValueError('unhealthy_native')
    return dict(cohort=cohort,check_evidence_id=evidence_id,configuration=config,revision=revision,
        assertion_id=assertion_id,timing=timing,delay=delay,anchor=anchor,check=check,
        transaction_switched=anchor['transaction_id']!=check['transaction_id'],
        instruction_changed=anchor['instruction_hex']!=check['instruction_hex'],
        anchor_antecedent_cover=triggered,
        check_cycle_antecedent_cover=(name,sid) in markers['TRIGGER'],
        check_assertion_failed=failed,
        marker_binding=dict(antecedent_cycle=anchor_id,assertion_failure_cycle=sid,configuration_label=name),
        status='bound_to_native_trace_and_markers')


def validate(event,ctx):
    expected=bind(ctx,event['cohort'],event['check_evidence_id'],event['assertion_id'])
    if event!=expected:raise ValueError('temporal_event_mismatch')
    return True


def selected_events(candidate,records,folder,visible):
    allowed={c:records[c] for c in visible['visible_counts']};ctx=context(folder,candidate,allowed)
    failures=[];controls=[];seen=set()
    # One actual selected false-alarm event per allowed cohort. No test outcomes.
    for e in visible['development_counterexamples']:
        if e['kind']!='false_positives' or e['cohort'] in seen:continue
        for a in e['native']['assertions']:
            if not a['failed']:continue
            event=bind(ctx,e['cohort'],e['evidence_id'],a['id'])
            failures.append(event);seen.add(e['cohort']);break
    # Two actual positive controls, first and held; always development alignment.
    # Do not tell the model that changing its text is sufficient for acceptance.
    if 'alignment' in allowed:
        phases=set()
        for row in allowed['alignment']['ledger']:
            if row['revision']!='before' or row['obligation']!='op_bit28_illegal' or row['expected']==row['observed']:continue
            phase=bool(row['sample']['instr_new'])
            if phase in phases:continue
            for a in row['native']['assertions']:
                if a['trigger'] and a['causal_detection']:
                    controls.append(bind(ctx,'alignment',row['evidence_id'],a['id']));phases.add(phase);break
    for e in failures+controls:validate(e,ctx)
    return dict(false_alarm_boundaries=failures,preserve_first_and_held_controls=controls,
        selection='First existing false-positive example per allowed cohort; first detected OP first/held example in alignment. No independent evidence.',
        semantics='anchor_antecedent_cover is the raw cover at the starting sample. check_assertion_failed is the raw failure at the consequent sample. check_cycle_antecedent_cover is a distinct event; do not confuse it with the starting cover.')


def request(candidate,records,folder,iteration,diagnostic=None):
    visible=p.feedback(None,records,True)
    req=fmt.request(candidate,visible,records,'T',iteration,diagnostic)
    body=json.loads(req['messages'][1]['content'])
    body['actual_feedback']['temporal_binding']=selected_events(candidate,records,folder,visible)
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['seed']=10407+iteration
    return req
