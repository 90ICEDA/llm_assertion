"""Replay authentic stat revisions; never manufacture a historical repair pair."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import research152_source_scope_recheck as base

ROOT=base.ROOT
SEARCH=ROOT/'deliverables/research155_stat_history_20261027_r01'
ARCHIVE=SEARCH/'archive_r02'
PRIOR=ROOT/'deliverables/research152_source_scope_prepare_20261027_r02'
REVISIONS={
    'keep_interface_2017':'b00eaf4d3ce6564c8c1e1bbe953ea12a3d5c2839',
    'before_latest_file_change':'fc5964ab90d63373328308d9d15301a894220b20',
    'upstream_head':'48ff7a7e2ef782cf778d47910cf85835c64b1bce',
}
dump=base.dump
read=base.read
sha=base.sha


def git(*args):
    return subprocess.check_output(['git','--git-dir='+str(SEARCH/'upstream.git'),*args])


def verify(folder):
    for name,h in read(folder/'seal.json').items():
        assert sha(folder/name)==h,name


def prepare(out):
    base.verify(PRIOR);verify(ARCHIVE)
    out.mkdir(parents=True,exist_ok=False)
    history=read(ARCHIVE/'history.json');checks=[]
    for item in history['commits']:
        source=(ARCHIVE/'commits'/item['commit']/'axis_stat_counter.v').read_text()
        block=re.sub(r'//[^\n]*','',item['frame_block'])
        match=re.search(r'if\s*\(monitor_axis_tlast\)\s*begin\s*frame_next\s*=\s*(?:1\'b)?0\s*;\s*end\s*else\s*if\s*\([!~]frame_reg\)\s*begin\s*frame_count_next\s*=\s*frame_count_next\s*\+\s*1\s*;',block)
        checks.append(dict(commit=item['commit'],frame_counter_increments=source.count('frame_count_next = frame_count_next + 1;'),
            last_branch_skips_increment=bool(match),interpretation='Static control-flow evidence, not a simulation result.'))
    assert all(c['last_branch_skips_increment'] and c['frame_counter_increments']==1 for c in checks)
    dump(out/'history_control_flow.json',checks)
    for label,c in REVISIONS.items():
        folder=out/'sources'/label;folder.mkdir(parents=True)
        (folder/'axis_stat_counter.v').write_bytes(git('show',c+':rtl/axis_stat_counter.v'))
        (folder/'commit.txt').write_bytes(git('show','-s','--format=fuller',c))
        (folder/'README.md').write_bytes(git('show',c+':README.md'))
        (folder/'upstream_test.py').write_bytes(git('show',c+':tb/test_axis_stat_counter.py'))
        assert sha(folder/'axis_stat_counter.v')==hashlib.sha256(git('show',c+':rtl/axis_stat_counter.v')).hexdigest()
        for width in (8,64):
            rows=read(PRIOR/f'stat_axis_w{width}.json')
            bench=base.axis_tb(rows,width)
            if label=='keep_interface_2017':bench=bench.replace('m_axis_','output_axis_')
            (folder/f'tb_w{width}.sv').write_text(bench)
    for width in (8,64):shutil.copy2(PRIOR/f'stat_axis_w{width}.json',out/f'stimulus_w{width}.json')
    (out/'last_module_change.patch').write_bytes(git('show','b9e0af36341a81ae80d6a8467b029d79c69b71cb','--','rtl/axis_stat_counter.v'))
    dump(out/'protocol.json',dict(revisions=REVISIONS,widths=[8,64],
        dataset='Previously exposed research152 development stimuli. Not new independent validation.',
        scope='Complete single/multi-beat frames, contiguous low tkeep, legal input stalls and output backpressure, quiet nonbusy snapshot. No in-flight trigger contract.',
        oracle='Reuse independently accepted-tlast frame count and accepted-byte snapshot oracle. No replacement of RTL or SVA verdicts.',
        selection='First revision adding current KEEP_ENABLE interface, parent of latest module edit, fetched upstream HEAD. Historical persistence checks only, not alleged repair candidates.',
        interface_adapter='2017 testbench output signal names only: m_axis_ -> output_axis_. RTL bytes exactly Git blob.',
        outcomes='A genuine fix requires an actual sourced repair commit and same-input fail/pass. None identified in searched refs; all-pass at some revision would require further investigation, not retroactive relabeling.',
        unchanged_unknowns=['case505 upstream derivation/temporal contract','original FIFO presented historical repair witness'],
        model_calls=0,formal_calls=0,max_native_compiles=6,max_native_executions=6))
    dump(out/'bindings.json',{base.rel(p):sha(p) for p in (Path(__file__),ROOT/'scripts/research152_source_scope_recheck.py',ROOT/'scripts/research_native_runner.py',ARCHIVE/'seal.json')})
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    verify(out);print('PREPARED156 3 authentic revisions x 2 widths; no repaired revision claimed',flush=True)


def run(prep,out):
    verify(prep);base.verify(PRIOR);verify(ARCHIVE)
    for name,h in read(prep/'bindings.json').items():assert sha(ROOT/name)==h,name
    out.mkdir(parents=True,exist_ok=False);results=[]
    protocol=read(prep/'protocol.json')
    for label,c in protocol['revisions'].items():
        for width in protocol['widths']:
            folder=out/label/f'w{width}';source=prep/'sources'/label/'axis_stat_counter.v'
            result=base.native.run_native((source.parent/f'tb_w{width}.sv').read_text(),folder,extra_sources=[source])
            entry=dict(label=label,commit=c,width=width,source_sha256=sha(source),native=result,oracle_status='unknown')
            if result['execution_status']=='completed':
                rows=read(prep/f'stimulus_w{width}.json');trace=base.trace(folder,rows);oracle=base.axis_oracle(trace,rows,width)
                dump(folder/'trace.json',trace);dump(folder/'oracle.json',oracle)
                entry.update(oracle_status='violation' if oracle['failed'] else 'no_violation_in_scope',
                    failures=oracle['failed'],responses=[e for e in oracle['events'] if e['kind']=='snapshot_response'],
                    accepted_beats=sum(e['kind']=='monitor_beat_accepted' for e in oracle['events']))
            results.append(entry);dump(out/'progress.json',results)
            print('REPLAY156',label,width,result['compile_status'],result['execution_status'],entry['oracle_status'],flush=True)
    verify(prep)
    dump(out/'results.json',dict(results=results,model_calls=0,formal_calls=0,historical_repair_pair=None,
        historical_repair_successes=0,stat_case505='unknown',fifo_presented_history='unknown'))


def audit(prep,run_path,out):
    verify(prep);verify(ARCHIVE);base.verify(PRIOR)
    out.mkdir(parents=True,exist_ok=False);results=read(run_path/'results.json');checks=[];rows_out=[];cost={'model_calls':0,'formal_calls':0,'native_compile_attempts':0,'native_executions':0,'compile_seconds':0.0,'execute_seconds':0.0}
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value:raise AssertionError(name)
    hist=read(ARCHIVE/'history.json')
    check('complete fetched branch history',not hist['shallow'])
    for c in read(prep/'history_control_flow.json'):
        check('persistent skip branch '+c['commit'],c['last_branch_skips_increment'] and c['frame_counter_increments']==1)
    for r in results['results']:
        label=r['label'];w=r['width'];folder=run_path/label/f'w{w}';source=prep/'sources'/label/'axis_stat_counter.v'
        check('exact source '+label+str(w),source.read_bytes()==git('show',r['commit']+':rtl/axis_stat_counter.v'))
        check('bench frozen '+label+str(w),(folder/'tb.sv').read_bytes()==(source.parent/f'tb_w{w}.sv').read_bytes())
        n=read(folder/'result.json');check('record consistency '+label+str(w),n==r['native'])
        cost['native_compile_attempts']+=1;cost['compile_seconds']+=n['compile']['wall_seconds']
        if 'execute' in n:cost['native_executions']+=1;cost['execute_seconds']+=n['execute']['wall_seconds']
        if n['execution_status']!='completed':continue
        stimuli=read(prep/f'stimulus_w{w}.json');trace=base.trace(folder,stimuli);oracle=base.axis_oracle(trace,stimuli,w)
        check('recomputed trace '+label+str(w),trace==read(folder/'trace.json'))
        check('recomputed oracle '+label+str(w),oracle==read(folder/'oracle.json'))
        for e in oracle['events']:
            if e['kind']=='snapshot_response':rows_out.append(dict(revision=label,width=w,epoch=e['epoch'],expected=e['expected'],actual=e['actual'],passed=e['expected']==e['actual']))
    dump(out/'audit.json',dict(checks=checks,cost=cost))
    dump(out/'scope_matrix.json',dict(snapshots=rows_out,historical_repair_successes=0,
        statement='No corresponding real repair identified in inspected refs. Not proof that no external fork/private fix exists.',
        exclusions=['case505 derivation unknown','FIFO presented historical witness unknown','No LLM refinement or new independent validation in this audit']))
    table='\n'.join(f"|{r['revision']}|{r['width']}|{r['epoch']}|{r['expected'][-1]}|{r['actual'][-1]}|{'通过' if r['passed'] else '违例'}|" for r in rows_out)
    refs=(ARCHIVE/'refs.txt').read_text().splitlines()
    text=f'''# 原始 stat 单拍帧计数问题：真实修复历史检索与回放

结论：在本轮检索范围内未找到对应真实修复提交，不能建立合格的修复前后 fail/pass 对。历史修复成功数为0。旧stat(case505)来源和原始FIFO presented历史见证继续unknown。

## 检索范围与来源

- [原上游](https://github.com/alexforencich/verilog-axis)：完整非浅克隆，固定HEAD `{hist['head']}`；包含全部公开分支/标签及14个PR head，共{len(refs)}个引用。
- 模块历史共{len(hist['commits'])}次修改，首次引入 `f22381baa2c5183a2948431e5dd347b69148d39c`（2014），全部快照的唯一帧计数递增均位于tlast分支的else if内。单拍帧在首次拍即tlast，因此跳过递增。此为静态路径核查，不等同19次原生实验。
- 最新模块编辑 [b9e0af3](https://github.com/alexforencich/verilog-axis/commit/b9e0af36341a81ae80d6a8467b029d79c69b71cb)只回退输出ready条件，没有修改帧计数。
- 公开issues/PR检索4组，包含原仓库stat、single frame、全站axis_stat_counter和后继taxi。原仓库相关结果未提供该修复；全站命中为UHDM转换器测试PR，不是计数修复。
- 后继taxi的 `src/axis/rtl` 公开目录中没有axis_stat_counter。只说明该目录未提供对应模块，不宣称穷尽所有分支/分叉或私有修复。
- 首次taxi递归树下载出现IncompleteRead，保留未完成archive；随后缩小到AXI RTL目录重新检索，完整结果在archive_r02。搜索无结果不等于修复不存在。

## 相同合法输入的原生回放

预先固定2017加入KEEP接口版本、最新模块编辑的父提交、当前HEAD，使用同一research152开发激励。原始RTL逐字节匹配Git对象；2017仅在测试平台适配输出端口名称，无RTL修改。不是修复对，也不是新独立测试。

|版本|位宽|快照|期望帧数|实际帧数|结果|
|---|---:|---:|---:|---:|---|
{table}

范围：8/64位，已完成单拍/多拍帧，连续低位tkeep，合法输入背压、输出背压，非busy且完整帧后触发快照。参考计数依据valid&&ready接受及tlast完成事件，输出解码为tag/ticks/bytes/frames；不主张跨中途trigger语义或任意tkeep。

帧计数违例由独立事务oracle判定；本次原生SVA另检查输出背压稳定性，不能将该SVA通过冒充帧计数通过。波形、工具版本、原始日志与事务均保留。

## 成本与未完成项

本轮{cost['native_compile_attempts']}次编译，{cost['native_executions']}次执行；模型0、形式化0；{len(checks)}项只读复核。编译{cost['compile_seconds']:.3f}s，执行{cost['execute_seconds']:.3f}s。有限仿真不等于证明。

待补条件是带可靠来源的真实修复版本。目前不能填写fixed commit，也不能用人工补丁、FIFO闲置错误或旧简化stat案例替代。若另有分叉/修复提交，可用已封存输入直接执行前后见证；没有该来源时维持unknown。

## 复现

在仓库根目录执行，使用全新输出目录：

```powershell
wsl -- python3 scripts/research156_stat_revision_replay.py run --prepared {base.rel(prep)} --out deliverables/research156_new_replay
wsl -- python3 scripts/research156_stat_revision_replay.py audit --prepared {base.rel(prep)} --run {base.rel(run_path)} --out deliverables/research156_new_audit
```
'''
    (out/'SUMMARY.md').write_text(text)
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print('AUDITED156',len(checks),'checks;',cost,'historical repair pairs 0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','audit']);ap.add_argument('--prepared',type=Path);ap.add_argument('--run',type=Path);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='run':run(a.prepared.resolve(),a.out.resolve())
    else:audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
