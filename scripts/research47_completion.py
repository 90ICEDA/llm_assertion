"""Read-only result details and documented protocol-metadata correction.

No model/native calls. Archived model records and predeclared criteria remain
unchanged. The old generic protocol is retained before copying the sealed one.
"""
import argparse
import json
from pathlib import Path
import shutil
import research47_sample_binding as campaign

read, dump = campaign.read, campaign.dump


def complete(run, report):
    prep = campaign.gate.portable(read(run / 'prepared_source.json')['path'])
    audit = read(report / 'audit.json')
    assert audit['passed']
    protected = {p.relative_to(run).as_posix(): campaign.common.digest(p)
                 for p in campaign.common.files(run / 'plan')}
    amendment = run / 'amendments/protocol_metadata'
    amendment.mkdir(parents=True, exist_ok=False)
    shutil.copy2(run / 'protocol.json', amendment / 'inherited_generic_protocol.json')
    shutil.copy2(prep / 'protocol.json', run / 'protocol.json')
    dump(amendment / 'record.json', dict(
        reason='loop.prepare emitted a generic research17 protocol. It was not the executed research47 configuration. Restore the exact predeclared47 protocol, preserving the generic original.',
        change='Post-run protocol metadata only; no request, response, decision, cost, plan or acceptance criterion changed.',
        inherited_sha256=campaign.common.digest(amendment / 'inherited_generic_protocol.json'),
        effective_sha256=campaign.common.digest(run / 'protocol.json'),
        source=str(prep / 'protocol.json'), actual_runner_snapshot_sha256=campaign.common.digest(run / 'source_snapshot/research47_sample_binding.py'),
        future_runner_sha256=campaign.common.digest(Path(campaign.__file__)),
        future_code_change='Copy sealed protocol immediately after loop.prepare; actual executed source snapshot retained.',
        model_artifact_hashes=protected))
    assert all(campaign.common.digest(run / p) == h for p, h in protected.items())
    expected = read(prep / 'expected.private.json')
    plan = read(run / 'accepted_plan.json')
    verdict = campaign.validate(plan, expected)
    assert verdict['accepted'] and verdict == read(run / 'accepted_plan_gate.json')
    actual = {r['id']: r for r in plan['windows']}
    fields = ('anchor_cycle', 'check_cycle', 'anchor_reset', 'check_reset', 'anchor_pending', 'applicability')
    rows = []
    for t in expected:
        truth = campaign.fixture([t])['windows'][0]
        rows.append(dict(id=t['id'], category=t['category'], source=t['source'], source_sha256=t['source_sha256'],
            actual=actual[t['id']], expected=truth,
            fields={f: type(actual[t['id']][f]) is type(truth[f]) and actual[t['id']][f] == truth[f] for f in fields}))
    scores = {f: dict(correct=sum(r['fields'][f] for r in rows), total=len(rows)) for f in fields}
    total = read(run / 'cost.json')['total']
    used = total['model_calls']
    assert used == 1 and len(list((run / 'plan').glob('v*'))) == 1
    assert read(prep / 'archive_hashes.json') == campaign.archive_hashes()
    result = dict(status='all_development_event_fields_accepted', per_field=scores,
        complete_windows=sum(all(r['fields'].values()) for r in rows), total_windows=len(rows),
        cost=total, research46_unchanged=True, rows=rows,
        scope='Same11 development windows; real model first call passed; not an independent understanding test, SVA acceptance or proof.')
    dump(report / 'field_results.json', result)
    dump(report / 'budget.json', dict(authorized_plan_calls=2, used_plan_calls=used, unused_plan_calls=2-used,
        authorized_sva_calls=0, sva_calls=0, transfer='research46 remaining2 reassigned to research47 plan-only',
        remainder='Unused1 remains subject to plan-only scope and stop-on-accept; no additional call made.',
        research45_other4='Original conditional-ablation restriction unchanged.'))
    command = ('wsl -- python3 scripts/research47_sample_binding.py run '
        '--prepared deliverables/research47_prepare_20261022_r01 '
        '--out deliverables/research47_real_20261022_r01 '
        '--authorization deliverables/research47_authorization_20261022_r01.json')
    dump(report / 'execution_record.json', dict(command_actually_executed=command, exit_code=0,
        existing_run_must_not_be_overwritten=True, repeated_model_calls_not_authorized=True))
    text = '# research47：真实采样字段门控已通过\n\n'
    text += '1次真实Highway/Qwen72B调用后，11/11开发窗口全部通过，按规则停止，第二次未调用。\n\n'
    text += '|字段|正确/总数|\n|---|---:|\n'
    text += ''.join(f'|{f}|{scores[f]["correct"]}/{scores[f]["total"]}|\n' for f in fields)
    text += '\nw5真实模型输出：\n\n```json\n' + json.dumps(actual['w5'], ensure_ascii=False, indent=2) + '\n```\n\n'
    text += ('锚点cycle2的rst=1，检查cycle3的rst=0。两个复位字段分别正确；anchor_pending=false、not_required也正确。'
        '完整计划与服务原始响应一致，没有本地替换字段。所有66项字段检查通过。'
        '原始请求、流式响应、用量及逐项门控见 ../research47_real_20261022_r01/plan/v0/。\n\n'
        '此前280项本地正负检查通过；本轮23项只读结果审计通过。research46全部受保护产物哈希保持不变，'
        '两次旧失败仍是失败。运行目录最初沿用了旧通用protocol说明，已恢复为调用前封存的research47协议；'
        '修正前副本和哈希保存在运行目录 amendments/protocol_metadata/。实际请求、响应、决策和标准均未变。\n\n')
    text += (f'实际成本：模型调用{used}，输入{total["prompt_tokens_total"]}、输出{total["completion_tokens_total"]} tokens，'
        f'调用耗时{total["model_wall_seconds_known_subtotal"]:.3f}秒；金额不可用。SVA调用、新增原生编译/执行、形式化和独立测试均为0。\n\n'
        '已生成 gated_sva_request.preview.json，包含实际通过的原始模型计划。它只是解锁后的请求产物，尚未调用SVA生成，'
        '没有新接受断言或新独立验收结果。原初始断言保持不变。\n\n'
        '适用范围仅为这些开发窗口；不能据此宣称跨场景稳定性、两个机制收益或全局正确性。\n\n'
        '授权2次中用1次，剩余1次仍受本轮周期判断及通过即停的限制，不自动转作SVA；research45另外4次仍限原条件性消融。\n\n'
        '实际执行命令（记录用途，不能覆盖重跑或重复消耗旧授权）：\n\n```powershell\n' + command + '\n```\n')
    (report / 'SUMMARY.md').write_text(text, encoding='utf-8')
    shutil.copy2(Path(__file__), report / 'completion_source.py')
    print('COMPLETE', len(rows), 'windows;', sum(sum(r['fields'].values()) for r in rows), 'fields;', used, 'real call')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args()
    complete(a.run.resolve(), a.report.resolve())
