"""Read-only model provenance, native evidence and paired decision audit."""
import argparse
import time
from collections import Counter
from pathlib import Path
import research73_discriminating as run
import research68_result_audit as native
import research28_report as model
import research32_model as text_interface
from research17_report import cost_audit

b, read, dump, ROOT = run.b, run.read, run.dump, run.ROOT


def audit(root, out):
    out.mkdir(parents=True, exist_ok=False)
    checks=[]
    def check(name, value):
        assert value, name
        checks.append(name)
    for name,h in read(root/'sealed.json').items(): check('sealed '+name,b.search.digest(root/name)==h)
    initial=read(root/'initial.json');cases=read(root/'cases.json');history=read(root/'history_cases.json')
    before=read(root/'baseline_public/result.json');historical=read(root/'baseline_history/result.json')
    check('public baseline has valid native execution', before['healthy'])
    start=time.perf_counter(); raw=0; results=[]; qualified=[]
    with b.extension.installed():
        raw+=native.raw_replay(root/'baseline_public',cases,initial,checks)
        raw+=native.raw_replay(root/'baseline_history',history,initial,checks)
        hi=b.loop.inspect(historical['group']['ledger'])
        dump(out/'baseline_mapping.json',hi['mapping'])
        for index,item in enumerate(read(root/'inventory.json')):
            folder=root/f'c{index:02d}';candidate=read(folder/'candidate.json');source=ROOT/item['path']
            check(f'c{index} source bytes',b.search.digest(source)==item['candidate_sha256'])
            edit=read(source.parent/'model_edit.json')
            check(f'c{index} real upstream response',model.raw_response(source.parent,edit))
            assembler=text_interface.assemble if edit['assertions'] and isinstance(edit['assertions'][0].get('antecedent'),str) else b.interface.assemble
            rendered=assembler(edit,initial)
            check(f'c{index} exact executable rendering',b.interface.executable_hash(rendered)==b.interface.executable_hash(candidate))
            check(f'c{index} candidate unmodified',candidate==read(source))
            raw+=native.raw_replay(folder/'public',cases,candidate,checks)
            small=read(folder/'public/result.json');plain=b.paired.current_decision(before,small,edit)
            saved=read(folder/'decision.json');check(f'c{index} ordinary decision',plain==saved['ordinary'])
            metrics=dict(index=index,source=item['path'],ordinary_pass=plain['accepted'],
                         public=small.get('counts'),historical=None,regressions={},extra_rejection=False)
            if plain['accepted']:
                raw+=native.raw_replay(folder/'history',history,candidate,checks)
                full=read(folder/'history/result.json');fi=b.loop.inspect(full['group']['ledger'])
                decision=run.policy.decision_for(plain,full,historical,True)
                check(f'c{index} historical decision',decision==saved['full'])
                transition=read(folder/'transition/active_transition.json')
                active=read(folder/'transition/active_candidate.json')
                check(f'c{index} durable retained version',active==(candidate if decision['accepted'] else initial))
                check(f'c{index} durable hash',transition['active_hash']==b.loop.sha(active))
                regressions={
                    'confirmed_lost_detection':sorted(hi['detections'] & fi['misses']),
                    'unconfirmed_detection_loss':sorted((hi['detections']-fi['detections'])-fi['misses']),
                    'new_legal_false_positive':sorted(fi['false_positives']-hi['false_positives']),
                    'lost_required_trigger':sorted({key for reason in decision['historical']['reasons'] if reason['kind']=='lost_obligation_trigger' for key in reason['evidence_keys']})}
                metrics.update(historical=full['counts'],regressions={k:len(v) for k,v in regressions.items()},
                               extra_rejection=not decision['accepted'])
                evidence=[]
                for kind,keys in regressions.items():
                    for key in keys:
                        left=hi['rows'][key];right=fi['rows'][key]
                        evidence.append(dict(kind=kind,key=key,obligation=right['obligation'],mechanism=right['variant'],
                            before=left,after=right))
                mechanism_keys=sorted({(e['kind'],e['obligation'],e['mechanism']) for e in evidence})
                dump(out/f'c{index:02d}_evidence.json',dict(regressions=regressions,mechanism_keys=mechanism_keys,evidence=evidence,
                    mapping=fi['mapping'],state_transition=transition,
                    scope='Fresh paired replay of archived model proposal. New journal verifies present retention, not historical rollback.'))
                if metrics['extra_rejection']:
                    qualified.append(dict(index=index,source=item['path'],mechanisms=mechanism_keys,
                        confirmed_loss=bool(regressions['confirmed_lost_detection']),
                        new_legal_failure=bool(regressions['new_legal_false_positive'])))
            results.append(metrics)
    # Exhaustively pair each qualifying regression with every public+history
    # passing archived proposal. These are reachability controls, not a causal
    # continuation, and none of their predicates may enter new model prompts.
    recoveries=[]
    for q in qualified:
        evidence=read(out/f"c{q['index']:02d}_evidence.json")
        for r in results:
            if not r['ordinary_pass'] or r['extra_rejection']:continue
            fi=b.loop.inspect(read(root/f"c{r['index']:02d}/history/result.json")['group']['ledger'])
            keys=evidence['regressions']['confirmed_lost_detection']
            fp=evidence['regressions']['new_legal_false_positive']
            restored=[k for k in keys if k in fi['detections']]
            cleared=[k for k in fp if k not in fi['false_positives'] and k not in fi['unknown']]
            check(f"c{q['index']} -> c{r['index']} archived restoration",len(restored)==len(keys) and len(cleared)==len(fp))
            recoveries.append(dict(failed=q['index'],restored=r['index'],source=r['source'],
                confirmed_lost_points=len(keys),restored_points=len(restored),legal_alarms_cleared=len(cleared),
                public=r['public'],historical=r['historical'],
                label='Archived real-model restoration availability; NOT new generation, same-budget recovery, or historical causal follow-up.'))
    dump(out/'restoration_controls.json',recoveries)
    check('protected independent results byte-identical',run.protected()==read(root/'protected.json'))
    elapsed=time.perf_counter()-start
    files=b.paired.files(root)
    cost=cost_audit(root,files);dump(out/'cost.json',cost)
    dump(out/'results.json',results);dump(out/'qualified.json',qualified)
    dump(out/'audit.json',dict(passed=True,checks=checks,raw_native_records=raw,
        reference_recomputations=raw,raw_recheck_wall_seconds=elapsed,
        source_hash=b.search.digest(Path(__file__)),model_calls=0,
        separate_runtime_oracle_seconds=None,scope='Retrospective development qualification, not new controlled efficacy or restoration.'))
    lines=['# research73：可区分历史门控的真实候选筛选','',
        '固定已有14个公共场景及普通接受规则，筛选9套不重复的历史真实模型提案；普通通过后再执行完整105历史回放。未使用独立测试选择候选或调整规则。',
        '', '|候选|普通通过|历史额外拒绝|确认丢失检出|新增合法误报|必检触发丢失|', '|---|---|---|---:|---:|---:|']
    for r in results:
        g=r['regressions'];lines.append(f"|c{r['index']:02d}|{r['ordinary_pass']}|{r['extra_rejection']}|{g.get('confirmed_lost_detection','未执行')}|{g.get('new_legal_false_positive','未执行')}|{g.get('lost_required_trigger','未执行')}|")
    lines += ['',f"普通通过 {sum(r['ordinary_pass'] for r in results)}/{len(results)}；历史额外拒绝 {len(qualified)}。回顾性筛选不能作为新随机实验的机制收益估计。",
        '', '每个真实提案均核对上游原始响应、模型编辑的程序渲染以及原生采样、独立事务判定、触发和失败日志。旧性质原样执行，无人工改写。',
        '', '退化点按原因/义务/人工故障机制归组；采样点数量不是独立缺陷数。unknown单列，不把未知检出丢失当作确认漏报。回放结论仅限有限开发数据和人工故障。',
        '', '拒绝后当前运行写入持久版本记录，保留基线；这验证当前回放的状态行为，不补造旧实验回滚历史。基线部分有效，不声称完整保护。',
        '', '本轮没有新模型调用，未完成统一预算内拒绝后自动恢复。已知成功提案只能作回顾性可达性对照，不能充当下一轮模型响应。',
        '', f"原始日志复核 {raw} 份；审计检查 {len(checks)} 项通过。实际成本：{cost['total']}。参考判定随原生执行完成，单独耗时不可用；复核耗时 {elapsed:.3f} 秒。",
        '', 'research72 与 research63 的受保护JSON哈希保持不变；未读取独立结果用于候选筛选，没有新独立测试通过声明。',
        '', '复核命令（新输出目录）：','```powershell',
        f'wsl -- python3 scripts/research73_result_audit.py --run {root.relative_to(ROOT).as_posix()} --out deliverables/research73_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 回顾性真实提案：普通接受与历史拒绝','',
        '候选来自既有真实模型原始响应，本次原样重新执行。不是新随机化实验；恢复对照不进入新的细化请求。']
    for q in qualified:
        index=q['index'];candidate=read(root/f'c{index:02d}/candidate.json')
        trace+=['',f'## c{index:02d}：{q["source"]}','', '```systemverilog']
        trace += [a['id']+': '+a['property'] for a in candidate['assertions']]
        trace+=['```', '普通范围固定为14个公共场景；完整历史为105场景。普通通过后增加历史检查才拒绝，旧规则没有放宽。',
            '',str(next(r for r in results if r['index']==index)),
            '', '基线原生历史214个目标检出，误报/漏报/关键unknown为0；拒绝后active版本哈希与基线相同。仍有1177条后续归因unknown，范围不扩大。']
        evidence=read(out/f'c{index:02d}_evidence.json')
        for kind in ('confirmed_lost_detection','new_legal_false_positive'):
            samples=[e for e in evidence['evidence'] if e['kind']==kind]
            if samples:
                e=samples[0]
                trace+=['',f"代表证据 {kind}：{e['key']}；义务 {e['obligation']}；故障机制 {e['mechanism']}。",f"采样周期 {e['after']['cycle']}；原始回放路径 {e['after']['source_directory']}。"]
    trace+=['','## 归档恢复对照','',
        '对所有普通和历史检查均通过的归档提案做配对回放比对；没有从独立结果选择恢复版本。']
    for r in recoveries:
        trace+=['',f"c{r['failed']:02d} → c{r['restored']:02d}：确认漏报恢复{r['restored_points']}/{r['confirmed_lost_points']}，合法误报消除{r['legal_alarms_cleared']}。来源 {r['source']}。"]
    trace+=['', '这些结果只证明已有真实模型性质能够在相同开发记录上恢复保护，未证明本次拒绝反馈会促成修复。新的有界真实继续细化尚待执行；旧成功性质不得送入请求。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    print('AUDITED',len(checks),'checks',raw,'native records','qualified',len(qualified),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
