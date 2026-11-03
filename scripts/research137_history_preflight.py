"""Read-only prepared-protocol audit plus explicitly local rollback fixtures."""
import argparse
import json
from pathlib import Path
import research136_prospective_history as p

ROOT,read,dump,digest,rel=p.ROOT,p.read,p.dump,p.digest,p.rel


def run(prep,out):
    opened=p.q.guard();p.verify(prep)
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,yes):
        assert yes,name
        checks.append(name)
    q=p.QUAL
    for name,h in read(q/'source_bindings.json').items():check('qualification_source/'+name,digest(ROOT/name)==h)
    req=read(prep/'request.preview.json');body=json.loads(req['messages'][1]['content'])
    check('exact_shared_requests',req==read(prep/'arms/O/request.preview.json')==read(prep/'arms/H/request.preview.json'))
    check('only_public_feedback',set(body['actual_feedback']['visible_counts'])=={'alignment','search'})
    check('no_old_immutable_contract',not any(t in json.dumps(req) for t in ('replace_op','immutable','copied unchanged','fixed BRANCH')))
    check('full_set_model_output_contract','operation=replace;' in body['output_contract'])
    check('no_fixture_or_private_target_table',not any(t in json.dumps(req) for t in ('local_history_loss','local_positive','target_preservation.private','focus.private')))
    first_ids={pair['selected_evidence_id'] for pair in body['actual_feedback']['paired_sample_table']}
    public_records=[read(q/f'native_controls/baseline/native/{k}/result.json') for k in ('alignment','search')]
    check('actual_selected_ids_public',first_ids<={row['evidence_id'] for rec in public_records for row in rec['ledger']})
    initial=read(prep/'initial.json');negative=read(q/'native_controls/local_history_loss/candidate.json')
    local=read(q/'fixture_results.private.json')
    check('ordinary_not_weakened',local['local_history_loss']['decisions']=={'O':True,'H':False})
    check('old_detection_loss_is_real',local['local_history_loss']['lost_detections']==141)
    check('healthy_positive_control',local['local_positive']['decisions']=={'O':True,'H':True})
    # Explicitly labeled local fixture only; no new generation claim.
    accepted=p.x.journal(out/'local_rollback_fixture/O',initial,negative,True,dict(local_fixture=True,rule='O'))
    rejected=p.x.journal(out/'local_rollback_fixture/H',initial,negative,False,dict(local_fixture=True,rule='H',lost_detections=141))
    check('durable_ordinary_transition',accepted==negative and read(out/'local_rollback_fixture/O/active.json')==negative)
    check('durable_history_rollback',rejected==initial and read(out/'local_rollback_fixture/H/active.json')==initial)
    check('fallback_original_270',local['baseline']['retained_detections']==270)
    check('baseline_remains_partial',not local['baseline']['decisions']['O'] and not local['baseline']['decisions']['H'])
    entries=read(prep/'candidate_matrix.json')
    check('all_locked_candidates_accounted',len(entries)==16 and len([v for v in entries if v['eligible']])==3)
    check('first_eligible_selection',read(prep/'selection.json')['selected']==next(v['id'] for v in entries if v['eligible']))
    check('excluded_have_reason',all(v['exclusion_reasons'] for v in entries if not v['eligible']))
    controller=p.controller_tests(req)
    check('controller_recomputed',controller==read(prep/'controller_checks.json'))
    # Physical cost paths: inline native benches execute their cohort once.
    # Legacy extractor also calls the SAME execution a compile smoke run.
    compile_files=sorted((q/'native_controls').rglob('compile.json'))
    execute_files=sorted((q/'native_controls').rglob('execute.json'))
    check('physical_native_cost',len(compile_files)==18 and len(execute_files)==18)
    for f in compile_files+execute_files:check('native_command/'+rel(f),read(f)['exit_code']==0)
    cost=dict(model_calls=0,formal_calls=0,native_compiles=18,total_physical_simulator_executions=18,
        compile_wall_seconds=sum(read(f)['wall_seconds'] for f in compile_files),
        execute_wall_seconds=sum(read(f)['wall_seconds'] for f in execute_files),
        note='Inline Ibex stimulus is run once per build. Legacy native_execute_calls=18 and compile_smoke_execute_calls=18 reference the same18 execute.json paths; never sum to36.')
    dump(out/'cost_physical.json',cost)
    dump(out/'checks.json',checks);dump(out/'read_audit.json',sorted(opened))
    dump(out/'audit.json',dict(passed=True,checks=len(checks),controller_checks=len(controller),
        raw_development_rows_reaudited=read(q/'outcome.json')['native_development_rows_reaudited'],
        candidate_count=16,eligible_ibex_candidates=3,model_calls=0,new_real_proposals=0,
        actual_extra_rejections=None,actual_recoveries=None,new_independent_tests=0,
        local_fixture_only=True,research133_read=False,prepared_seal=digest(prep/'sealed.json')))
    lines=['# research135–137：可编辑历史保护的前瞻先导资格与封存','',
        '本地资格成立，research136协议与首轮真实请求预览已封存。尚未调用模型，尚无新提案、实际额外拒绝、恢复或新独立验收。',
        '候选总体事先限定：既有research117的全部9个FIFO候选，以及research87–123 real运行中的全部去重Ibex model_call候选加原共享基线。不是全仓库或随机总体。7个Ibex中3个合格；9个FIFO因为父案例/接口不同暂缓，不等于质量不合格。', '',
        '|候选|合格|已有确认检出|公共漏报|排除/暂缓原因|','|---|---|---:|---:|---|']
    for e in entries:
        d=e['development'] if isinstance(e['development'],dict) else {}
        lines.append(f'|{e["id"]}|{e["eligible"]}|{d.get("existing_detections","未在本轮判定")}|{d.get("public_misses","未在本轮判定")}|{", ".join(e["exclusion_reasons"]) or "符合资格；按固定顺序选第一个"}|')
    lines+=['','选中i00，即原共享Ibex #166部分基线；已有270个BRANCH检出，420个OP点仍未保护。按锁定的基线优先、来源顺序选取，未依据O/H差值或旧独立结果选择。',
        'BRANCH与OP谓词均可由模型修改。复用原始research51全集合文本渲染器及原生151事务验收；保留a0/OP槽位标签仅为现有采样检查器绑定，不固定任何谓词。公共接口变化本身不计创新收益。',
        '|本地原生资格对象|普通O|完整历史H|丢失原检出|新增合法误报|','|---|---|---|---:|---:|',
        '|原基线|拒绝|拒绝|0|0|','|正对照夹具|接受|接受|0|0|','|历史退化夹具|接受|拒绝|141|0|',
        '上述对照是明确的本地夹具，非真实模型成功结果，绝不发送模型。退化夹具仅证明相同普通规则允许、历史规则能额外拒绝的保护损失确实可表达；不保证下一次真实提案会出现。拒绝回退的持久化本地检查保留原270检出基线，仍不是完整案例通过。',
        '两规则公共生成、当前9事务、搜索36事务、原生触发/合法性标准一致。H增加完整151检查和自身拒绝诊断；H/R等价结论保留，不设置第三组来制造独有收益。',
        '封存预算：共享新提案1次；仅O接受、H拒绝、关键unknown为0且确认新增误报或旧检出丢失，才允许H恢复1次。若仅历史旧缺口未补齐而无实际退化，则停止。每轨迹上限2次，实际物理上限2次，无重试、不转额度、不扩种子。O接受即停；报告实际成本不一致。',
        '仅恢复通过完整接受后，两组终态先冻结，再生成96个新指令、四配置的独立测试；排除所有旧输入，仅终态后读取旧独立输入整数作碰撞排除，绝不读取结果或反馈给模型。research133 FIFO独立数据不读取、不使用。',
        f'本轮复核38124条原生开发记录；18次新编译、18次实际仿真、模型0、形式化0。协议/来源/回退检查{len(checks)}项，分支预算检查{len(controller)}项。旧工具把同一个内嵌bench执行同时标为execute和smoke，本报告按物理路径去重。',
        '搜索机制：本轮未执行搜索收益实验，也不更改research125负结果。未获得新前瞻真实提案前，不能报告防退化增量成立或恢复率。',
        '', '只读核验：','```powershell',f'wsl -- python3 scripts/research136_prospective_history.py verify --prepared {rel(prep)}','```',
        '新的模型预算须在本封存后明确授权；旧用途额度不转用。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'source_bindings.json',{rel(f):digest(f) for f in [Path(__file__),prep/'sealed.json',q/'sealed.json',q/'outcome.json',q/'fixture_results.private.json']})
    p.verify(prep)
    print('PREFLIGHT137',len(checks),'checks +',len(controller),'controller; model0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve())
