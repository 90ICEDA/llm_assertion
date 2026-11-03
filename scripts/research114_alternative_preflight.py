"""Offline qualification of a sealed model-only pilot; never submits generation."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research113_alternative_model_pilot as s
import research105_temporal_preflight as native

ROOT, read, dump, sha = s.ROOT, s.read, s.dump, s.sha


def run(prep, out):
    s.verify(prep); out.mkdir(parents=True, exist_ok=False)
    checks = []

    def check(name, condition):
        assert condition, name
        checks.append(name)

    def rejects(name, fn):
        try:
            fn()
        except (AssertionError, KeyError, ValueError):
            checks.append(name)
        else:
            raise AssertionError(name)

    # Recompute actual raw RTL/reference/trigger records and temporal bindings.
    # This is archived-run audit, not a new native experiment or model response.
    native.run(s.SOURCE, out / 'native_evidence_audit')
    audit = read(out / 'native_evidence_audit/preflight.json')
    check('archived_native_evidence_recomputed', audit['passed'] and audit['native_rows_recomputed'] == 4236)
    original = read(s.SOURCE / 'request.preview.json'); req = read(prep / 'request.preview.json')
    check('only_model_field_changed', {k for k in set(req) | set(original) if req.get(k) != original.get(k)} == {'model'})
    check('messages_byte_identical', req['messages'] == original['messages'])
    check('model_catalog_listed', any(e.get('id') == s.MODEL for q in read(prep / 'inventory.json')['queries'] for e in q.get('models', [])))
    config = read(prep / 'model_config.json'); oldconfig = read(s.SOURCE / 'model_config.json')
    check('only_configuration_model_changed', {k for k in config if config[k] != oldconfig[k]} == {'remote_model'})
    for name in ('initial.json', 'proposal.json', 'baseline_full.json', 'history_cases.json', 'search_cases.json', 'excluded_words.json'):
        check(name + '_unchanged', sha(prep / name) == sha(s.SOURCE / name))
    check('115_plus36_transactions', len(read(prep / 'history_cases.json')) == 115 and len(read(prep / 'search_cases.json')) == 36)
    excluded = set(read(prep / 'excluded_words.json'))
    used = {t['instruction'] for n in ('history_cases.json', 'search_cases.json') for t in read(prep / n)}
    check('development_words_excluded', used <= excluded)
    current = read(prep / 'proposal.json'); records = s.r.records(s.r.VERSION / 'native')
    for i in range(2):
        old = s.r.temporal.request(current, records, s.r.VERSION / 'native', i)
        new = s.request(current, records, s.r.VERSION / 'native', i)
        old['model'] = s.MODEL
        check(f'round{i}_only_model_changed', new == old)
        check(f'round{i}_same_seed', new['seed'] == 10407 + i)
    check('no_successful_archive_or_tests_in_payload', not any(n in json.dumps(req) for n in
          ('research93', 'research92_real', 'frozen/', 'independent_cases', 'research108_real')))
    # Inspect the real transport payload without calling .call or reading a key.
    with patch.object(Path, 'read_text', side_effect=AssertionError('no credential or source read during model initialization')):
        model = s.p.Model(out / 'transport_configuration_only', config)
        model.pending_request = req
        check('effective_transport_payload_is_sealed_request', model._payload(current, 'op_bit28_illegal', {}, 'preflight') == req)
        check('configured_model_is_selected_model', model.remote_model == s.MODEL)
        check('no_generation_during_constructor', len(model.calls) == 0)
    budget = s.Budget(); budget.reserve(req); budget.reserve(req)
    check('two_attempts_charge_full_reservations', len(budget.entries) == 2 and sum(e['reservation'] for e in budget.entries) <= 80000)
    rejects('third_dispatch_rejected', lambda: budget.reserve(req))
    wrong = copy.deepcopy(req); wrong['model'] = s.p.prior.transport.DEFAULT_MODEL
    rejects('fallback_to_qwen_rejected', lambda: s.Budget().reserve(wrong))
    large = copy.deepcopy(req); large['messages'] = [dict(role='user', content='x' * 40000)]
    rejects('oversize_dispatch_rejected', lambda: s.Budget().reserve(large))
    for accepted in (False, True):
        for status in ('response_received', 'http_error', 'response_truncated', 'timeout'):
            for calls in (1, 2):
                expected = accepted or status != 'response_received' or calls == 2
                check(f'stop_{accepted}_{status}_{calls}', s.must_stop(accepted, status, calls) == expected)
    dummy = ROOT / 'deliverables/research113_AUTH_TEST_NOT_RUN'
    grant = dict(purpose=s.PURPOSE, authorized_calls=2, endpoint=s.p.prior.transport.DEFAULT_URL, model=s.MODEL,
                 prepared_sha256=sha(prep / 'sealed.json'), run_output=dummy.relative_to(ROOT).as_posix())
    s.grant_check(grant, prep, dummy)
    for key, value in [('purpose', 'research104_temporal_recovery'), ('authorized_calls', 3), ('authorized_calls', True),
                       ('endpoint', 'https://example.invalid/'), ('model', s.p.prior.transport.DEFAULT_MODEL),
                       ('prepared_sha256', 'incorrect'), ('run_output', 'another_run')]:
        bad = dict(grant); bad[key] = value
        rejects(f'wrong_grant_{key}_{value}_rejected', lambda bad=bad: s.grant_check(bad, prep, dummy))
    check('no_dummy_generation_run_created', not dummy.exists())
    check('protected_qwen_failures_unchanged', s.protected() == read(prep / 'protected_failures.json'))
    check('old_generation_routes_stopped', read(prep / 'route_stops.json')['no_further_calls'])
    check('no_new_success_claim', read(prep / 'comparison.json')['changed_fields'] == ['model'])
    s.verify(prep)
    result = dict(passed=True, checks=checks, count=len(checks), reused_native_checks=audit['count'],
                  native_rows_recomputed=audit['native_rows_recomputed'], generation_calls=0, new_native_runs=0,
                  prepared_sha256=sha(prep / 'sealed.json'), script_sha256=sha(Path(__file__)))
    dump(out / 'preflight.json', result)
    (out / 'SUMMARY.md').write_text('\n'.join([
        '# research112–114：停止旧路线，封存单替代模型先导', '',
        f'本轮仅执行模型目录GET和离线核验；新增生成调用0、新原生执行0、新接受版本0、新独立测试0。{len(checks)}项先导检查和{audit["count"]}项复用时序检查通过，重新核对4236条既有原生记录。', '',
        f'选择：`{s.MODEL}`。同一服务目录已列出该ID，但目录不提供参数兼容性、实际模型权重、价格等证明；生成能力与服务兼容性均待实际授权调用确认。本地WSL Ollama tags连接被拒绝，不代表其他主机没有模型。', '',
        'research104完整集合路线、research108 C完整集合/E原子编辑路线保持失败及停止状态。不再追加Qwen72B调用。', '',
        '唯一实验变量：model。与research104首轮请求的messages、当前失败候选、真实跨周期诊断、输出表示、seed10407、temperature0.2、max_tokens1024、流式及JSON参数完全相同。第二轮seed10408，只反馈本模型自己的真实结果；不更改表示、计划门槛或原生验收。历史Qwen结果作为历史参照，不伪称同期随机对照，种子相同也不保证跨模型采样等价。', '',
        '预算：最多2次新调用（含HTTP错误、截断、重复或无效响应），不重试、不切模型、不降级参数；服务/传输失败立即停止。每次最多40000保守token预留，总80000；预留不是实际token或价格。每次300秒，总墙钟1200秒；最多14次原生编译及执行（两版各6次、条件性独立回放2次）。', '',
        '接受条件不变：当前9事务与完整115历史＋36搜索事务，420 OP＋270 BRANCH检出，首周期/保持阶段必要触发，无合法误报、漏报、关键unknown，历史所有性质门控通过。失败版本不激活，上一版本只是部分BRANCH基线，不能称整例通过。', '',
        '只有完整接受后，才保存冻结哈希并生成96个新指令、四配置独立测试。独立失败停止本路线，不反馈给模型、不自动扩种子。成功仅说明该选定案例上的公共生成瓶颈缓解；不能计作契约搜索或防退化收益。后续前瞻机制实验需另行封存、授权。', '',
        '搜索审计保留research110结果：342次选择可复现，两个原实验契约独有缺口均0。可见选择依赖不等于额外发现或成本优势；本轮不重复查询或伪造新收益。', '',
        '封存请求：`' + (prep / 'request.preview.json').relative_to(ROOT).as_posix() + '`', '',
        '离线复核命令（输出目录须不存在）：', '```powershell',
        'wsl -- python3 scripts/research114_alternative_preflight.py --prepared ' + prep.relative_to(ROOT).as_posix() + ' --out deliverables/research114_preflight_NEW', '```', '',
        '取得本轮用途及模型绑定授权后才可执行：', '```powershell',
        'wsl -- python3 scripts/research113_alternative_model_pilot.py run --prepared ' + prep.relative_to(ROOT).as_posix() + ' --out deliverables/research113_real_20261025_r01 --authorization deliverables/research113_authorization_20261025_r01.json', '```',
        '授权文件尚未创建；prepare/preflight不是模型实验成功。',
    ]) + '\n', encoding='utf-8')
    print('PREFLIGHT114', {k: v for k, v in result.items() if k != 'checks'}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepared', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args(); run(a.prepared.resolve(), a.out.resolve())
