"""Bounded new-history development screen; cached Git only, no model calls."""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import research_native_runner as n

ROOT=n.ROOT; D=ROOT/'deliverables'
LOCK=D/'research183_history_screen_20261101_r01/population_lock.json'
REPO=D/'research155_stat_history_20261027_r01/upstream.git'
dump=n.dump
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p): return Path(p).relative_to(ROOT).as_posix()
def git(*args): return subprocess.check_output(['git','--git-dir='+str(REPO),*args])


def isolation():
    reads=set()
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo'): raise RuntimeError('network_not_allowed')
        if event!='open' or not isinstance(args[0],(str,bytes)): return
        name=str(args[0]).replace('\\','/').lower()
        if any(x in name for x in ('/.secrets/','/.env','/independent','/holdout','/tested_versions/','/terminal_frozen/','/frozen/')):
            raise RuntimeError('independent_or_secret_read_denied')
        if '/deliverables/' in name and not (isinstance(args[1],str) and any(x in args[1] for x in 'wax+')):
            reads.add(str(args[0]))
    sys.addaudithook(guard)
    return reads


def usage(candidates):
    # Reuse the recorded development metadata inventory. Add only later public
    # request/preparation metadata, never independent outputs or aggregate runs.
    listing=D/'research177_history_screen_20261029_r01/metadata_paths.txt'
    paths={ROOT/s.replace('\\','/') for s in listing.read_text(encoding='utf-8-sig').splitlines()}
    for p in D.iterdir():
        if not p.is_dir() or not re.match(r'research(17[7-9]|18[0-2])_',p.name): continue
        if 'prepare' in p.name:
            paths.update(p.glob('request.preview.json'))
            paths.update(p.glob('*/request.preview.json'))
        # Explicit development-only model record locations; not recursive runs.
    paths.update(D/x for x in [
        'research179_frame_controller_run_20261029_r01/shared/model_call/request.json',
        'research181_presentation_run_20261030_r01/arms/C/r0/model_call/request.json',
        'research181_presentation_run_20261030_r01/arms/T/r0/model_call/request.json'])
    files=[];hits=[]
    for p in sorted(paths):
        parts=p.relative_to(D).parts
        if not parts[0].startswith('research') or any(x in str(p).lower() for x in ('independent','holdout','tested_versions','terminal_frozen','/frozen/')): continue
        if p.name not in {'request.json','request.preview.json','plan_request.preview.json','protocol.json','population_lock.json','candidate_matrix.json'} or not p.exists(): continue
        if p.stat().st_size>8000000: continue
        text=p.read_text(encoding='utf-8-sig',errors='replace'); files.append(dict(path=rel(p),sha256=sha(p)))
        for c in candidates:
            mods=[m for m in c['modules'] if re.search(r'\b'+m+r'\b',text)]
            commit=c['fix'][:7] in text
            if mods or commit: hits.append(dict(candidate=c['id'],path=rel(p),modules=mods,exact_fix_mention=commit,
                                               request='request' in p.name, module_definition=any(re.search(r'\bmodule\s+'+m+r'\b',text) for m in mods)))
    return dict(files=files,hits=hits,scope='Recorded development requests and protocols only; exact fix versus generic module reuse separated. No guarantee about external/deleted records.',independent_read=False)


def fifo_rows(depth):
    rows=[]
    def add(rst=0,v=0,data=0,last=0,ready=0,frame=-1): rows.append(dict(cycle=len(rows),rst=rst,v=v,data=data,last=last,ready=ready,frame=frame))
    for _ in range(3): add(rst=1)
    for i in range(depth-1): add(v=1,data=1+i,last=i==depth-2,frame=0)
    for _ in range(12): add()
    # Oversize frame while earlier complete frame occupies storage. After the
    # first overflow, idle cycles plus downstream draining test drop persistence.
    for i in range(depth+4):
        if i==depth//2+1:
            for _ in range(20): add(ready=1)
        add(v=1,data=80+i,last=i==depth+3,ready=int(i>depth//2),frame=1)
    for _ in range(40): add(ready=1)
    for i in range(3): add(v=1,data=200+i,last=i==2,ready=1,frame=2)
    for _ in range(80): add(ready=1)
    return rows


def common_sv(inputs,outputs,dest_width):
    return f'''module tb;
bit clk=0;always #5 clk=~clk;bit rst=1;integer cycle=-1;
bit [{inputs*8-1}:0] s_axis_tdata=0;bit [{inputs-1}:0] s_axis_tvalid=0,s_axis_tlast=0,s_axis_tkeep='1;
wire [{inputs-1}:0] s_axis_tready;bit [{inputs*8-1}:0] s_axis_tid=0;
bit [{inputs*dest_width-1}:0] s_axis_tdest=0;bit [{inputs-1}:0] s_axis_tuser=0;
wire [{outputs*8-1}:0] m_axis_tdata,m_axis_tid;wire [{outputs-1}:0] m_axis_tvalid,m_axis_tlast,m_axis_tkeep,m_axis_tuser;
wire [{outputs*dest_width-1}:0] m_axis_tdest;bit [{outputs-1}:0] m_axis_tready=0;
wire [{inputs-1}:0] status_overflow,status_bad_frame,status_good_frame;
'''


def hold_sva(outputs):
    return '\n'.join(f'''hold_{p}: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid[{p}] && !m_axis_tready[{p}]) |=> (m_axis_tvalid[{p}] && $stable({{m_axis_tdata[{8*p}+:8],m_axis_tlast[{p}]}}))) else $display("ASSERT_FAIL hold_{p} cycle=%0d",$sampled(cycle));
always @(posedge clk) if(!rst && m_axis_tvalid[{p}] && !m_axis_tready[{p}]) $display("TRIGGER hold_{p} cycle=%0d",cycle);''' for p in range(outputs))


def trace_sv():
    return '$display("TRACE cycle=%0d rst=%0d sv=%0d sr=%0d sd=%0d sl=%0d dest=%0d mv=%0d mr=%0d md=%0d ml=%0d ov=%0d good=%0d",cycle,rst,s_axis_tvalid,s_axis_tready,s_axis_tdata,s_axis_tlast,s_axis_tdest,m_axis_tvalid,m_axis_tready,m_axis_tdata,m_axis_tlast,status_overflow,status_good_frame);'


def fifo_tb(depth):
    lines=[common_sv(1,1,8),f'axis_fifo #(.DEPTH({depth}),.DATA_WIDTH(8),.KEEP_ENABLE(0),.FRAME_FIFO(1),.DROP_WHEN_FULL(1)) dut(.*);',hold_sva(1),
           'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for r in fifo_rows(depth):
        lines += [f"@(negedge clk);cycle={r['cycle']};rst={r['rst']};s_axis_tvalid={r['v']};s_axis_tdata={r['data']};s_axis_tlast={r['last']};m_axis_tready={r['ready']};",
                  '@(posedge clk);'+trace_sv()]
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def switch_tb(ram,config):
    inputs,outputs=2,(2 if ram else 1)
    text=common_sv(inputs,outputs,1)
    if ram:
        text+='axis_ram_switch #(.FIFO_DEPTH(256),.CMD_FIFO_DEPTH(16),.SPEEDUP(1),.S_COUNT(2),.M_COUNT(2),.S_DATA_WIDTH(8),.M_DATA_WIDTH(8),.S_KEEP_ENABLE(0),.M_KEEP_ENABLE(0),.DEST_WIDTH(1)) dut(.*);\n'
    else:
        text+='axis_switch #(.S_COUNT(2),.M_COUNT(1),.DATA_WIDTH(8),.KEEP_ENABLE(0),.DEST_WIDTH(1)) dut(.*);\nassign status_overflow=0;assign status_good_frame=0;\n'
    text+=hold_sva(outputs)
    # Source advances only on handshake; both revisions see the same source
    # transaction program and absolute sink readiness, not assumed equal cycles.
    text+=f'''
integer sent0=0,sent1=0;integer ix;bit h0,h1;
initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);
for(integer t=0;t<2000;t=t+1) begin
@(negedge clk);cycle=t;rst=(t<4);
s_axis_tvalid=0;s_axis_tlast=0;s_axis_tdata=0;s_axis_tdest=0;
if(!rst) begin
 if(sent0<96) begin s_axis_tvalid[0]=1;s_axis_tdata[0+:8]=sent0;s_axis_tlast[0]=1;s_axis_tdest[0]={'(sent0%2)' if ram and config else '0'};end
 if(sent1<96) begin s_axis_tvalid[1]=1;s_axis_tdata[8+:8]=128+sent1;s_axis_tlast[1]=1;s_axis_tdest[1]={'(sent1%2)' if ram and config else '0'};end
end
m_axis_tready=0;
if(t>=240) m_axis_tready={'2' if ram else '1'}'b{'11' if ram else '1'};
if(t>=240 && t<650 && t%11<5) m_axis_tready[0]=0;
@(posedge clk);{trace_sv()}
h0=s_axis_tvalid[0]&&s_axis_tready[0];h1=s_axis_tvalid[1]&&s_axis_tready[1];
if(h0) sent0=sent0+1;if(h1) sent1=sent1+1;
end
@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule
'''
    return text


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);lock=read(LOCK);dump(out/'population_lock.json',lock)
    use=usage(lock['candidates']);dump(out/'prior_usage.json',use)
    manifest=[];cases=[]
    for case in lock['candidates']:
        parent=git('rev-parse',case['fix']+'^').decode().strip();folder=out/case['id'];folder.mkdir()
        (folder/'fix.patch').write_bytes(git('show','--format=fuller',case['fix'],'--','rtl'))
        for rev,commit in [('before',parent),('after',case['fix'])]:
            names=git('ls-tree','-r','--name-only',commit,'rtl').decode().splitlines()
            # Capture same-revision dependencies byte-exact, no patched RTL.
            for name in names:
                if not(name.endswith('.v') or name=='rtl/axis_switch_wrap.py'):continue
                p=folder/rev/Path(name).name;p.parent.mkdir(exist_ok=True)
                raw=git('show',commit+':'+name);p.write_bytes(raw)
                blob=git('rev-parse',commit+':'+name).decode().strip()
                assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==blob
                manifest.append(dict(case=case['id'],revision=rev,commit=commit,path=rel(p),sha256=sha(p),git_blob=blob))
            (folder/rev/'README.upstream.txt').write_bytes(git('show',commit+':README.md'))
        configs=[] if case['id']=='switch_wrapper' else [8,16] if case['id']=='frame_fifo_drop' else [0,1] if case['id']=='ram_switch_backpressure' else [0]
        for cfg in configs:
            tb=fifo_tb(cfg) if case['id']=='frame_fifo_drop' else switch_tb(case['id']=='ram_switch_backpressure',cfg)
            (folder/f'tb_{cfg}.sv').write_text(tb)
            if case['id']=='frame_fifo_drop':dump(folder/f'stimuli_{cfg}.json',fifo_rows(cfg))
        cases.append(dict(**case,parent=parent,configs=configs,
                          exact_fix_previously_mentioned=any(x['candidate']==case['id'] and x['exact_fix_mention'] for x in use['hits']),
                          prior_module_request_count=sum(x['candidate']==case['id'] and x['request'] and bool(x['modules']) for x in use['hits']),
                          selection_status='exclude_generator_only_no_direct_RTL_pair' if not configs else 'bounded_original_native_pair'))
    dump(out/'cases.json',cases);dump(out/'source_manifest.json',manifest)
    dump(out/'protocol.json',dict(model_calls=0,network_calls=0,formal_calls=0,compile_attempts=10,hard_cap=16,retries=0,
        selection='All four preselected commits retained; no replacements. Each configured revision attempted once, build failures retained as tool limitations.',
        switch='All connections enabled. M_COUNT1 must route every accepted packet regardless of destination. Compiler failure is not a functional witness.',
        ram='No intentional drop. Unique single-beat payloads 0..95 / 128..223 identify accepted requests from two sources; preserve per-source/destination order and exactly-once response; sink stalls then drains. Arbitration interleaving across sources is unrestricted.',
        fifo='FRAME_FIFO=1 DROP_WHEN_FULL=1. Accepted oversize frame (>DEPTH) must be entirely dropped, including across idle and downstream release. Earlier length DEPTH-1 frame and later three-beat frame must pass in this drained scope. Not every accepted frame is required to return under drop mode.',
        legality='Source payload/destination/last held until accepted; per-revision handshake acceptance recorded. Switch inputs share transaction program and sink schedule, not promised bit-identical arrival cycles if ready differs. FIFO port vectors are identical.',
        timeout='2000 switch cycles and FIFO final80 ready cycles are bounded observations, not protocol-mandated formal liveness. Pending-only result stays bounded-not-drained, not a proof.',
        scope='Synchronous FIFO implementation only; asynchronous sibling archived but not executed. All evidence development, not search-new-discovery or independent validation.',
        qualification='Original witness alone does not establish partial protection. Diagnostic hold assertions handwritten; require actual old detection AND other missed target transactions, not multiple symptoms of same fault. No model pilot if not established.'))
    dump(out/'code_bindings.json',{rel(p):sha(p) for p in (LOCK,Path(__file__),Path(n.__file__))})
    dump(out/'seal.json',{relpath.as_posix():sha(out/relpath) for relpath in [p.relative_to(out) for p in out.rglob('*') if p.is_file()]})
    print('PREPARED183 cases4 configurations5 original_pairs5 calls0',flush=True)


def verify(prep):
    for p,h in read(prep/'seal.json').items():assert sha(prep/p)==h,p
    for p,h in read(prep/'code_bindings.json').items():assert sha(ROOT/p)==h,p


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);executions=[]
    for c in read(prep/'cases.json'):
        for cfg in c['configs']:
            for rev in ('before','after'):
                src=prep/c['id']/rev
                result=n.run_native((prep/c['id']/f'tb_{cfg}.sv').read_text(),out/c['id']/str(cfg)/rev,
                                    extra_sources=sorted(src.glob('*.v')),timeout=240)
                executions.append(dict(case=c['id'],config=cfg,revision=rev,result=result))
                dump(out/'executions.json',executions)
                print('NATIVE183',c['id'],cfg,rev,result['compile_status'],result['execution_status'],flush=True)
    dump(out/'cost.json',dict(model_calls=0,formal_calls=0,native_compile_attempts=len(executions),
          native_executions=sum(x['result']['native_simulation_calls'] for x in executions),
          compile_seconds=sum(x['result']['compile']['wall_seconds'] for x in executions),
          execution_seconds=sum(x['result'].get('execute',{}).get('wall_seconds',0) for x in executions)))


def traces(folder):
    return [{k:int(v) for k,v in (s.split('=') for s in line.split()[1:])} for line in (folder/'execute.log').read_text().splitlines() if line.startswith('TRACE ')]


def oracle(tr,case,cfg):
    inputs=1 if case=='frame_fifo_drop' else 2;outputs=2 if case=='ram_switch_backpressure' else 1
    accepted=[];returned=[];violations=[];legal=True;previous=None
    for v in tr:
        if previous and not v['rst'] and not previous['rst']:
            for p in range(inputs):
                if (previous['sv']>>p)&1 and not (previous['sr']>>p)&1:
                    if not(v['sv']>>p)&1 or any(((v[k]>>(p*w))&((1<<w)-1))!=((previous[k]>>(p*w))&((1<<w)-1)) for k,w in [('sd',8),('sl',1),('dest',8 if inputs==1 else 1)]):legal=False
            for p in range(outputs):
                if (previous['mv']>>p)&1 and not(previous['mr']>>p)&1:
                    if not(v['mv']>>p)&1 or (v['md']>>(p*8))&255 != (previous['md']>>(p*8))&255 or (v['ml']>>p)&1 != (previous['ml']>>p)&1:
                        violations.append(dict(cycle=v['cycle'],obligation='output_hold',port=p))
        if not v['rst']:
            for p in range(inputs):
                if (v['sv']&v['sr']>>0)&(1<<p):
                    accepted.append(dict(cycle=v['cycle'],source=p,data=(v['sd']>>(8*p))&255,last=(v['sl']>>p)&1,dest=(v['dest']>>(p*(8 if inputs==1 else 1)))&((1<<(8 if inputs==1 else 1))-1)))
            for p in range(outputs):
                if (v['mv']&v['mr'])&(1<<p):returned.append(dict(cycle=v['cycle'],port=p,data=(v['md']>>(8*p))&255,last=(v['ml']>>p)&1))
        previous=v
    associations=[];expected=[];discarded=[]
    if case=='frame_fifo_drop':
        frame=[]
        for a in accepted:
            frame.append(a)
            if a['last']:
                if len(frame)>cfg:discarded.append(frame)
                else:expected.extend(frame)
                frame=[]
        for i,b in enumerate(returned):
            a=expected[i] if i<len(expected) else None
            associations.append(dict(request=a,response=b))
            if 80<=b['data']<80+cfg+4:violations.append(dict(cycle=b['cycle'],obligation='oversize_frame_atomic_drop',response=b))
            elif a is None or (a['data'],a['last'])!=(b['data'],b['last']):violations.append(dict(cycle=b['cycle'],obligation='retained_frame_order',request=a,response=b,attribution='after_first_mismatch_may_be_secondary'))
        pending=max(0,len(expected)-len(returned))
    else:
        queue=defaultdict(deque)
        for a in accepted:queue[(a['source'],a['dest'] if outputs==2 else 0)].append(a)
        for b in returned:
            src=int(b['data']>=128);key=(src,b['port']);a=queue[key].popleft() if queue[key] else None
            associations.append(dict(request=a,response=b))
            if a is None or a['cycle']>b['cycle'] or (a['data'],a['last'])!=(b['data'],b['last']):violations.append(dict(cycle=b['cycle'],obligation='exactly_once_routed_order',request=a,response=b))
        pending=sum(map(len,queue.values()));expected=accepted
    return dict(legal=legal,accepted=accepted,returned=returned,associations=associations,violations=violations,
                pending_in_bounded_drain=pending,discarded_oversize_frames=discarded,
                expected_return_count=len(expected),complete_scope_pass=legal and not violations and pending==0,
                status='violation' if legal and violations else 'unknown_pending' if pending else 'pass' if legal else 'illegal_source')


def report(prep,run,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[];pairs=[];matrix=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for case in read(prep/'cases.json'):
        witnessed=[];partial=False
        for cfg in case['configs']:
            views={};props={}
            for rev in ('before','after'):
                folder=run/case['id']/str(cfg)/rev;r=read(folder/'result.json')
                check('tb binding '+str(folder),sha(folder/'tb.sv')==sha(prep/case['id']/f'tb_{cfg}.sv'))
                if r['execution_status']!='completed':
                    views[rev]=dict(status='unknown_native',compile=r['compile_status'],support=r['tool_support_status']);continue
                tr=traces(folder);views[rev]=oracle(tr,case['id'],cfg);props[rev]=dict(failures=r['failures'],triggers=len(r['triggers']))
                check('legal source '+str(folder),views[rev]['legal'])
                dump(out/f"{case['id']}_{cfg}_{rev}_transactions.json",views[rev])
            before,after=views['before'],views['after']
            witness=before['status']=='violation' and after.get('complete_scope_pass',False)
            if witness:witnessed.append(cfg)
            # Local diagnostic property qualification only; no synthetic fault.
            det=len(props.get('before',{}).get('failures',[]))
            old_detected=det>0 and witness
            missed=witness and not det
            pairs.append(dict(case=case['id'],config=cfg,before=before['status'],after=after['status'],original_functional_witness=witness,
                              diagnostic_failures=det,diagnostic_triggers=props.get('before',{}).get('triggers',0),
                              old_detected=old_detected,current_missed=missed,partial_qualification=False,
                              distinction='Output hold is editable; no separate old-protected/current-missed transaction class has been established.'))
        reason=('wrapper generator only; not an original RTL functional-pair test; excluded from this bounded screen' if not case['configs'] else
                'original functional witness established; partial-protection/non-whitelist discrimination not established' if witnessed else
                'no reliable functional before-violation/after-pass witness within fixed native scope; retain unknown')
        matrix.append(dict(id=case['id'],fix=case['fix'],parent=case['parent'],configs=case['configs'],witness_configs=witnessed,
                           prior_exact_fix_mention=case['exact_fix_previously_mentioned'],prior_module_request_count=case['prior_module_request_count'],
                           qualification=False,reason=reason,new_model_pilot_sealed=False))
    dump(out/'candidate_matrix.json',matrix);dump(out/'pair_results.json',pairs);dump(out/'checks.json',checks)
    dump(out/'cost.json',read(run/'cost.json'))
    dump(out/'decision.json',dict(action='STOP_NO_QUALIFIED_MODEL_PILOT',original_pair_cases=sum(bool(x['witness_configs']) for x in matrix),
         qualified_partial_candidates=0,model_calls=0,conditional_recovery=dict(numerator=0,denominator=0,estimate=None),
         H_R='equivalent; additional historical checking only',search576='completed negative unchanged',
         limitation='Screening scope is four fixed commits, ten native attempts; not a claim that no useful historical case exists. New witnesses are known development evidence, not search-added discoveries.'))
    lines=['# research183 新历史案例本地筛选','', '**结论：本轮不封存模型先导；原始前后见证与部分保护资格分开报告。**','',
           '|固定案例|前后见证配置|资格／排除理由|','|---|---|---|']
    for x in matrix:lines.append(f"|{x['id']}|{x['witness_configs']}|{x['reason']}|")
    lines += ['', '清单在查看补丁和运行前按本地缓存Git提交顺序固定，4项全部保留，没有替换失败案例。原始源码及同版本依赖按Git blob校验，未修补RTL。原生日志、命令、工具版本、波形在运行目录。手写保持SVA仅作诊断，不计模型生成。',
              '', '公共／历史区分尚未成立：必须在合法事务中同时具备旧目标检出与另一个当前漏报，不能把同一次丢失的多个后果拆成机制机会。编译失败、未曝光、未排空及未找到违例均不按成功处理；累计数量不是独立Bug数。',
              '', 'switch采用相同源事务程序与下游ready计划，源端只在握手后推进；前后版本可能接受周期不同，不能称每周期激励完全相同。FIFO使用相同端口向量。固定排空时限仅为本次仿真范围。异步FIFO兄弟修复仅保存来源，未做异步验证。',
              '', '使用历史审计区分模块出现与具体修复提交出现；模块曾使用不等于本提交已用于调参，未匹配也不能证明云端/删除材料中从未使用。所有本轮采样属于开发数据，不能在后续算未知新发现。独立测试未用于筛选；research181成功性质未用于构造候选。',
              '', '条件恢复仍0/0、不可估计；H/R等价；576次搜索负结果保持不变。本轮不扩种子、不调用模型、不重跑已有FIFO验收。',
              '', '复核：', '```powershell',
              f'wsl -- python3 scripts/research183_history_screen.py report --prepared {rel(prep)} --run {rel(run)} --out deliverables/research183_recheck', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'source_bindings.json',{rel(p):sha(p) for p in [Path(__file__),prep/'seal.json',run/'executions.json',run/'cost.json']})
    dump(out/'seal.json',{p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print('REPORT183',json.dumps(matrix),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run','report']);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepared',type=Path);ap.add_argument('--run',type=Path)
    args=ap.parse_args();isolation()
    if args.mode=='prepare':prepare(args.out.resolve())
    elif args.mode=='run':run(args.prepared.resolve(),args.out.resolve())
    else:report(args.prepared.resolve(),args.run.resolve(),args.out.resolve())
