"""Read-only audit of the bounded screen, source novelty and drop witness."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import research183_history_screen as s

D=s.D;ROOT=s.ROOT
P=D/'research183_history_prepare_20261101_r01'
R=D/'research183_history_native_20261101_r01'
F=D/'research184_fifo_fixture_repair_20261101_r01'


def normalized_module(text,module):
    match=re.search(r'\bmodule\s+'+re.escape(module)+r'\b.*?\bendmodule\b',text,re.S)
    return re.sub(r'\s+','',match.group()) if match else None


def strings(obj):
    if isinstance(obj,dict):
        for v in obj.values():yield from strings(v)
    elif isinstance(obj,list):
        for v in obj:yield from strings(v)
    elif isinstance(obj,str):
        yield obj
        if obj.strip().startswith(('{','[')):
            try:child=json.loads(obj)
            except (ValueError,RecursionError):return
            yield from strings(child)


def audit(out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for folder in (P,F/'prepared',F/'report',D/'research183_history_report_20261101_r01'):
        for name,h in s.read(folder/'seal.json').items():check('seal '+s.rel(folder/name),s.sha(folder/name)==h)
    for row in s.read(P/'source_manifest.json'):
        path=ROOT/row['path'];raw=path.read_bytes()
        check('blob '+row['path'],hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==row['git_blob'] and s.sha(path)==row['sha256'])
    candidates=s.read(P/'cases.json'); wanted={};matches=[];scanned=[]
    for c in candidates:
        for mod in c['modules']:
            for rev in ('before','after'):
                path=P/c['id']/rev/(mod+'.v')
                if path.exists():wanted[(c['id'],mod,rev)]=normalized_module(path.read_text(),mod)
    usage=s.read(P/'prior_usage.json')
    for item in usage['files']:
        path=ROOT/item['path']
        if 'request' not in path.name:continue
        check('unchanged prior request '+item['path'],s.sha(path)==item['sha256'])
        scanned.append(item)
        for text in strings(s.read(path)):
            if 'module' not in text:continue
            for (case,mod,rev),expected in wanted.items():
                value=normalized_module(text,mod)
                if value and value==expected:matches.append(dict(case=case,module=mod,revision=rev,request=item['path']))
    unique={json.dumps(x,sort_keys=True):x for x in matches}
    s.dump(out/'prior_request_source_usage.json',dict(request_files=scanned,matches=list(unique.values()),
        comparison='Full named module through endmodule, whitespace normalized, recursively decode JSON message bodies. Module names alone do not imply exact revision reuse.',
        scope='Recorded local development inventory only, not external/deleted source or all model requests ever made.',
        conclusion='No exact module-body match in the scanned requests' if not unique else 'Exact matches retained; cannot call corresponding revision unused.'))
    # Reconstruct the decisive witness independently as input/output frames.
    witnesses=[]
    for cfg in (8,16):
        sides={}
        for rev in ('before','after'):
            folder=F/'native'/str(cfg)/rev;native=s.read(folder/'result.json');tr=s.traces(folder)
            check('native complete '+str(cfg)+rev,native['compile_status']=='passed' and native['execution_status']=='completed')
            reference=s.oracle(tr,'frame_fifo_drop',cfg)
            frames=[];current=[]
            for v in tr:
                if not v['rst'] and v['sv'] and v['sr']:
                    current.append(dict(cycle=v['cycle'],data=v['sd'],last=v['sl']))
                    if v['sl']:frames.append(current);current=[]
            check('three completed input frames '+str(cfg)+rev,len(frames)==3 and not current)
            check('expected frame sizes '+str(cfg)+rev,[len(x) for x in frames]==[cfg-1,cfg+4,3])
            forbidden={x['data']:x for x in frames[1]};allowed=[(x['data'],x['last']) for f in (frames[0],frames[2]) for x in f]
            outputs=[dict(cycle=v['cycle'],data=v['md'],last=v['ml']) for v in tr if not v['rst'] and v['mv'] and v['mr']]
            leaked=[dict(request=forbidden[x['data']],response=x) for x in outputs if x['data'] in forbidden]
            retained=[(x['data'],x['last']) for x in outputs if x['data'] not in forbidden]
            check('surrounding legal frames remain '+str(cfg)+rev,retained==allowed)
            if rev=='after':check('fixed no oversized leakage '+str(cfg),not leaked and reference['complete_scope_pass'])
            # Match old/fixed source vectors exactly, not just the test program.
            sides[rev]=dict(input_frames=frames,outputs=outputs,leaked=leaked,
                            source_vectors=[[v[k] for k in ('cycle','rst','sv','sd','sl','mr')] for v in tr],
                            hold_assertion_failures=len(native['failures']),hold_triggers=len(native['triggers']))
        check('same actual stimuli '+str(cfg),sides['before']['source_vectors']==sides['after']['source_vectors'])
        if cfg==16:
            check('14 actual leaked beats',len(sides['before']['leaked'])==14)
            check('current missed by existing hold checks',sides['before']['hold_assertion_failures']==0)
        witnesses.append(dict(config=cfg,before=sides['before'],after=sides['after'],
                              independent_bug_count=1 if sides['before']['leaked'] else 0,
                              partial_qualification=False))
    s.dump(out/'verified_frame_witnesses.json',witnesses)
    matrix=s.read(F/'report/candidate_matrix.json')
    for row in matrix:
        row['exact_module_request_matches']=[x for x in unique.values() if x['case']==row['id']]
    s.dump(out/'candidate_matrix.json',matrix)
    s.dump(out/'checks.json',checks)
    s.dump(out/'decision.json',dict(original_fix_witness_cases=1,new_partial_qualified_candidates=0,
        action='STOP_NO_MODEL_PILOT',conditional_recovery=dict(numerator=0,denominator=0,estimate=None),
        next_local_only='For the new synchronous FIFO drop witness, separately check a partial candidate with actual prior target detection and a different current miss. Existing hold-only candidate is ineligible. No model call or pilot request now.',
        H_R='equivalent',search576='unchanged valid negative',new_evidence_role='development_known_from_now_on'))
    cost=s.read(F/'report/cost.json');s.dump(out/'cost.json',cost)
    failure=sides # no dependence on any independent/tested result
    lines=['# 新历史案例筛选：最终本地审计','',
           '**固定4个案例，确认1个原始修复前后功能见证；新增合格部分候选0个。停止，不封存模型先导。**','',
           '|案例|实际结果|资格|','|---|---|---|',
           '|单输出switch索引修复|前后均受Verilator零宽位选限制|unknown|',
           '|switch包装器参数修复|仅Python包装器生成器；未进入直接RTL对照|本轮排除，未声称无法复现|',
           '|RAM switch背压修复|一组前后通过；另一组旧版115接受/113返回，固定时限剩2项，新版排空|缺少明确延迟上限，pending unknown；保持断言无旧目标检出|',
           '|同步frame FIFO drop修复|Depth16旧版泄漏超长帧14拍，修复版0；两侧正常帧均完整。Depth8未曝光|真实前后见证成立；保持断言漏报，缺少旧目标检出，不能进入模型先导|',
           '', '修复提交：`a9c04a465150ae5fc9cd8f32906213d9ba9afb06`；父提交：`6795c25e7ffd5d8380e3fc1f8b34e30179a24df7`。来源为本地缓存的 alexforencich/verilog-axis 原始Git对象。原始RTL与依赖文件逐项Git blob校验，未替换设计代码。',
           '', 'Depth16的输入帧长度为15、20、3拍。20拍超长帧在存储已满后遇到空闲及下游排空；旧版未保持丢帧状态，输出其中14拍。修复版整帧丢弃，前后各18拍正常数据完整。17条顺序/丢帧报警记录包含14条泄漏及3条后续错位，不能计成17个Bug；独立按帧过滤复核确认正常帧自身未丢失。实际输入端口向量前后完全相同。',
           '', '已有输出保持性质在Depth16触发19次、违例检出0，故确认当前漏报，但尚无历史目标检出，不能用“触发”代替保护资格。未通过删去成功断言或样本白名单制造普通/历史差异。异步FIFO兄弟修复未执行；这不是原始FIFO presented案例，也不追改已有FIFO验收。',
           '', f'使用历史：扫描840份开发元数据，其中{len(scanned)}份请求进一步递归解析并比较完整模块正文；找到{len(unique)}个相同正文匹配。FIFO模块名此前已被使用，故这里只报告新增修复版本/失效机制；无匹配结论限该本地记录范围，不能排除外部或删除材料。research181独立结果、成功性质均未用于筛选。',
           '', '首轮四次FIFO编译失败是新增测试平台序列化错误，旧记录保留。随后另封存数值字面量修正；源码、激励与原生标准不变。合计14次编译尝试、8次执行，模型及形式化调用0；全部成本见cost.json。',
           '', f'本轮审计{len(checks)}项通过。新的见证均归入开发已知清单，不可在后续契约搜索中重新计为新增发现。条件恢复仍0/0不可估计；H/R等价；576次搜索负结果不变。',
           '', '**若继续，下一步只能是这一新drop机制的本地部分保护资格检查；资格成立前不封存模型先导。** 本轮没有完成跨案例稳定性或新的契约搜索公平比较。',
           '', '复核命令（新目录，不调用模型或仿真）：','```powershell',
           'wsl -- python3 scripts/research183_result_audit.py --out deliverables/research183_screen_recheck','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    sources=[Path(__file__),P/'seal.json',F/'prepared/seal.json',F/'report/seal.json']
    for cfg in (8,16):
        for rev in ('before','after'):
            sources += [F/'native'/str(cfg)/rev/f for f in ('tb.sv','result.json','execute.log')]
    s.dump(out/'source_bindings.json',{s.rel(p):s.sha(p) for p in sources})
    s.dump(out/'seal.json',{p.name:s.sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(checks=len(checks),requests=len(scanned),prior_exact_module_matches=len(unique),original_witness_cases=1,new_partial_candidates=0)))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);args=ap.parse_args();s.isolation();audit(args.out.resolve())
