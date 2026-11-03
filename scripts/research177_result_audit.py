"""Read-only original-history witness audit. No native/model reruns."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import research177_history_screen as s


def audit(prep,run,out):
    s.verify(prep)
    for name,h in s.read(run/'seal.json').items():assert s.sha(run/name)==h,name
    checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    sources=s.read(prep/'source_manifest.json')
    for src in sources:
        p=s.ROOT/src['path'];data=p.read_bytes()
        check(src['case']+src['revision']+' frozen SHA',s.sha(p)==src['sha256'])
        check(src['case']+src['revision']+' Git blob',hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==src['git_blob'])
        check(src['case']+src['revision']+' cached original identity',data==s.git('show',src['commit']+':rtl/'+p.name))
    cases=s.read(prep/'cases.json');pairs=s.read(run/'paired_results.json');rows=[];witnesses=[];native_trigger_map=[]
    for p in pairs:
        c=next(c for c in cases if c['id']==p['case']);traces={}
        for rev in ('before','after'):
            folder=run/p['case']/str(p['config'])/rev;n=s.read(folder/'result.json');tr=s.trace(folder);traces[rev]=tr
            check(f'{c["id"]}/{p["config"]}/{rev} complete',n['compile_status']=='passed' and n['execution_status']=='completed')
            check(f'{c["id"]}/{p["config"]}/{rev} original source',str(prep/c['id']/rev/(c['module']+'.v')) in n['compile']['argv'])
            check(f'{c["id"]}/{p["config"]}/{rev} exact bench',(folder/'tb.sv').read_text().strip()==(prep/c['id']/f'tb_{p["config"]}.sv').read_text().strip())
            oracle=s.oracle_pipe(tr) if c['module']=='axis_pipeline_fifo' else s.oracle_frame(tr,p['config'])
            check(f'{c["id"]}/{p["config"]}/{rev} rejudged oracle',oracle==p['revisions'][rev]['oracle'])
            check(f'{c["id"]}/{p["config"]}/{rev} source holds under stall',oracle['legal'])
            native_trigger_map.append(dict(case=c['id'],config=p['config'],revision=rev,
                failures=len(n['failures']),triggers=dict(Counter(x['id'] for x in n['triggers'])),
                interpretation='Handwritten diagnostic SVA only. Trigger markers are procedural diagnostics, not native cover proof.'))
            if c['module']=='axis_pipeline_fifo':
                accepted=sum(not v['rst'] and v['sv'] and v['sr'] for v in tr)
                returned=sum(not v['rst'] and v['mv'] and v['mr'] for v in tr)
                check(f'{c["id"]}/{p["config"]}/{rev} direct accepted count',accepted==oracle['accepted'])
                check(f'{c["id"]}/{p["config"]}/{rev} direct returned count',returned==oracle['returned'])
                check(f'{c["id"]}/{p["config"]}/{rev} unbounded sink ready during drain',all(v['mr'] and not v['sv'] for v in tr if v['cycle']>=100))
                rows.append(dict(case=c['id'],config=p['config'],revision=rev,accepted=accepted,returned=returned,
                    missing_in_executed_drain=accepted-returned,reference_failure_points=len(oracle['failures'])))
            else:
                # Separate group-based reconstruction from actual sampled input.
                pending=[];due={};cancelled=[]
                for v in tr:
                    if v['rst']:
                        if pending:cancelled.append(pending.copy())
                        pending=[];continue
                    if v['v'] and v['r']:
                        pending.append(dict(cycle=v['cycle'],bytes=v['k'].bit_count() if p['config'] else 1,last=v['last']))
                        if v['last']:
                            due[v['cycle']+1]=dict(requests=pending.copy(),expected=sum(x['bytes'] for x in pending));pending=[]
                mismatches=[]
                for v in tr:
                    if v['rst']:continue
                    e=due.get(v['cycle']);check(f'frame{p["config"]}/{rev} valid{v["cycle"]}',bool(v['valid'])==bool(e))
                    if e and e['expected']!=v['length']:mismatches.append(v['cycle'])
                check(f'frame{p["config"]}/{rev} group reference agreement',mismatches==[v['cycle'] for v in oracle['failures']])
                check(f'frame{p["config"]}/{rev} native failure agreement',sorted(mismatches)==sorted(int(v['detail'].split('=')[1]) for v in n['failures']))
                rows.append(dict(case=c['id'],config=p['config'],revision=rev,exposed_completions=len(due),
                    incorrect_lengths=len(mismatches),reset_cancellations=len(cancelled)))
                if rev=='before':
                    for cycle in mismatches:
                        witnesses.append(dict(case=c['id'],config=p['config'],response_cycle=cycle,
                            requests=due[cycle]['requests'],expected=due[cycle]['expected'],old_length=tr[cycle]['length'],
                            stimulus=tr[max(0,cycle-2):cycle+1]))
        keys=('rst','sv','sd','sl','mr') if c['module']=='axis_pipeline_fifo' else ('rst','v','r','k','last')
        check(c['id']+str(p['config'])+' same input port stimulus',len(traces['before'])==len(traces['after']) and all(all(a[k]==b[k] for k in keys) for a,b in zip(traces['before'],traces['after'])))
        for w in witnesses:
            if w['case']==c['id'] and w['config']==p['config']:
                w['fixed_length']=traces['after'][w['response_cycle']]['length']
                check('fixed length matches independent sum '+str(w['response_cycle'])+' cfg'+str(p['config']),w['fixed_length']==w['expected'])
    use=s.read(prep/'prior_usage_audit.json');check('no recorded exact-name metadata matches',not use['hits']);check('no prior research-script matches',not use['script_hits'])
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('checks',checks),('pair_counts',rows),('frame_length_witnesses',witnesses),('native_diagnostic_counts',native_trigger_map)]:s.dump(out/(name+'.json'),value)
    s.dump(out/'source_bindings.json',{s.rel(p):s.sha(p) for p in (Path(__file__),prep/'seal.json',run/'seal.json',prep/'prior_usage_audit.json')})
    lines=['# research177 原始历史案例见证复核','',
        '**固定4项候选中，2项通过来源与原始前后见证筛选，1项无合格功能见证保留unknown，1项仅排版改动排除。没有模型调用或先导封存。**','',
        '|候选|结果及范围|','|---|---|',
        '|axis_pipeline_fifo / 0b5fc5b|LENGTH=2旧版接受62/输出61，新版65/65；LENGTH=4旧版64/63，新版71/71。相同合法输入、持续背压解除后充分排空，确认原始已接受数据丢失。LENGTH=3两版64/64，为无违例对照。|',
        '|axis_frame_len / 0b2066a|KEEP关闭8位、KEEP启用32位两配置各8个完成帧；旧版各4个长度错误，修复版各0。有效完成标记两版一致，计数不应跨帧累加。|',
        '|axis_pipeline_fifo / 6c23426|阻塞改非阻塞赋值；本轮两版均出现同样容量/排空问题，未证明该修改解决独立功能违例。保留unknown，不能将邻近off-by-one修复的成功移植过来。|',
        '|axis_switch / a613cc8|仅clk/rst端口空白对齐；去空白后源码相同，排除为非功能修复，未花费仿真额度。|','',
        'pipeline激励保持相同数据，避免源端在背压中变化；每次握手仍是独立接受事件。丢失结论依据接受/返回数量不守恒及帧边界错位。**重复数据不能唯一定位到底哪一个输入拍丢失**；原队列中的待匹配请求只是顺序参考，不能把cycle99等标成已定位的实际丢失事务。首次失配后的逐请求归因保留不确定，不额外计为多个Bug。',
        'frame_len例：KEEP启用时第二个连续单拍帧接受2字节，旧输出6、新输出2；第三帧接受1字节，旧输出7、新输出1。frame_length_witnesses.json记录接受周期、响应周期、原始采样及固定版本结果；组帧累加复核与原生SVA诊断一致。',
        '其规格来自原模块注释、参数约定及接口：只计valid&&ready，连续低位KEEP表示有效字节；注册完成输出晚一周期，复位取消部分帧。本轮没有稀疏KEEP、计数溢出或多时钟验证。它是新的frame_len案例，不能据此补认旧stat的来源或真实修复。','',
        '## 使用记录与来源边界','',
        f"已检查{len(use['files'])}份既有模型请求/计划/开发协议元数据及研究脚本，精确模块名/提交命中0；未扫描独立结果用于选择。候选顺序在看补丁前固定。只能说“已审计本地记录中无调参使用证据”，不能排除外部云机或已删除记录。",
        '8份原始RTL文件均与缓存Git提交blob逐字一致，父提交、修复提交、SHA256、补丁及同提交README保存。两次慢速目录遍历在封存/仿真前中断，r01/r02保留；最终r03使用Windows rg文件清单。没有隐式仿真重试。','',
        f'只读复核{len(checks)}项通过；执行成本为12次原生编译、12次执行，编译102.977秒、执行0.235秒；模型/网络/形式化均0。手写诊断SVA不是模型生成。原生工具版本、命令、日志、波形和完整失败记录均在运行目录。','',
        '## 下一步','',
        '只把上述2项作为下一阶段本地候选：分别核查是否已有可编辑部分性质，能同时保留历史目标检出并遗漏当前目标，以及公共/历史规则的非白名单区分和新的独立目标余量。**本轮尚未建立这些资格，不应立即调用模型。** H/R等价、条件恢复0/0及576次搜索负结果不变。','',
        '固定清单：`deliverables/research177_history_screen_20261029_r01/population_lock.json`；源码、排除清单和协议：`deliverables/research177_history_prepare_20261029_r03/`；原生结果：`deliverables/research177_history_run_20261029_r01/`。','',
        '只读复核命令（新输出目录）：','```powershell',
        'wsl -- python3 scripts/research177_result_audit.py --prepared deliverables/research177_history_prepare_20261029_r03 --run deliverables/research177_history_run_20261029_r01 --out deliverables/research177_report_recheck','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    s.dump(out/'seal.json',{p.relative_to(out).as_posix():s.sha(p) for p in out.rglob('*') if p.is_file()})
    print('AUDITED177',len(checks),'checks;2 source/witness cases;0 model/pilot',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
