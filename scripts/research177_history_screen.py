"""Fixed four-case, local original-history screening. No model or network.

Only development qualification: no partial-candidate construction, pilot or
independent test. Original source bytes are extracted from the cached Git repo.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import research_native_runner as n

ROOT=n.ROOT;D=ROOT/'deliverables';LOCK=D/'research177_history_screen_20261029_r01/population_lock.json'
REPO=D/'research155_stat_history_20261027_r01/upstream.git'
dump=n.dump
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(ROOT).as_posix()
def git(*args):return subprocess.check_output(['git','--git-dir='+str(REPO),*args])


def usage_scan(candidates):
    """Recorded model inputs plus development protocols, not holdout outcomes."""
    files=[];hits=[];skipped=[]
    modules=sorted({c['module'] for c in candidates})
    names={'request.json','request.preview.json','plan_request.preview.json','protocol.json','population_lock.json','candidate_matrix.json'}
    listing=LOCK.parent/'metadata_paths.txt'
    for entry in listing.read_text(encoding='utf-8-sig').splitlines():
        p=ROOT/entry.replace('\\','/');parts=p.relative_to(D).parts;top=parts[0];name=p.name
        if not top.startswith('research') or top.startswith(('research177_','research174_','research175_')):continue
        if any('independent' in x or 'holdout' in x or x in ('tested_versions','terminal_frozen','frozen') for x in parts):continue
        if name not in names:continue
        if p.stat().st_size>8_000_000:skipped.append(dict(path=rel(p),reason='over8MB'));continue
        text=p.read_text(encoding='utf-8-sig',errors='replace');files.append(dict(path=rel(p),sha256=sha(p)))
        for c in candidates:
            if re.search(r'\b'+c['module']+r'\b',text) or c['fix'][:7] in text:
                hits.append(dict(path=rel(p),candidate=c['id'],module=c['module'],
                    module_definition_present=bool(re.search(r'\bmodule\s+'+c['module']+r'\b',text)),
                    commit_mentioned=c['fix'][:7] in text,request='request' in name))
    scripts=[]
    for p in (ROOT/'scripts').glob('research*.py'):
        if p==Path(__file__):continue
        text=p.read_text(encoding='utf-8-sig',errors='replace')
        found=[c['id'] for c in candidates if re.search(r'\b'+c['module']+r'\b',text) or c['fix'][:7] in text]
        if found:scripts.append(dict(path=rel(p),sha256=sha(p),candidates=found))
    return dict(files=files,hits=hits,script_hits=scripts,skipped=skipped,metadata_path_listing=rel(listing),metadata_path_listing_sha256=sha(listing),
        scope='Local recorded request/plan/protocol/candidate metadata and research scripts only; native/build/object/source/independent directories excluded from metadata traversal. Exact identifier matching, not frame_length_adjust substring. No proof about external/deleted/cloud records. README catalog mentions alone do not establish tuning.',
        independent_outcomes_read=False)


def pipe_tb(length):
    return '''module tb;
bit clk=0;always #5 clk=~clk;bit rst=1;integer cycle=-1;
bit [7:0] s_axis_tdata=8'h35;bit s_axis_tkeep=1,s_axis_tvalid=0,s_axis_tlast=0;wire s_axis_tready;
bit [7:0] s_axis_tid=0,s_axis_tdest=0;bit s_axis_tuser=0;
wire [7:0] m_axis_tdata,m_axis_tid,m_axis_tdest;wire m_axis_tkeep,m_axis_tvalid,m_axis_tlast,m_axis_tuser;
bit m_axis_tready=0;
axis_pipeline_fifo #(.DATA_WIDTH(8),.KEEP_ENABLE(0),.LENGTH('''+str(length)+''')) dut(.*);
hold_valid: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid && !m_axis_tready) |=> m_axis_tvalid) else $display("ASSERT_FAIL hold_valid cycle=%0d",$sampled(cycle));
hold_data: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid && !m_axis_tready) |=> $stable({m_axis_tdata,m_axis_tlast})) else $display("ASSERT_FAIL hold_data cycle=%0d",$sampled(cycle));
always @(posedge clk) if (!rst && m_axis_tvalid&&!m_axis_tready) $display("TRIGGER hold cycle=%0d",cycle);
initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);
for(integer t=0;t<256;t=t+1) begin
@(negedge clk);cycle=t;rst=(t<3);s_axis_tvalid=(t>=4&&t<100);s_axis_tlast=(t==99);m_axis_tready=(t>=40);
@(posedge clk);$display("TRACE cycle=%0d rst=%0d sv=%0d sr=%0d sd=%0d sl=%0d mv=%0d mr=%0d md=%0d ml=%0d",cycle,rst,s_axis_tvalid,s_axis_tready,s_axis_tdata,s_axis_tlast,m_axis_tvalid,m_axis_tready,m_axis_tdata,m_axis_tlast);
end
@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule
'''


def frame_stim():
    rows=[]
    def add(rst=0,v=0,r=1,k=15,last=0):rows.append(dict(cycle=len(rows),rst=rst,v=v,r=r,k=k,last=last))
    for _ in range(3):add(rst=1)
    def beat(k,last,gap=0,stall=0):
        for _ in range(gap):add()
        for _ in range(stall):add(v=1,r=0,k=k,last=last)
        add(v=1,k=k,last=last)
    beat(15,1);beat(3,1);beat(1,1)
    beat(15,0,2);beat(15,0,stall=2);beat(7,1);beat(3,1,2,1)
    beat(15,0);add(rst=1);add(rst=1)
    beat(1,1);beat(15,1);beat(15,0);beat(3,1)
    for _ in range(5):add()
    return rows


def frame_expected(rows,keep):
    accumulator=0;pv=0;pl=0;expected=[]
    for row in rows:
        expected.append(dict(valid=pv,length=pl,applicable=not row['rst']))
        if row['rst']:accumulator=0;pv=0;pl=0;continue
        pv=0
        if row['v'] and row['r']:
            accumulator+=row['k'].bit_count() if keep else 1
            if row['last']:pv=1;pl=accumulator;accumulator=0
    return expected


def frame_tb(keep,rows):
    width=32 if keep else 8;kw=4 if keep else 1;expected=frame_expected(rows,keep)
    lines=['module tb;bit clk=0;always #5 clk=~clk;bit rst=1;integer cycle=-1;',
        f'bit [{kw-1}:0] monitor_axis_tkeep;bit monitor_axis_tvalid=0,monitor_axis_tready=0,monitor_axis_tlast=0;wire [15:0] frame_len;wire frame_len_valid;bit ev=0;integer el=0;',
        f'axis_frame_len #(.DATA_WIDTH({width}),.KEEP_ENABLE({keep}),.KEEP_WIDTH({kw})) dut(.*);',
        'length_check: assert property (@(posedge clk) disable iff(rst) ev |-> (frame_len_valid && frame_len==el)) else $display("ASSERT_FAIL length_check cycle=%0d",$sampled(cycle));',
        'valid_check: assert property (@(posedge clk) disable iff(rst) 1 |-> frame_len_valid==ev) else $display("ASSERT_FAIL valid_check cycle=%0d",$sampled(cycle));',
        'always @(posedge clk) if(!rst&&ev) $display("TRIGGER length_check cycle=%0d",cycle);',
        'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for row,e in zip(rows,expected):
        k=row['k'] if keep else 1
        lines += [f"@(negedge clk);cycle={row['cycle']};rst={row['rst']};monitor_axis_tvalid={row['v']};monitor_axis_tready={row['r']};monitor_axis_tkeep={k};monitor_axis_tlast={row['last']};ev={e['valid']};el={e['length']};",
            '@(posedge clk);$display("TRACE cycle=%0d rst=%0d v=%0d r=%0d k=%0d last=%0d length=%0d valid=%0d",cycle,rst,monitor_axis_tvalid,monitor_axis_tready,monitor_axis_tkeep,monitor_axis_tlast,frame_len,frame_len_valid);']
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);lock=read(LOCK);dump(out/'population_lock.json',lock)
    usage=usage_scan(lock['candidates']);dump(out/'prior_usage_audit.json',usage)
    print('USAGE177',len(usage['files']),'metadata files;',len(usage['hits']),'matches',flush=True)
    manifest=[];cases=[]
    for c in lock['candidates']:
        fix=c['fix'];parent=git('rev-parse',fix+'^').decode().strip();case=out/c['id'];case.mkdir()
        patch=git('show','--format=fuller',fix,'--','rtl/'+c['module']+'.v');(case/'fix.patch').write_bytes(patch)
        versions={}
        for rev,commit in [('before',parent),('after',fix)]:
            p=case/rev/(c['module']+'.v');p.parent.mkdir();data=git('show',commit+':rtl/'+c['module']+'.v');p.write_bytes(data);versions[rev]=data
            blob=git('rev-parse',commit+':rtl/'+c['module']+'.v').decode().strip()
            computed=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest();assert computed==blob
            manifest.append(dict(case=c['id'],revision=rev,commit=commit,path=rel(p),sha256=sha(p),git_blob=blob,git_blob_verified=True))
            (case/rev/'README.md').write_bytes(git('show',commit+':README.md'))
        semantic_equal=re.sub(rb'\s+',b'',versions['before'])==re.sub(rb'\s+',b'',versions['after'])
        cfgs=[] if semantic_equal else [2,3,4] if c['id']=='pipeline_offbyone' else [2] if c['id']=='pipeline_assignment' else [0,1]
        status='exclude_whitespace_only_no_functional_change' if semantic_equal else 'execute_bounded_original_pair'
        for cfg in cfgs:
            tb=pipe_tb(cfg) if c['module']=='axis_pipeline_fifo' else frame_tb(cfg,frame_stim())
            (case/f'tb_{cfg}.sv').write_text(tb,encoding='utf-8')
        cases.append(dict(**c,before=parent,configs=cfgs,status=status,whitespace_stripped_identical=semantic_equal,
            prior_request_hits=[h for h in usage['hits'] if h['candidate']==c['id'] and h['request']],
            prior_script_hits=[h for h in usage['script_hits'] if c['id'] in h['candidates']]))
    dump(out/'cases.json',cases);dump(out/'source_manifest.json',manifest)
    dump(out/'frame_stimuli.json',frame_stim())
    dump(out/'contracts.json',dict(
        pipeline='Original AXI pipeline FIFO preserves each actually accepted byte and TLAST in order; output stable under stall. Same fixed legal port stimuli both revisions, but acceptance counts may differ with capacity. No equality of ready or cycles required. Once source ends at cycle100, sink ready stays high; 156 cycles drain exceeds both configured maximum buffers/pipeline; report leftover accepted requests, not mere waveform differences.',
        frame_len='Count only monitor valid&&ready beats. With KEEP_ENABLE1 and contiguous low keep masks, byte count is popcount; with KEEP_ENABLE0,width8 one byte per accepted beat. One cycle after accepted TLAST report that frame length and valid; next frame starts zero; reset discards partial frame. Count sums stay below16-bit wrap.',
        limitations='No protocol latency for axis_switch inferred from whitespace patch. Assignment fix may be simulator/tool scheduling only; no before/fixed functional witness means unknown.',
        counts='Model0/network0. Diagnostic SVA is handwritten, never model-generated. All tests development. No mechanism increment or pilot qualification established.',
        budget='12 compile attempts for fixed6 pairs; global ceiling16, no automatic retries, no replacement cases.'))
    dump(out/'code_bindings.json',{rel(p):sha(p) for p in (Path(__file__),Path(n.__file__),LOCK,LOCK.parent/'metadata_paths.txt')})
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print('PREPARED177',sum(len(c['configs']) for c in cases),'pairs',flush=True)


def verify(prep):
    for k,h in read(prep/'seal.json').items():assert sha(prep/k)==h,k
    for k,h in read(prep/'code_bindings.json').items():assert sha(ROOT/k)==h,k


def trace(folder):
    p=folder/'execute.log'
    return [{k:int(v) for k,v in (w.split('=') for w in line.split()[1:])} for line in p.read_text().splitlines() if line.startswith('TRACE ')] if p.exists() else []


def oracle_pipe(tr):
    queue=[];events=[];fails=[];previous=None;legal=True
    for v in tr:
        if v['rst']:queue=[];previous=None;continue
        if previous and previous['sv'] and not previous['sr'] and (not v['sv'] or v['sd']!=previous['sd'] or v['sl']!=previous['sl']):legal=False
        if v['sv'] and v['sr']:
            queue.append(dict(accept_cycle=v['cycle'],data=v['sd'],last=v['sl']));events.append(dict(kind='input',cycle=v['cycle']))
        if v['mv'] and v['mr']:
            req=queue.pop(0) if queue else None
            events.append(dict(kind='output',cycle=v['cycle'],request=req))
            if req is None or (req['data'],req['last'])!=(v['md'],v['ml']):fails.append(dict(cycle=v['cycle'],obligation='accepted_order_and_frame',request=req,observed=[v['md'],v['ml']]))
        if previous and previous['mv'] and not previous['mr'] and (not v['mv'] or (v['md'],v['ml'])!=(previous['md'],previous['ml'])):fails.append(dict(cycle=v['cycle'],obligation='output_stability'))
        previous=v
    if queue:fails.append(dict(cycle=tr[-1]['cycle'],obligation='bounded_drain_no_loss',pending=queue))
    return dict(legal=legal,failures=fails,events=events,accepted=sum(x['kind']=='input' for x in events),returned=sum(x['kind']=='output' for x in events),pending=len(queue))


def oracle_frame(tr,keep):
    expected=frame_expected(tr,keep);fails=[];events=[];legal=True;previous=None;pending=[]
    for v,e in zip(tr,expected):
        if not v['rst']:
            if v['valid']!=e['valid']:fails.append(dict(cycle=v['cycle'],obligation='completion_valid',expected=e,actual=v))
            if e['valid']:
                events.append(dict(kind='frame_result',cycle=v['cycle'],expected=e['length'],observed=v['length']))
                if v['length']!=e['length']:fails.append(dict(cycle=v['cycle'],obligation='per_frame_length',expected=e['length'],actual=v['length']))
            if previous and not previous['rst'] and previous['v'] and not previous['r'] and (not v['v'] or v['k']!=previous['k'] or v['last']!=previous['last']):legal=False
            if v['v'] and v['r']:
                pending.append(v['cycle']);events.append(dict(kind='accepted',cycle=v['cycle'],last=v['last'],keep=v['k']))
                if v['last']:events.append(dict(kind='frame_complete',cycle=v['cycle'],requests=pending.copy()));pending=[]
        else:
            if pending:events.append(dict(kind='reset_cancel',cycle=v['cycle'],requests=pending.copy()));pending=[]
        previous=v
    return dict(legal=legal,failures=fails,events=events,frame_results=sum(x['kind']=='frame_result' for x in events))


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);cases=read(prep/'cases.json');results=[];calls=[]
    for c in cases:
        for cfg in c['configs']:
            pair={};trs={}
            for rev in ('before','after'):
                folder=out/c['id']/str(cfg)/rev
                result=n.run_native((prep/c['id']/f'tb_{cfg}.sv').read_text(),folder,extra_sources=[prep/c['id']/rev/(c['module']+'.v')]);calls.append(result)
                vals=trace(folder);trs[rev]=vals
                complete=result['compile_status']=='passed' and result['execution_status']=='completed' and len(vals)==(256 if c['module']=='axis_pipeline_fifo' else len(frame_stim()))
                oracle=(oracle_pipe(vals) if c['module']=='axis_pipeline_fifo' else oracle_frame(vals,cfg)) if complete else None
                pair[rev]=dict(complete=complete,oracle=oracle,native_result=rel(folder/'result.json'))
                print('NATIVE177',c['id'],cfg,rev,result['compile_status'],result['execution_status'],flush=True)
            inputs=('rst','sv','sd','sl','mr') if c['module']=='axis_pipeline_fifo' else ('rst','v','r','k','last')
            same=bool(trs['before']) and len(trs['before'])==len(trs['after']) and all(all(a[k]==b[k] for k in inputs) for a,b in zip(trs['before'],trs['after']))
            qualified=all(p['complete'] and p['oracle']['legal'] for p in pair.values()) and same and bool(pair['before']['oracle']['failures']) and not pair['after']['oracle']['failures']
            results.append(dict(case=c['id'],config=cfg,same_inputs=same,original_pair_witness=qualified,revisions=pair))
            dump(out/'paired_results.json',results)
    verify(prep);matrix=[]
    for c in cases:
        pairs=[p for p in results if p['case']==c['id']];w=sum(p['original_pair_witness'] for p in pairs)
        usage_clean=not c['prior_request_hits'] and not c['prior_script_hits']
        status='source_and_functional_witness_qualified' if w and usage_clean else 'prior_use_needs_review' if w else 'excluded_whitespace_only' if c['whitespace_stripped_identical'] else 'unknown_no_functional_pair_witness'
        matrix.append(dict(case=c['id'],module=c['module'],fix=c['fix'],before=c['before'],status=status,witness_pairs=w,total_pairs=len(pairs),
            prior_use='no_recorded_request_or_script_use_in_audited_scope' if usage_clean else 'matches_require_review',
            reason='Original unchanged RTL and legal same inputs expose before failures with fixed pass' if w else 'Whitespace-stripped RTL identical; no functional repair' if c['whitespace_stripped_identical'] else 'Keep native failure/no-violation/unknown records; do not infer functional fix success from patch',
            mechanism_pilot_qualified=False))
    dump(out/'qualification_matrix.json',matrix)
    cost=dict(model_calls=0,network_calls=0,formal_calls=0,native_compiles=len(calls),native_executions=sum(x['native_simulation_calls'] for x in calls),
        compile_seconds=sum(x['compile']['wall_seconds'] for x in calls),execute_seconds=sum(x.get('execute',{}).get('wall_seconds',0) for x in calls))
    dump(out/'cost.json',cost);dump(out/'source_bindings.json',{rel(prep/'seal.json'):sha(prep/'seal.json'),rel(Path(__file__)):sha(Path(__file__))})
    lines=['# research177 新历史案例本地筛选','',
        '候选按预定提交顺序固定4项；不按预计机制收益替换。只做开发资格验证，模型调用0，没有模型先导或独立测试。','',
        '|案例|前后见证对|结论|','|---|---|---|']
    lines += [f"|{x['case']}|{x['witness_pairs']}/{x['total_pairs']}|{x['status']}|" for x in matrix]
    lines += ['', '逐对结果：','', '|案例/配置|合法输入一致|旧版失败点|新版失败点|见证|','|---|---|---|---|---|']
    for p in results:
        counts=[len(p['revisions'][v]['oracle']['failures']) if p['revisions'][v]['oracle'] else 'unknown/tool failure' for v in ('before','after')]
        lines.append(f"|{p['case']}/{p['config']}|{p['same_inputs']}|{counts[0]}|{counts[1]}|{p['original_pair_witness']}|")
    lines += ['', '来源：本地缓存的alexforencich/verilog-axis Git对象；每个原始文件核验Git blob和SHA256，保存直接父提交、修复提交、补丁、同提交README及工具日志。不宣称本轮重新联网核验上游。',
        '未调参资格限于已检查的本地请求/计划/协议/脚本记录。完整查阅清单与命中在准备目录prior_usage_audit.json；不能排除已删除或外部云机记录。独立结果未用于筛选。',
        'pipeline FIFO按各版实际握手建立队列，输入端口激励完全相同，容量变化可能导致接受数量不同；不把ready或延迟不同当违例。frame_len由独立接受拍累加及帧边界规则判定，手写SVA只作原生诊断，不计真实模型生成。',
        '编译/工具失败与缺少真实前后违例均保留unknown；空白排版修复明确排除。失败点是有限采样，不是独立Bug数量；非形式化证明。',
        '本轮未验证可编辑部分候选、旧保护＋当前漏报、非白名单区分和新独立余量，因此来源/见证通过不等于可以调用模型。H/R等价、条件恢复0/0及576次搜索负结果保持不变；stat及原始FIFO presented来源/见证unknown不变。','',f'成本：{cost}','',
        '执行命令（目录必须不存在）：','```powershell',f'wsl -- python3 scripts/research177_history_screen.py run --prepared {rel(prep)} --out {rel(out)}','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(matrix=matrix,cost=cost),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','run']);p.add_argument('--prepared',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED177')
    else:run(a.prepared.resolve(),a.out.resolve())
