"""Executable checker qualification, hand-authored vectors + independent Python oracle."""
import itertools,json,shlex,sys
from pathlib import Path
import run_repair_contract as e
import contract_v3_checker as c

OUT=e.ROOT/'deliverables/repair_contract_v3_20261010'

def simulate(name,decls,rows,cs,functions='',between_reset=False):
    p=OUT/'qualification'/name;p.mkdir(parents=True,exist_ok=True)
    body=['`timescale 1ns/1ps','module tb;','reg clk=0;always #5 clk=~clk;reg rst=0;integer cycle=0;',decls,functions]
    body+= [c.monitor('clk','rst',i,z) for i,z in enumerate(cs)]
    body+= ['always @(posedge clk) cycle<=cycle+1;','initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for i,r in enumerate(rows):
        if i:body+=['@(negedge clk);']
        body+= [f"{n}={v};" for n,v in r.items()]
        if between_reset and i==3:body+=['#1 rst=0; #1 rst=1;']
    body+=['@(negedge clk);$finish;end','endmodule']
    (p/'checker_tb.sv').write_text('\n'.join(body));e.dump(p/'input.json',rows);e.dump(p/'candidates.json',cs)
    build=e.command(['iverilog','-g2012','-s','tb','-o','sim.out','checker_tb.sv'],p,'compile')
    assert build['status']=='ok',(name,build)
    sim=e.command(['vvp','sim.out'],p,'simulate');assert sim['status']=='ok'
    (p/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd '+shlex.quote(str(p))+'\niverilog -g2012 -s tb -o sim.out checker_tb.sv\nvvp sim.out\n')
    actual={i:[] for i in range(len(cs))}
    for line in (p/'simulate.stdout').read_text().splitlines():
        if line.startswith('CHECK '):
            _,j,t,a,f=line.split();actual[int(j)].append({'cycle':int(t),'trigger':int(a) if a.isdigit() else None,'fail':int(f) if f.isdigit() else None})
    return p,actual

def qualify():
    OUT.mkdir(parents=True,exist_ok=True);results=[]
    # Widths cross the host 32-bit boundary; all values enumerated for <=8 bits.
    for w in [1,2,4,8,17,32,65,256]:
        vals=list(range(1<<w)) if w<=8 else [0,1,2,3,1<<(w-1),(1<<w)-1,((1<<w)-1)//3]
        rows=[{'rst':0,'x':0,'expected':0}]+[{'rst':1,'x':f"{w}'h{v:x}",'expected':sum((v>>b)&1 for b in range(w))} for v in vals]
        cs=[{'antecedent':'1','consequent':f'af_count_{w}(x)==expected','delay':0}, {'antecedent':'1','consequent':f'af_count_{w}(x)!=expected','delay':0}]
        p,actual=simulate(f'popcount_w{w}',f'reg [{w-1}:0] x;reg [31:0] expected;',rows,cs,c.count_function(w))
        expected={0:[{'cycle':i,'trigger':1,'fail':0} for i in range(1,len(rows))],1:[{'cycle':i,'trigger':1,'fail':1} for i in range(1,len(rows))]}
        e.dump(p/'expected.json',expected);e.dump(p/'actual.json',actual);assert actual==expected
        results.append({'test':p.name,'pass':True,'samples':len(vals),'checks':2*len(vals),'basis':'Python per-bit sum; correct and intentionally false comparison'})
    # Explicit temporal table includes overlap, first active sample, reset cancellation,
    # a result one sample early and one sample late; no candidate/contract-derived expected values.
    seq=[(0,0,0),(0,0,0),(1,0,0),(1,1,0),(1,1,0),(1,0,1),(1,0,1),(1,1,0),(1,0,1),(1,0,0),(1,1,0),(1,0,0),(1,0,0),(1,0,1),(1,1,0),(0,0,0),(1,0,0),(1,0,0)]
    rows=[dict(zip(['rst','a','b'],r)) for r in seq]
    cs=[{'antecedent':'a','consequent':'b','delay':d} for d in [0,1,2]]
    p,actual=simulate('delay_overlap_reset_boundary','reg a;reg b;',rows,cs)
    expected={i:c.reference_checks(rows,z,lambda expr,r:r[expr],'rst') for i,z in enumerate(cs)}
    assert [x['cycle'] for x in expected[2] if x['fail']]==[9,12]
    assert actual==expected
    e.dump(p/'expected.json',expected);e.dump(p/'actual.json',actual)
    results.append({'test':p.name,'pass':True,'checks':sum(map(len,actual.values())),'delay2_expected_failures':[9,12],'delay2_pass_due_cycles':[5,6],'cancelled_trigger_cycle':14,'basis':'independent due-event map and literal failure cycle assertion'})
    # Reset asserted and released between sampling edges must cancel queued work.
    rr=[{'rst':0,'a':0,'b':0},{'rst':1,'a':0,'b':0},{'rst':1,'a':1,'b':0},{'rst':1,'a':0,'b':0},{'rst':1,'a':0,'b':0},{'rst':1,'a':0,'b':0}]
    p,actual=simulate('asynchronous_reset_cancel','reg a;reg b;',rr,[cs[2]],between_reset=True)
    expected={0:[{'cycle':i,'trigger':int(i==2),'fail':0} for i in range(1,6)]}
    assert actual==expected;e.dump(p/'expected.json',expected);e.dump(p/'actual.json',actual)
    results.append({'test':p.name,'pass':True,'checks':5,'basis':'hand-authored no due failure after between-edge reset'})
    rr=[{'rst':0,'x':0},{'rst':1,'x':"4'b0x01"},{'rst':1,'x':"4'b0z01"}]
    p,actual=simulate('unknown_bits_propagate','reg [3:0] x;',rr,[{'antecedent':'1','consequent':'af_count_4(x)>1','delay':0}],c.count_function(4))
    assert [x['fail'] for x in actual[0]]==[None,None];e.dump(p/'actual.json',actual);e.dump(p/'expected.json',{'fail':[None,None]})
    results.append({'test':p.name,'pass':True,'checks':2,'basis':'X/Z must remain unknown, not counted as zeros'})
    e.dump(OUT/'qualification.json',{'passed':all(r['pass'] for r in results),'tests':results,'scope':'sampled unsigned packed popcount, exact delays 0..2; four-state unknown propagation; no SVA engine equivalence claim','checker_sha256':e.sha(Path(c.__file__))})
    print(json.dumps({'qualification_pass':True,'tests':len(results),'checks':sum(r['checks'] for r in results)}))

if __name__=='__main__':qualify()
