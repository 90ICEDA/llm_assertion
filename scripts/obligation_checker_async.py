"""Qualified optional checker extension: clear pN history on between-edge reset.

Frozen r02/r04 experiments keep the original sampled-history executor. This
module is a separate correction, not retroactively substituted in their logs.
"""
import argparse
import copy
from pathlib import Path
import contract_v3_checker as original
import run_obligation_evidence as x


def tb_text(d,rows,candidates,param=None):
    text=original.tb_text(d,rows,candidates,param)
    before=f'always @(posedge {d["clk"]}) begin\np1_'
    after=f'always @(posedge {d["clk"]} or negedge {d["rst"]}) begin\np1_'
    assert text.count(before)==1
    return text.replace(before,after,1)


def qualify(run):
    out=x.ROOT/'deliverables'/run/'async_history_qualification';out.mkdir(exist_ok=False)
    d=x.definition('onehot');rows=[]
    for i,(reset,value) in enumerate([(0,0),(1,2),(1,2),(1,0),(1,0)]):
        r={n:0 for n in d['inputs']};r.update({d['rst']:reset,'oh_i':value,'en_i':1,'cycle':i,'stimulus_id':f'qa:{i}'})
        rows.append(r)
    c=dict(id='qa_history_clear',antecedent='1',consequent='p1_oh_i == 0',delay=0,
           provenance='hand_authored_executor_QA',authorized_history_depth=3)
    results=[]
    for pulse in (False,True):
        records={}
        for version,fn in [('original',original.tb_text),('async_history',tb_text)]:
            folder=out/(version+('_pulse' if pulse else '_sampled'));folder.mkdir()
            text=fn(d,rows,[c]);marker='\n'.join(f'{n}={rows[3][n]};' for n in [d['rst'],*d['inputs']])
            # cycle 3 has the same values as cycle 4; insert at the first occurrence.
            if pulse:text=text.replace(marker,marker+f'\n#1 {d["rst"]}=0; #1 {d["rst"]}=1;',1)
            (folder/'checker_tb.sv').write_text(text)
            source=x.ROOT/'deliverables'/run/'frozen/onehot/correct.v'
            (folder/'rtl.v').write_bytes(source.read_bytes())
            b=x.command(['iverilog','-g2012','-s','tb','-o','sim.out','rtl.v','checker_tb.sv'],folder,'compile')
            assert b['status']=='ok'
            s=x.command(['vvp','sim.out'],folder,'simulate');assert s['status']=='ok'
            trace,checks=x.parse_stdout(folder/'simulate.stdout');records[version]=checks[0]
            x.dump(folder/'input.json',rows);x.dump(folder/'checks.json',checks)
            (folder/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd "'+str(folder)+'"\niverilog -g2012 -s tb -o sim.out rtl.v checker_tb.sv\nvvp sim.out\n')
        if not pulse:assert records['original']==records['async_history']
        else:
            a=next(r for r in records['original'] if r['cycle']==3)
            b=next(r for r in records['async_history'] if r['cycle']==3)
            assert a['fail']==1 and b['fail']==0
        results.append(dict(between_edge_reset=pulse,checks=records))
    x.dump(out/'result.json',dict(passed=True,original_history_semantics='only sampled reset clears pN; between-edge pulses leave stale pN',
        corrected_semantics='pN observer block also sensitive to active-low reset; pending antecedents already asynchronous',
        results=results,new_checker_sha256=x.sha(Path(__file__)),used_in_search_or_refinement=False,
        interpretation='Real checker limitation, not candidate failure. Existing results apply only to sampled reset schedules. Extension separately qualified on this witness; not native SVA equivalence proof.'))
    print('async history limitation reproduced; extension qualified; frozen experiments unchanged')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);qualify(p.parse_args().run)
