"""Native SVA bounded-response/tag semantics qualification, NOT an RTL bug case.

Drives explicitly synthetic interface waveforms through the existing native SVA
executor. The independent Python event monitor owns the oracle. Prospective
obligations are checked at their deadline using native $past; no procedural
replacement of assertions and no claim of arbitrary ## sequence support.
"""
import argparse
import copy
from pathlib import Path
import re
from research_native_runner import run_native
from research194_refinement_runner import dump,read,file_hash


FIELDS=('rst_n','flush','req_valid','req_ready','req_id','req_data','rsp_valid','rsp_ready','rsp_id','rsp_data')


def waves():
    rows=[dict(rst_n=int(i>=3),flush=0,req_valid=0,req_ready=1,req_id=3,req_data=0,
        rsp_valid=0,rsp_ready=1,rsp_id=0,rsp_data=0) for i in range(34)]
    for t,tag,data in ((6,0,0x31),(7,1,0xa7),(8,2,0x55),(12,0,0x22),(16,3,0x43),(21,1,0x33)):
        rows[t].update(req_valid=1,req_id=tag,req_data=data)
    for t,tag,data in ((8,1,0xa7),(9,0,0x31),(10,2,0x55),(17,3,0x43),(18,3,0x43)):
        rows[t].update(rsp_valid=1,rsp_id=tag,rsp_data=data)
    rows[17]['rsp_ready']=0
    rows[11].update(req_valid=1,req_ready=0,req_id=0,req_data=0x99)
    rows[13]['flush']=1;rows[22]['rst_n']=0;rows[23]['rst_n']=0
    result={'legal_reorder_cancel_backpressure':rows}
    late=copy.deepcopy(rows);late[9]['rsp_valid']=0
    # Move tag 0 beyond its deadline without replacing tag 2's valid response.
    late[10].update(rsp_valid=1,rsp_id=0,rsp_data=0x31)
    late[11].update(rsp_valid=1,rsp_id=2,rsp_data=0x55)
    result['late_response']=late
    wrong=copy.deepcopy(rows);wrong[8]['rsp_id']=2;result['wrong_response_tag']=wrong
    dropped=copy.deepcopy(rows);dropped[18]['rsp_valid']=0;result['dropped_response']=dropped
    return result


def oracle(rows,lo=1,hi=3):
    pending={};violations=[];unknown=[];completed=[];cancelled=[];max_pending=0
    for t,r in enumerate(rows):
        if not r['rst_n'] or r['flush']:
            cancelled.extend(pending.values());pending={};continue
        if r['rsp_valid'] and r['rsp_ready']:
            tag=r['rsp_id'];request=pending.pop(tag,None)
            if request is None:violations.append(dict(cycle=t,kind='unmatched_response',response_tag=tag))
            else:
                age=t-request['cycle']
                if not lo<=age<=hi:violations.append(dict(cycle=t,kind='response_window',request=request,age=age))
                if request['data']!=r['rsp_data']:violations.append(dict(cycle=t,kind='response_data',request=request))
                completed.append(dict(request=request,response_cycle=t))
        if r['req_valid'] and r['req_ready']:
            tag=r['req_id']
            if tag in pending:unknown.append(dict(cycle=t,reason='request_tag_reused_while_pending'))
            else:pending[tag]=dict(cycle=t,tag=tag,data=r['req_data'])
        max_pending=max(max_pending,len(pending))
        for tag,req in list(pending.items()):
            if t>=req['cycle']+hi:
                violations.append(dict(cycle=t,kind='response_deadline',request=req));del pending[tag]
    unknown += [dict(request=r,reason='incomplete_trace_tail') for r in pending.values()]
    return dict(status='unknown' if unknown else 'violation' if violations else 'legal',violations=violations,
        unknown=unknown,completed=completed,cancelled=cancelled,max_simultaneously_pending=max_pending)


def past(expression,delay):return '('+expression+')' if delay==0 else f'$past(({expression}),{delay})'


def assertions(name,lo,hi,match_id):
    if not 1<=lo<=hi<=8:raise ValueError('bounded_response_1_to8')
    request='req_valid && req_ready';response='rsp_valid && rsp_ready'
    uncancelled=' && '.join('!'+past('flush || !rst_n',k) for k in range(hi))
    ant=f'{past(request,hi)} && ({uncancelled})'
    terms=[];origins=[]
    for delay in range(lo,hi+1):
        offset=hi-delay
        term=f'{past(response,offset)} && ({past("rsp_data",offset)} == {past("req_data",hi)})'
        if match_id:term+=f' && ({past("rsp_id",offset)} == {past("req_id",hi)})'
        terms.append('('+term+')')
        origin=f'{past(request,delay)} && (rsp_data == {past("req_data",delay)})'
        if match_id:origin+=f' && (rsp_id == {past("req_id",delay)})'
        origin+=' && '+' && '.join('!'+past('flush || !rst_n',k) for k in range(delay))
        origins.append('('+origin+')')
    return [dict(label=name+'_deadline',antecedent=ant,consequent=' || '.join(terms),obligations=['bounded_response']),
        dict(label=name+'_match',antecedent=response,consequent=' || '.join(origins),obligations=['response_matching'])]


def bench(rows,props):
    code=['module tb;','bit clk=0; always #5 clk=~clk;','integer cycle=-1;']
    for name in FIELDS:
        width='[1:0] ' if name.endswith('_id') else '[7:0] ' if name.endswith('_data') else ''
        code.append(f'logic {width}{name}=0;')
    for a in props:
        label=a['label'];ant=a['antecedent'];cons=a['consequent']
        code.append(f'{label}: assert property (@(posedge clk) disable iff(!rst_n) ({ant}) |-> ({cons})) else $display("ASSERT_FAIL {label} cycle=%0d",$sampled(cycle));')
        code.append(f'assert property (@(posedge clk) disable iff(!rst_n) !({ant})) else $display("TRIGGER {label} cycle=%0d",$sampled(cycle));')
    code+=['initial begin','$dumpfile("wave.vcd");$dumpvars(0,tb);']
    for t,row in enumerate(rows):
        code.append('@(negedge clk); cycle='+str(t)+'; '+' '.join(f'{k}={v};' for k,v in row.items()))
    code+=['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end','endmodule']
    return '\n'.join(code)


def run(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    versions={k:assertions(k,*args) for k,args in {'wide_window':(1,4,True),'unmatched_id':(1,3,False),'bounded_matched':(1,3,True)}.items()}
    schedule=waves();dump(out/'protocol.json',dict(scope=__doc__,model_calls=0,rtl_bug_claim=False,versions=versions,waveforms=schedule,
        source_sha256=file_hash(__file__),known_limits=['Bounds up to 8 sampled cycles; no tag reuse while outstanding.',
            'Input/response waveforms are synthetic controls, not executions of a repaired upstream RTL design.']))
    rows=[]
    for name,wave in schedule.items():
        truth=oracle(wave);native=run_native(bench(wave,[a for v in versions.values() for a in v]),out/name/'native')
        grades=[]
        for version,props in versions.items():
            labels={a['label'] for a in props};fails=[x for x in native.get('failures',[]) if x['id'] in labels]
            triggers=[x for x in native.get('triggers',[]) if x['id'] in labels]
            healthy=native['compile_status']=='passed' and native['execution_status']=='completed'
            grades.append(dict(version=version,native_executable=healthy,trigger_count=len(triggers),failures=fails,
                verdict='unknown' if not healthy or truth['unknown'] or not triggers else 'alarm' if fails else 'no_alarm'))
        rows.append(dict(waveform=name,oracle=truth,grades=grades,native=native));dump(out/'results.json',rows)
    ok=all(g['native_executable'] for r in rows for g in r['grades'])
    expected=all(next(g for g in r['grades'] if g['version']=='bounded_matched')['verdict']==('no_alarm' if r['oracle']['status']=='legal' else 'alarm') for r in rows)
    dump(out/'outcome.json',dict(status='qualified' if ok and expected else 'unknown_or_mismatch',model_calls=0,
        native_jobs=len(rows),max_simultaneously_pending=max(r['oracle']['max_simultaneously_pending'] for r in rows),
        scope='Native assertion semantics qualification only; not LLM repair, RTL mutation validation, or unseen-fault generalization.'))
    print(read(out/'outcome.json'),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
