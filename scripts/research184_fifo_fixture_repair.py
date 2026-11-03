"""Explicit local follow-up to research183's boolean serialization failure.

No new cases, stimuli, predicates, source revisions or acceptance criteria.
Old failed compilations remain archived and counted. No model/network calls.
"""
import argparse
import json
from pathlib import Path
import re
import research183_history_screen as s

ROOT=s.ROOT;D=s.D
P=D/'research183_history_prepare_20261101_r01'
R=D/'research183_history_native_20261101_r01'
A=D/'research183_history_report_20261101_r01'


def execute(out):
    s.verify(P);out.mkdir(parents=True,exist_ok=False);prep=out/'prepared';prep.mkdir();checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    old_cost=s.read(R/'cost.json')
    check('prior10 attempts',old_cost['native_compile_attempts']==10)
    check('within original hard cap16',old_cost['native_compile_attempts']+4<=16)
    for cfg in (8,16):
        original=(P/'frame_fifo_drop'/f'tb_{cfg}.sv').read_text()
        repaired=re.sub(r'\bTrue\b',"1'b1",re.sub(r'\bFalse\b',"1'b0",original))
        check('only TLAST boolean tokens need repair '+str(cfg),
              all('s_axis_tlast=' in line for line in original.splitlines() if re.search(r'\b(True|False)\b',line)))
        check('inverse serialization equality '+str(cfg), repaired.replace("1'b1",'True').replace("1'b0",'False')==original)
        check('no Python bool tokens '+str(cfg),not re.search(r'\b(True|False)\b',repaired))
        (prep/f'tb_{cfg}.sv').write_text(repaired)
        for rev in ('before','after'):
            r=s.read(R/'frame_fifo_drop'/str(cfg)/rev/'result.json')
            log=(R/'frame_fifo_drop'/str(cfg)/rev/'compile.log').read_text()
            check('actual fixture failure '+str(cfg)+rev,r['compile_status']=='failed' and "variable: 'False'" in log)
    # Independent local oracle controls; never model evidence or real RTL results.
    def row(c,sv=0,sd=0,sl=0,mv=0,md=0,ml=0):
        return dict(cycle=c,rst=0,sv=sv,sr=1,sd=sd,sl=sl,dest=0,mv=mv,mr=1,md=md,ml=ml,ov=0,good=0)
    good=[row(0,1,1,1),row(1,mv=1,md=1,ml=1)]
    check('oracle legal delivery pass',s.oracle(good,'frame_fifo_drop',8)['status']=='pass')
    check('oracle pending stays unknown',s.oracle(good[:1],'frame_fifo_drop',8)['status']=='unknown_pending')
    over=[row(i,1,80+i,int(i==11)) for i in range(12)]
    check('oracle oversize discarded',s.oracle(over,'frame_fifo_drop',8)['complete_scope_pass'])
    over.append(row(12,mv=1,md=90,ml=1))
    check('oracle oversize leakage violation',s.oracle(over,'frame_fifo_drop',8)['violations'][0]['obligation']=='oversize_frame_atomic_drop')
    s.dump(prep/'protocol.json',dict(
        purpose='local_boolean_serialization_repair_not_model_pilot',
        old_failure='research183 four FIFO compile failures preserved; not an RTL tool limitation',
        changed='Only generated TLAST True/False literals become 1\'b1/1\'b0. Stimulus semantics and diagnostic predicates unchanged.',
        source=P.as_posix(),configs=[8,16],additional_compile_budget=4,additional_execution_budget=4,
        retries=0,total_compile_cap_including_old=16,model_calls=0,network_calls=0,
        stop='After four fixed jobs, classify actual results, no substitute cases or new model protocol.',
        data='development only; no independent tests accessed',
        oracle='Unchanged research183 oracle; oversize frame must never appear, retained frame ordering checked; pending-only stays unknown.'))
    s.dump(prep/'checks.json',checks)
    s.dump(prep/'bindings.json',{s.rel(p):s.sha(p) for p in (Path(__file__),Path(s.__file__),P/'seal.json',R/'cost.json',A/'seal.json')})
    s.dump(prep/'seal.json',{p.name:s.sha(p) for p in prep.iterdir() if p.is_file()})
    jobs=[]
    for cfg in (8,16):
        for rev in ('before','after'):
            result=s.n.run_native((prep/f'tb_{cfg}.sv').read_text(),out/'native'/str(cfg)/rev,
                                  extra_sources=sorted((P/'frame_fifo_drop'/rev).glob('*.v')),timeout=240)
            jobs.append(dict(config=cfg,revision=rev,result=result));s.dump(out/'executions.json',jobs)
            print('NATIVE184',cfg,rev,result['compile_status'],result['execution_status'],flush=True)
    report=out/'report';report.mkdir();pairs=[]
    for cfg in (8,16):
        sides={};diagnostic={}
        for rev in ('before','after'):
            folder=out/'native'/str(cfg)/rev;r=s.read(folder/'result.json')
            if r['execution_status']!='completed':
                sides[rev]=dict(status='unknown_native');continue
            tr=s.traces(folder);v=s.oracle(tr,'frame_fifo_drop',cfg);sides[rev]=v
            check('legal source '+str(cfg)+rev,v['legal'])
            stim=s.read(P/'frame_fifo_drop'/f'stimuli_{cfg}.json')
            check('all sealed cycles '+str(cfg)+rev,len(tr)==len(stim))
            check('stimulus identical '+str(cfg)+rev,
                  all([x['cycle'],x['rst'],x['sv'],x['sd'],x['sl'],x['mr']]==[y['cycle'],y['rst'],y['v'],y['data'],int(y['last']),y['ready']] for x,y in zip(tr,stim)))
            s.dump(report/f'transactions_{cfg}_{rev}.json',v)
            diagnostic[rev]=dict(triggers=len(r['triggers']),alarms=len(r['failures']))
        witness=sides['before']['status']=='violation' and sides['after'].get('complete_scope_pass',False)
        pairs.append(dict(config=cfg,original_pair_witness=witness,
            before={k:sides['before'].get(k) for k in ('status','pending_in_bounded_drain','expected_return_count')},
            after={k:sides['after'].get(k) for k in ('status','pending_in_bounded_drain','expected_return_count')},
            before_violation_points=len(sides['before'].get('violations',[])),
            leaked_oversize_beats=sum(v['obligation']=='oversize_frame_atomic_drop' for v in sides['before'].get('violations',[])),
            diagnostic=diagnostic,partial_protection_qualified=False,
            partial_reason='Only existing diagnostic hold properties evaluated. No separately established historical target detection and current miss; violation point counts can include cascades, not independent bugs.'))
    matrix=s.read(A/'candidate_matrix.json')
    for x in matrix:
        if x['id']=='frame_fifo_drop':
            x['witness_configs']=[v['config'] for v in pairs if v['original_pair_witness']]
            x['reason']='new original synchronous FIFO drop witness; existing hold properties have no old target detections, partial qualification not established' if x['witness_configs'] else 'no qualifying original pair in repaired fixture scope; unknown retained'
            x['scope']='Original synchronous axis_fifo only; not asynchronous sibling or original FIFO presented case.'
            x['fixture_failure_preserved']=s.rel(R/'frame_fifo_drop')
    current=dict(model_calls=0,formal_calls=0,native_compile_attempts=len(jobs),native_executions=sum(x['result']['native_simulation_calls'] for x in jobs),
         compile_seconds=sum(x['result']['compile']['wall_seconds'] for x in jobs),execution_seconds=sum(x['result'].get('execute',{}).get('wall_seconds',0) for x in jobs))
    total={k:old_cost[k]+current[k] for k in current}
    s.dump(report/'cost.json',dict(research183=old_cost,fixture_repair=current,total=total))
    s.dump(report/'candidate_matrix.json',matrix);s.dump(report/'pair_results.json',pairs);s.dump(report/'checks.json',checks)
    s.dump(report/'decision.json',dict(action='STOP_NO_QUALIFIED_MODEL_PILOT',new_original_pair_cases=sum(bool(x['witness_configs']) for x in matrix),
         qualified_partial_candidates=0,models=0,conditional_recovery=dict(numerator=0,denominator=0,estimate=None),
         H_R='equivalent',search576='completed negative unchanged',
         next='Newly witnessed drop behavior can support a separately bounded local partial-candidate check; do not call a model before retained historical target detection plus current miss and non-whitelist difference are established.'))
    lines=['# research183/184 新历史案例本地筛选结果','',
           '**本轮未封存模型先导，未调用模型。原始前后见证与部分保护资格分开统计。**','',
           '|固定案例|原始功能前后见证|资格／限制|','|---|---|---|']
    for x in matrix:lines.append(f"|{x['id']}|{x['witness_configs']}|{x['reason']}|")
    lines+=['','## 执行结果','']
    for p in pairs:lines.append(f"- 同步frame FIFO Depth={p['config']}：旧版 {p['before']['status']}，修复版 {p['after']['status']}；旧版泄漏超长帧拍数 {p['leaked_oversize_beats']}，诊断保持性质 {p['diagnostic']}。")
    lines+=['','RAM switch：固定两组均原生执行；一组前后通过，另一组旧版接受115/返回113、2项未排空，修复版通过。缺少已确认的最大响应时限，保留unknown_pending，不追认为确定功能违例。单输出switch前后均遇当前Verilator零宽位选限制，unknown；包装器Python生成器修复不在本次直接RTL功能对照范围。',
            '', '四个候选按缓存Git日志顺序在补丁检查前锁定，未用预期机制收益筛选。源码与同版本依赖用Git blob核验，没有修补原RTL。840份开发请求/协议中未找到本次4个具体修复提交的匹配；FIFO模块已有340份请求提及，故只称新的提交/失效机制筛选，不称全新模块或从未接触的材料。该检索不覆盖外部/删除记录。',
            '', '首轮四次FIFO编译失败来自新增测试平台的True/False序列化错误；research183失败原样保留。research184另行封存，只转换TLAST数值字面量，原激励、源码、断言及判定规则未变。不是追改旧实验成功，也不是模型细化。',
            '', '## 资格与下一步','',
            '原始违例曝光不等于已有历史保护。当前手写输出保持性质尚未建立“历史目标检出＋另一个当前漏报”；未证明非白名单公共／历史区分，因此停止先导准备。不得把多个错误拍或后续错位计成多个独立失效机制。若继续，只能另立本地部分保护检查，先确认实质资格再考虑封存模型先导。',
            '', '本轮所有新样本为开发数据，今后不能再算搜索新增发现。未读取research181独立测试或成功性质来挑选候选。同步FIFO新提交与原始FIFO presented、既有人工FIFO验收严格区分；异步兄弟修复未验证。条件恢复0/0、不可估计；H/R等价及576次查询负结果不变。',
            '', f"合计原生编译尝试{total['native_compile_attempts']}次、执行{total['native_executions']}次，包含首轮失败成本；新模型/形式化0。所有结论限有限仿真范围，非形式化证明。",
            '', '可执行复现（新目录）：','```powershell',
            'wsl -- python3 scripts/research184_fifo_fixture_repair.py --out deliverables/research184_reproduce', '```']
    (report/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    s.dump(report/'source_bindings.json',{s.rel(p):s.sha(p) for p in [Path(__file__),prep/'seal.json',P/'seal.json',A/'seal.json',out/'executions.json']})
    s.dump(report/'seal.json',{p.name:s.sha(p) for p in report.iterdir() if p.is_file()})
    print('COMPLETE184',json.dumps(pairs),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    args=p.parse_args();s.isolation();execute(args.out.resolve())
