"""Seeded public-specification schedules; no simulator or held-out result reads."""
import random
from research194_cases import digest,get_case

CASES=('arbiter','counter')
LENGTHS=(24,72,216)
FAMILIES={
    'arbiter':('priority_stream','held_grant','ack_pause','reset_inflight','withdraw_request','repeated_handoffs'),
    'counter':('up_boundary','down_boundary','load_arbitration','clear_arbitration','enable_pause','reset_inflight')}
OBLIGATIONS={
    'priority_stream':['arbiter_priority','arbiter_valid'],'held_grant':['arbiter_hold','arbiter_valid'],
    'ack_pause':['arbiter_hold','arbiter_priority'],'withdraw_request':['arbiter_hold','arbiter_valid'],
    'repeated_handoffs':['arbiter_priority','arbiter_valid'],
    'up_boundary':['counter_step','counter_boundary'],'down_boundary':['counter_step','counter_boundary'],
    'load_arbitration':['counter_load','counter_step'],'clear_arbitration':['clear_cancel','counter_load'],
    'enable_pause':['counter_step']}


def generate_query(case_id,family,length,seed,split='development'):
    if case_id not in CASES or family not in FAMILIES[case_id]:raise ValueError('case_or_family')
    if split not in ('development','independent'):raise ValueError('split')
    if length<16:raise ValueError('schedule_too_short')
    key=dict(case=case_id,family=family,length=length,seed=seed,split=split)
    rng=random.Random(int(digest(key)[:16],16));rows=[]
    reset_length=3 if split=='development' else 5
    masks=(1,3,6,8,15) if split=='development' else (2,4,5,9,10)
    values=(0,1,7,14,15) if split=='development' else (2,5,9,11,13)
    period=rng.choice((5,7,9));hold=rng.choice((2,3,4));initial=rng.choice(values)
    for i in range(length):
        t=i-reset_length;tail=i>=length-3
        if case_id=='arbiter':
            reset=i<reset_length or (family=='reset_inflight' and t>=0 and t%period==period-2)
            request=rng.choice(masks) if not tail and not reset else 0
            acknowledge=15
            if family=='held_grant':acknowledge=15 if t%period==0 else 0
            elif family=='ack_pause':acknowledge=0 if t%period<hold else 15
            elif family=='withdraw_request':
                if t%period in (2,3):request=0
                acknowledge=15 if t%period==period-1 else 0
            elif family=='repeated_handoffs':acknowledge=15 if t%2 else 0
            if tail:acknowledge=15
            rows.append(dict(rst=int(reset),request=request,acknowledge=0 if reset else acknowledge))
        else:
            reset=i<reset_length or (family=='reset_inflight' and t>=0 and t%period==period-2)
            row=dict(rst_n=int(not reset),clr=0,en=int(not reset and not tail),load=int(t==0),down=int(family=='down_boundary'),d=initial)
            if family=='load_arbitration' and t>=0 and t%period==0:row.update(load=1,en=1,d=rng.choice(values))
            if family=='clear_arbitration' and t>=0 and t%period==0:row.update(clr=1,load=1,en=1,d=rng.choice(values))
            if family=='enable_pause':row['en']=int(not reset and not tail and t%period>=hold)
            if family=='reset_inflight' and t>=0 and t%period==period-1:row.update(load=1,d=rng.choice(values))
            if reset or tail:row.update(clr=0,en=0,load=0)
            rows.append(row)
    obligations=(['reset_cancel','arbiter_valid'] if case_id=='arbiter' else ['reset_cancel','counter_step']) if family=='reset_inflight' else OBLIGATIONS[family]
    return dict(id=f'{case_id}/{family}/n{length}/{digest(rows)[:12]}',family=family,rows=rows,obligations=obligations,
        dimensions=['trigger','response','window','transaction','exception'],estimated_cost=2*length,split=split,
        semantic_key=digest(dict(case=case_id,inputs=rows)),generator_parameters=dict(key,period=period,hold=hold,initial=initial),
        constraints=['Fixed pre-edge sample convention; public specification and seeded inputs only.',
            'Reset cancels outstanding obligations; final three quiet samples drain next-sample assertions.',
            'Acknowledgement and request changes are explicit open-loop schedules; grant ownership is judged by the independent monitor.' if case_id=='arbiter' else
            'Counter priority is reset, clear, load, enabled step, hold; load/en/clear overlaps are intentional legal priority tests.'],
        evidence_visibility='public_development' if split=='development' else 'reserved_independent_after_freeze')


def query_pool(case_id,seed,split='development'):
    return [generate_query(case_id,family,length,seed,split) for family in FAMILIES[case_id] for length in LENGTHS]


def coverage(query):
    rows=query['rows'];case=query['generator_parameters']['case']
    result=dict(samples=len(rows),family=query['family'],declared_obligations=query['obligations'],input_sha256=digest(rows))
    if case=='arbiter':
        result.update(request_changes=sum(a['request']!=b['request'] for a,b in zip(rows,rows[1:])),
            request_with_no_ack=sum(bool(r['request']) and not r['acknowledge'] and not r['rst'] for r in rows),
            concurrent_requests=sum(r['request'].bit_count()>1 for r in rows),resets=sum(bool(r['rst']) for r in rows))
    else:
        result.update(enabled_samples=sum(r['en'] for r in rows),disabled_samples=sum(r['rst_n'] and not r['en'] for r in rows),
            loads=sum(r['load'] for r in rows),clear_load_overlap=sum(r['clr'] and r['load'] for r in rows),resets=sum(not r['rst_n'] for r in rows))
    return result
