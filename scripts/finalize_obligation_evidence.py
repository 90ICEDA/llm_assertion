"""Strict audit/report from raw records. Search outputs remain untouched."""
import argparse
import collections
import csv
import json
from pathlib import Path
import shutil
import run_obligation_evidence as x


def obligations():
    definitions={
      'onehot':[('multihot_detect','popcount(oh_i)>1','same sampled input word','err_o=1',0,'all 4-bit words are legal; error may also assert for independent address/enable checks')],
      'fifo':[('empty_when_idle','push_i=0','current presentation','empty_o=1',0,'Depth=0 only'),('nonempty_when_present','push_i=1','stable item until pop or reset','empty_o=0',0,'pop=0 stalls without withdrawing or changing presented data')],
      'filter':[('qualified_value','every active sample; enabled qualification or disabled bypass','maximal equal-input episode; polarity change discards progress','output equals stored value when enabled, else current input',0,'threshold held per reset epoch; threshold equal intervals update stored value for next pre-NBA sample')],
      'spill':[('collision_empty','flush_i && push_i','collision event at trigger','valid_o=0',1,'flush takes priority; raw data_o requirement UNRESOLVED')],
      'stat':[('valid_latency','each frame_done_i event, including overlaps','epoch + trigger sample','stat_valid_o corresponds exactly to due events',2,'absence checked when no event due; earlier transaction can validly occupy next sample'),('captured_length','each frame_done_i event','epoch + trigger sample + captured frame_len_i','stat_len_o equals captured length on due sample',2,'different lengths and consecutive events allowed')],
      'intr':[('mask_timing_unresolved','enable=0','current or previous sampling interpretation UNRESOLVED','intr_o=0 under respective interpretation',None,'both interpretations retained; neither promoted to definitive full-parent acceptance')]}
    out=[]
    for k,items in definitions.items():
        for name,trigger,transaction,response,delay,allowed in items:
            out.append(dict(obligation_id=k+'.'+name,parent_bug=x.IDS[k],case=k,prerequisites=x.read(x.OUT/'frozen'/k/'contract.json')['parameters'],
                trigger=trigger,transaction_ownership=transaction,required_response=response,response_deadline_samples=delay,
                permitted_behavior=allowed,forbidden_behavior='violation of required response at exact due sample',reset='active-low reset cancels outstanding events and starts a new epoch; no checks during reset',
                source=x.rel(x.OUT/'frozen'/k/'spec_sources.json'),scope='target repair obligation, not all module functionality',
                status='unresolved' if k=='intr' else 'confirmed_common_part' if k=='spill' else 'scoped_contract'))
    x.dump(x.OUT/'obligation_catalog.json',out)


def verify_pairs(qs):
    """Compare whole-prefix rejection, not just different failure timestamps."""
    output=[]
    for p in x.read(x.OUT/'pairs_frozen.json'):
        if not p['natural_pair']:continue
        k=next(k for k,v in x.IDS.items() if v==p['parent_bug_id'])
        pool=x.read(x.OUT/'frozen'/k/'candidates.json')['candidates'];indices={c['id']:i for i,c in enumerate(pool)}
        for method in ['ordinary','disagreement','obligation']:
            witnesses=[]
            for q in qs:
                if q['case']!=k or q['method']!=method or q['status']!='ok':continue
                for rr in q['runs']:
                    folder=x.ROOT/rr['run'];tr=x.read(folder/'trace.json');d=x.read(folder/'definition.json');oracle=x.read(folder/'independent_reference.json')
                    refs={o['cycle']:o for o in oracle['events']}
                    aa={r['cycle']:r for r in x.read(folder/f'checker_{indices[p["a"]]}_cycles.json')}
                    bb={r['cycle']:r for r in x.read(folder/f'checker_{indices[p["b"]]}_cycles.json')}
                    a=b=False
                    for row in tr:
                        t=row['cycle']
                        if not row[d['rst']]:a=b=False;continue
                        a |= bool(aa[t]['fail']);b |= bool(bb[t]['fail'])
                        o=refs[t]
                        if a==b or o['classification']=='unknown_spec':continue
                        if o['legal_prefix'] or o['first_violation']:
                            witnesses.append(dict(run=rr['run'],cycle=t,seed=q['seed'],query=q['query_id'],
                                a_rejects_prefix=a,b_rejects_prefix=b,label='scoped_legal_prefix' if o['legal_prefix'] else 'first_target_violation',
                                conclusion=('A false-positive; B accepts this prefix' if a else 'B false-positive; A accepts this prefix') if o['legal_prefix'] else ('B misses this prefix; A alarm attribution still unknown' if a else 'A misses this prefix; B alarm attribution still unknown')))
                            break
            output.append(dict(pair_id=p['pair_id'],case=k,method=method,a=p['a'],b=p['b'],focused_11=p['status']=='distinguished_on_checked_legal_inputs',
                distinguished=bool(witnesses),witnesses=witnesses,quality_order='not_established',
                reason='Whole-prefix local decisions only; both candidates can have other defects; no positive credit from unconfirmed alarm attribution',
                spec_scope='common validity obligation only' if k=='spill' else 'unknown' if k=='intr' else 'scoped resolved target'))
    x.dump(x.OUT/'search/verified_pair_results.json',output)
    return output


def screening():
    folder=x.OUT/'historical_screening';p=folder/'windows_retry_ibex.jsonl'
    if not p.exists():return
    rows=[json.loads(s) for s in p.read_text().splitlines()]
    ranked=sorted(rows,key=lambda r:(r.get('lines_added',0)+r.get('lines_removed',0),r['number']))
    results=[]
    for r in ranked:
        result=dict(case_id=f"{r['org']}/{r['repo']}#{r['number']}",source=r['html_url'],title=r['title'],
            base_commit=r['base']['sha'],merge_commit=r['merge_commit_sha'],fix_commits=[z.get('sha') for z in r.get('commits',[])],
            intent=r['problem_statement'],benchmark_reported_result=r.get('run_result'),
            status='deferred',reason='No local Docker or Verilator; original benchmark test not run on either revision; reported benchmark pass is not this study reproduction',
            before='not_executed',after='not_executed',admitted=False,generator_visible=False)
        if len(results)<3:
            dest=folder/('ibex_'+str(r['number']));dest.mkdir(exist_ok=True)
            for name,field in [('fix.patch','fix_patch'),('test.patch','test_patch'),('tb_script.sh','tb_script'),('prepare_script.sh','prepare_script')]:
                value=r.get(field,'');(dest/name).write_text(value if isinstance(value,str) else json.dumps(value,indent=2))
            x.dump(dest/'source.json',result);result['archived_reproducer']=x.rel(dest)
        results.append(result)
    x.dump(folder/'screening_complete.json',dict(source_dataset='https://huggingface.co/datasets/henryen/hwe-bench',sha256=x.sha(p),
        download_attempts=[dict(environment='WSL',status='network_unreachable',record='result.json'),dict(environment='Windows',status='success',file=p.name)],
        metadata_rows=len(rows),shortlist_size=3,admitted=0,rows=results))


def finalize():
    x.guard();obligations();screening()
    qs=[json.loads(s) for s in (x.OUT/'search/queries.jsonl').read_text().splitlines()]
    pairs=verify_pairs(qs)
    checks=[]
    protocol=x.read(x.OUT/'protocol.json')
    for k in x.IDS:
        for seed in protocol['seeds']:
            for method in protocol['methods']:
                qq=[q for q in qs if (q['case'],q['seed'],q['method'])==(k,seed,method)]
                checks.append(dict(kind='exact_attempted_query_budget',case=k,seed=seed,method=method,passed=len(qq)==12 and sorted(q['step'] for q in qq)==list(range(12))))
    checks.append(dict(kind='unique_query_ids',passed=len(set(q['query_id'] for q in qs))==len(qs)))
    snapshots=x.read(x.OUT/'source_manifest.json')
    checks.append(dict(kind='source_snapshot_hashes',passed=all(x.sha(x.ROOT/e['source'])==x.sha(x.ROOT/e['snapshot'])==e['sha256'] for e in snapshots)))
    # Every physical compile/sim is accounted, including failed batched candidates.
    for q in qs:
        checks.append(dict(kind='query_cost_recount',query=q['query_id'],passed=q['compile_attempts']==len(q['runs']) and q['attempted_queries']==1 and q['cache_hits']==q['retries']==q['solver_calls']==q['model_calls']==0))
    seedrows=[];curves=[]
    for k in x.IDS:
        for seed in protocol['seeds']:
            for method in protocol['methods']:
                rows=sorted([q for q in qs if (q['case'],q['seed'],q['method'])==(k,seed,method)],key=lambda q:q['step'])
                gaps=set();seconds=0;raw=0;uniq=set()
                for q in rows:
                    seconds+=q['wall_seconds'];raw+=len(q['evidence']);uniq|={e['evidence_id'] for e in q['evidence']}
                    for e in q['evidence']:
                        if e['kind']=='false_positive':gaps.add((e['candidate_id'],'false_positive','legal_prefix'))
                        else:
                            gaps|={(e['candidate_id'],'miss',c['obligation']) for c in e['obligations'] if not c['passed'] and not c['conditional']}
                    curves.append(dict(case=k,seed=seed,method=method,attempted_queries=q['step']+1,wall_seconds=seconds,
                        gaps=len(gaps),raw_evidence=raw,unique_evidence=len(uniq)))
                seedrows.append(dict(case=k,seed=seed,method=method,gaps=sorted(gaps),gap_count=len(gaps),seconds=seconds,
                    eligible_main=k in ['onehot','fifo','stat'],conditional_spill=k=='spill',supplementary_filter=k=='filter'))
    x.dump(x.OUT/'search/strict_seed_results.json',seedrows)
    x.dump(x.OUT/'search/resource_curves.json',curves)
    with (x.OUT/'search/resource_curves.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(curves[0]));w.writeheader();w.writerows(curves)
    delta=[]
    for k in x.IDS:
        for seed in protocol['seeds']:
            dd={r['method']:r for r in seedrows if r['case']==k and r['seed']==seed}
            g=set(map(tuple,dd['obligation']['gaps']))
            for other in ['ordinary','disagreement']:
                b=set(map(tuple,dd[other]['gaps']))
                delta.append(dict(case=k,seed=seed,comparator=other,guided_only=sorted(g-b),comparator_only=sorted(b-g),
                    guided_count=len(g),comparator_count=len(b),net=len(g)-len(b),budget=12,
                    scope='unknown_execution' if k=='filter' else 'unknown_spec' if k=='intr' else 'common_spill_obligation' if k=='spill' else 'natural_resolved_target'))
    x.dump(x.OUT/'search/paired_gain.json',delta)
    dumpchecks=dict(passed=all(r['passed'] for r in checks),checks=checks,cpu_seconds=None,cpu_measurement_status='not_instrumented; per-command and query wall time recorded',
        source_hash_count=len(snapshots),heldout_evaluated=False,initial_audit_correction='160 final runs: 151 exact successful replays plus 9 separately preserved unsupported executions')
    x.dump(x.OUT/'audit.json',dumpchecks)
    assert dumpchecks['passed']
    baseline=x.read(x.OUT/'baseline/omitted_unknowns/summary.json');legacy=x.read(x.OUT/'legacy_replay/corrected_feedback_summary.json')
    parent=x.read(x.OUT/'parent_accounting.json');summaries=x.read(x.OUT/'search/parent_method_results.json')
    lines=['# 本轮交付与结论（2026-10-13）','', '**第1项已完成本轮有限范围复核；第2项已实际运行，未证明义务指导整体优于对照。第3、4项状态见下文。**', '',
        '本文件是最终入口。REPORT.md 保留初始汇总，问题台账以 problem_ledger_complete.json 为准；候选对以 search/verified_pair_results.json 为准。初次遗漏未知运行、初次 TP 计算遗漏 fixed-safe 门控的诊断均原样保留，修正不删除历史结果。', '',
        '## 第1项：原始统计和真实复现','',
        '六个独立父案例 × 八种旧方法 = 48 个单元：8 个有限通过、23 个已知失败、17 个未知。8 个通过均来自 onehot。11 对是早期 25 对中的已区分自然候选子集；25 对含21对自然候选及4对人工控制，不是 v3 40 个问题单元的配对。', '',
        '| 父案例 | 通过单元 | 已知失败 | 未知 |','|---|---:|---:|---:|']
    for p in parent:lines.append(f"| {p['case']} | {p['pass_cells']} | {p['failed_cells']} | {p['unknown_cells']} |")
    lines+=['',f"最终相关160条原运行已核验：151条成功运行重编译后 TRACE/CHECK 全同，另9条 unsupported_syntax 原样复现。40条问题记录全部保留原状态；23条有独立前缀缺陷证据，17条完整合约仍未知。11组 checker 测试664条检查通过，独立规格监视器另有手写轨迹测试。",'',
        'stat 的 fixed RTL 在连续不同长度事务上也违约，因此 fixed 标签不能替代合法性判定。独立事件队列捕获触发长度、追踪触发/到期和复位 epoch；合法误报要求整个复位后前缀合规。偶合报警不计独立命中。', '',
        '原生 SVA 能力探针失败（Icarus 12.0）；本轮是过程 checker + 独立 Python 规格监视器，不能称为原生 SVA 或形式证明。spill invalid data 和 intr 采样按用户答复继续未知。', '',
        '## 第2项：冻结候选后的等预算比较','',
        f"旧配置896次编译/仿真全部复现原始计数，按原反馈定义 {legacy['original_signature_reproduced']}/11 对再次同签名。普通自然候选也保留：五个旧池父案例各7条；filter是另外3条v2自然候选，单列。候选全文、原SVA、哈希、配置均冻结。",'',
        f"三方法×六父案例×三种子×12次查询 = {len(qs)} 次实际尝试，{sum(q['compile_attempts'] for q in qs)}次编译，{sum(q['simulation_attempts'] for q in qs)}次仿真启动。无重试/缓存/求解器；失败查询收费。每次查询对双RTL批量检查同一冻结池。",'',
        '| 父案例 | 普通/分歧/义务：累计候选缺口 | 三方法区分焦点候选对 | 范围 |','|---|---|---|']
    for k in x.IDS:
        sets={m:set(g for r in seedrows if r['case']==k and r['method']==m for g in map(tuple,r['gaps'])) for m in protocol['methods']}
        counts=[len(sets[m]) for m in protocol['methods']]
        paircounts=[sum(r['distinguished'] for r in pairs if r['case']==k and r['method']==m and r['focused_11']) for m in protocol['methods']]
        scope='批量语法失败，效果未知' if k=='filter' else '规格未知，不计收益' if k=='intr' else '只含明确valid清空义务' if k=='spill' else '旧自然候选、目标范围'
        lines.append(f"| {k} | {' / '.join(map(str,counts))} | {' / '.join(map(str,paircounts))} | {scope} |")
    lines+=['', '缺口按候选×误报/漏报×义务去重；不是父bug独立样本。逐种子成对差集见 search/paired_gain.json，按查询数和秒数的发现曲线见 search/resource_curves.csv。完整原始/去重证据量及成本见 REPORT.md 和 search/queries.jsonl。', '',
        '旧二值反馈漏掉了合法前缀接受集合、首次目标违例前缀的漏报，以及捕获数据/事务归属等区别。新证据先由规格监视器裁定，再比较候选；不把候选分歧本身作为答案。双方均可能有缺陷，因此只报告见证范围内的取舍，不给出全局优劣。', '',
        'filter的两个不支持表达式会阻塞整批编译，108次查询均已计费并标未知。它没有旧11对候选，未并入主结果；需要隔离编译后开展独立实验区块，不能靠改写本轮失败记录制造提升。', '',
        '## 复现与当前卡点','',
        '最小复现索引：minimal/index.json（如已生成）；每个条目含实际RTL重跑、单样本删除最小性范围和全部失败尝试。问题台账包含全部原运行、候选内容、哈希、规格位置、逐周期定位、置信和缺失证据。',
        '第3项新模型A/B/C/D：本搜索运行未执行，旧八臂不冒充新四臂。model_access.json/model_probe 保存实际可用性探测。',
        '第4项：搜索前已隔离三组/父案例的新场景并封存哈希；本轮未细化断言，因此未以其声明独立改善。旧v3保留场景已用于诊断，均视作已见开发资料。',
        '真实历史：已筛选 HWE-Bench ibex 35条元数据并保存3例补丁、原测试脚本、修复前后commit及来源；本环境缺 Docker/Verilator，尚未复现前失败/后通过，入选数0。WSL下载失败与Windows重试均保留。来源：https://github.com/pku-liang/hwe-bench 。六个人工父案例不标为历史bug。', '',
        '重建：python3 scripts/run_obligation_evidence.py --run obligation_evidence_20261013_r01 report；python3 scripts/finalize_obligation_evidence.py --run obligation_evidence_20261013_r01。新实验使用新的 --run，依次 prepare、baseline、search、report；补充审计命令见各脚本。所有 simulate/compile 命令均写入对应目录。',
        '保存的wall time为实际执行时间；CPU秒数和服务缓存开销不可得，未记为零。此小样本、三个种子和有限查询只支持本范围结论。']
    (x.OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(audit_pass=True,queries=len(qs),source_files_preserved=len(snapshots),final_report=x.rel(x.OUT/'README.md'))))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);a=ap.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;finalize()
