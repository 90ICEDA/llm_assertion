"""Aggregate observed qualification and blocked continuation, no model calls."""
import argparse
from pathlib import Path
import research17_loop as loop
from research34_campaign import digest


def report(out):
    out.mkdir(parents=True,exist_ok=False)
    q=loop.ROOT/'deliverables/research39_qualification_20261022_r01'
    p=loop.ROOT/'deliverables/research39_local_probe_20261022_r01'
    prep=loop.ROOT/'deliverables/research39_prepare_20261022_r01'
    checks=loop.read(q/'verification.json')
    probe=loop.read(p/'qualification.json')
    transport=loop.read(p/'model_call/transport_result.json')
    raw=loop.read(p/'model_call/response.raw.json')
    done=raw['service_done']
    events=[__import__('json').loads(line) for line in (p/'model_call/response.stream.jsonl').read_text().splitlines()]
    assert ''.join(e.get('message',{}).get('content','') for e in events)==raw['message']['content']
    assert done['done'] and done['prompt_eval_count']==transport['prompt_tokens']==probe['prompt_tokens']
    assert done['eval_count']==transport['completion_tokens']==probe['completion_tokens']
    for name,h in loop.read(prep/'prepared_hashes.json').items(): assert digest(prep/name)==h,name
    for name,h in loop.read(prep/'source_snapshot/hashes.json').items(): assert digest(loop.ROOT/'scripts'/name)==h,name
    cost=dict(checks['cost'])
    cost.update(model_calls=1,model_scope='local grammar probe only; no repair generation',
        remote_calls=0,prompt_tokens_total=transport['prompt_tokens'],
        completion_tokens_total=transport['completion_tokens'],
        prompt_tokens_known_subtotal=transport['prompt_tokens'],
        completion_tokens_known_subtotal=transport['completion_tokens'],
        model_wall_seconds_known_subtotal=transport['wall_seconds'],usage_unavailable_calls=0,
        model_status={transport['status']:1})
    result=dict(status='awaiting_new_bounded_remote_authorization',
        qualification_passed=checks['passed'],qualification_checks=len(checks['checks']),
        local_probe=probe,probe_done_reason=done['done_reason'],
        remote_request=str(prep/'request.preview.json'),cost=cost,
        retained_candidate_hash=loop.sha(loop.read(prep/'shared_initial.json')),
        task_matrix=[dict(id=2,status='not_completed',reason='No newly accepted model SVA; request prepared, prior remote grants exhausted.'),
                     dict(id=3,status='not_executed',reason='Fresh independent test requires an accepted and frozen new version.')],
        claims='Syntax/native transport qualification is not semantic repair. Local probe does not establish reliable constrained generation. No new independent inputs materialized.')
    loop.dump(out/'results.json',result)
    loop.dump(out/'source_manifest.json',{str(path.relative_to(loop.ROOT)):digest(path) for path in (
        q/'verification.json',q/'cost.json',p/'qualification.json',p/'model_call/transport_result.json',
        p/'model_call/response.raw.json',p/'model_call/response.stream.jsonl',prep/'request.preview.json',
        loop.ROOT/'scripts/research39_ast_refinement.py',Path(__file__))})
    (out/'SUMMARY.md').write_text(f'''# research39 本轮状态

第 2 项新模型 SVA 验收未完成，第 3 项新冻结版本独立测试未执行。

已实现模型自选表达式树、严格接口校验、无原生结果时保留上一轮历史数值反馈；接受门控不变。36/36 项本地检查通过，实际编译 2 次、执行 4 次（包含 2 次冒烟）。旧 research38 结果回归审计 167/167 通过。语法夹具不进入模型提示词、修复候选或独立验收。

一次真实本地 Qwen 7B 对抗语法探测失败：生成不断嵌套的表达式，在 512 输出 tokens 上限停止，JSON 不完整。输入 59、输出 512 tokens，耗时 {transport['wall_seconds']:.2f} 秒，服务正常关闭。日志未见语法解析错误，不据此宣称约束生成成功。该调用只测试语法，不是硬件细化成功。原始响应完整保存在 `deliverables/research39_local_probe_20261022_r01/model_call/`。

此前明确远程额度已耗尽，新的最多 2 次授权待用户答复。新请求和代码快照位于 `deliverables/research39_prepare_20261022_r01/`，没有新增远程请求。保留候选哈希 `{result['retained_candidate_hash']}`。

新真实版本必须先通过 8 条目标漏报以及历史门控，再完成 113 场景历史回放；接受后冻结，才生成并执行 56 场景、48 种不同激励的新独立测试。没有改写旧模型表达式、降低标准或编造测试成功。本次仍不支持稳定自动细化或完整闭环已经成功的结论。

```powershell
# 资格检查，不调用模型；输出目录须不存在。
wsl -- python3 scripts/research39_qualification.py --out deliverables/research39_qualification_NEW
# 用户授权记录落实后运行；当前尚未执行，不是成功轨迹。
wsl -- python3 scripts/research39_ast_refinement.py run --prepared deliverables/research39_prepare_20261022_r01 --out deliverables/research39_real_20261022_r01 --authorization deliverables/research39_prepare_20261022_r01/authorization.json
```
''',encoding='utf-8')
    print(result['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.out.resolve())
