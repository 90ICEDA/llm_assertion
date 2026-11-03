"""Raw native and evidence-isolation checks before any new model invocation."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research116_prospective_deepseek as s
from research88_cross_parent_audit import inspect_version

ROOT, read, dump, sha = s.ROOT, s.read, s.dump, s.sha


def run(prep, search, out):
    s.verify(prep); out.mkdir(parents=True, exist_ok=False)
    checks = []; rows = 0

    def check(name, value):
        assert value, name
        checks.append(name)

    def rejects(name, fn):
        try: fn()
        except (AssertionError, KeyError, ValueError): checks.append(name)
        else: raise AssertionError(name)

    initial = read(prep / 'initial.json'); baseline = read(prep / 'baseline_full.json')
    n, ev, records = inspect_version(prep / 'baseline_native', initial, baseline); rows += n
    check('initial_partial_not_accepted', s.old.decisions(ev) == dict(O=False, H=False, R=False))
    check('initial_matches_pre_research113_baseline', sha(prep / 'initial.json') == sha(s.SOURCE / 'initial.json'))
    check('baseline270_branch_and_public_gap', s.old.public_eligibility(ev, records) == read(prep / 'task_eligibility.json'))
    req = s.payload(initial, records, prep / 'baseline_native', False, 0)
    check('sealed_request_exact', req == read(prep / 'request.preview.json'))
    for arm in s.ARMS:
        check('identical_initial_' + arm, req == read(prep / 'arms' / arm / 'request.preview.json'))
    altered = copy.deepcopy(records)
    altered['history'] = dict(counts={'PRIVATE_HISTORY_SENTINEL': 7}, ledger=[], required_untriggered=['SECRET'])
    check('ordinary_entire_request_invariant_to_hidden_history', req == s.payload(initial, altered, prep / 'baseline_native', False, 0))
    original_read_text = Path.read_text

    def guarded_read(path, *args, **kwargs):
        # A stronger access check than searching for a path string in the prompt.
        name = path.as_posix()
        assert 'research113_real' not in name and 'independent' not in name and 'frozen/' not in name, name
        if name.startswith((prep / 'baseline_native/history').as_posix()):
            raise AssertionError('public_request_reads_hidden_native_history')
        return original_read_text(path, *args, **kwargs)

    with patch.object(Path, 'read_text', guarded_read):
        check('public_request_reads_no_holdout_or_history_files', s.payload(initial, records, prep / 'baseline_native', False, 0) == req)
    body = json.loads(req['messages'][1]['content'])
    check('first_public_counts_only', set(body['actual_feedback']['visible_counts']) == {'alignment', 'search'})
    check('no_success_or_test_payload', not any(word in json.dumps(req) for word in ('research113_real', 'independent_cases', 'frozen/', 'PRIVATE_HISTORY_SENTINEL')))
    # The qualified common constructor is identical on the same full development data.
    full = s.payload(initial, records, prep / 'baseline_native', True, 0)
    expected = s.temporal.request(initial, records, prep / 'baseline_native', 0)
    expected.update(model=s.MODEL, seed=s.SEED)
    check('qualified_common_frontend_identical', full == expected)
    for name, wanted in [('positive', dict(O=True, H=True, R=True)), ('known_overbroad', dict(O=True, H=False, R=False))]:
        root = prep / 'controls' / name; candidate = read(root / 'candidate.json')
        n, ce, cr = inspect_version(root / 'native', candidate, baseline); rows += n
        check(name + '_real_native_rules', s.old.decisions(ce) == wanted)
        h = s.payload(candidate, cr, root / 'native', True, 1)
        r = s.payload(candidate, cr, root / 'native', True, 1)
        check(name + '_H_R_identical_feedback_and_request', h == r)
        o = s.payload(candidate, cr, root / 'native', False, 1)
        changed = copy.deepcopy(cr); changed['history'] = altered['history']
        check(name + '_O_hidden_history_invariant', o == s.payload(candidate, changed, root / 'native', False, 1))
        for label, request in [('O', o), ('H', h), ('R', r)]:
            check(name + label + '_call_reservation_fits', sum(len(m['content'].encode()) for m in request['messages']) + 2048 + request['max_tokens'] <= 40000)
        hbody = json.loads(h['messages'][1]['content'])
        check(name + '_history_actually_supplied_H_R', 'history' in hbody['actual_feedback']['visible_counts'])
    entries = []
    for path in ('shared/v0', 'arms/O/v1', 'arms/H/v1', 'arms/R/v1'):
        s.reserve(entries, path, req)
    check('max4_physical_reservations', len(entries) == 4 and sum(e['reservation'] for e in entries) <= 160000)
    rejects('fifth_dispatch_rejected', lambda: s.reserve(entries, 'arms/R/v1', req))
    one = []; s.reserve(one, 'shared/v0', req)
    rejects('repeat_dispatch_rejected', lambda: s.reserve(one, 'shared/v0', req))
    rejects('third_round_rejected', lambda: s.reserve([], 'arms/R/v2', req))
    badmodel = copy.deepcopy(req); badmodel['model'] = 'qwen/qwen-2.5-72b-instruct'
    rejects('fallback_model_rejected', lambda: s.reserve([], 'shared/v0', badmodel))
    dummy = ROOT / 'deliverables/research116_AUTH_TEST_NOT_RUN'
    grant = dict(purpose=s.PURPOSE, authorized_calls=4, model=s.MODEL, endpoint=s.old.prior.transport.DEFAULT_URL,
        prepared_sha256=sha(prep / 'sealed.json'), run_output=dummy.relative_to(ROOT).as_posix())
    s.grant_check(grant, prep, dummy)
    for field, value in [('purpose', s.qualified.PURPOSE), ('authorized_calls', 2), ('authorized_calls', 5),
                         ('model', 'qwen/qwen-2.5-72b-instruct'), ('prepared_sha256', 'bad'), ('run_output', 'another_run')]:
        bad = dict(grant); bad[field] = value
        rejects('invalid_grant_' + field + str(value), lambda bad=bad: s.grant_check(bad, prep, dummy))
    check('no_dummy_run', not dummy.exists())
    config = read(prep / 'model_config.json')
    with patch.object(Path, 'read_text', side_effect=AssertionError('initialization_must_not_read_key')):
        model = s.old.Model(out / 'transport_configuration_only', config); model.pending_request = req
        check('effective_transport_matches_request', model._payload(initial, '', {}, '') == req and model.remote_model == s.MODEL)
        check('no_model_calls_during_setup', model.calls == [])
    cost = read(prep / 'preparation_cost.json')['total']
    check('18_fresh_native_qualification_runs', cost['native_compile_calls'] == cost['native_execute_calls'] == 18 and cost['model_calls'] == 0)
    excluded = set(read(prep / 'excluded_words.json'))
    check('old_development_exclusions_kept', set(read(s.SOURCE / 'excluded_words.json')) <= excluded)
    check('task_fixed_before_input_exclusion', read(prep / 'task_lock.json')['initial_sha256'] == sha(s.SOURCE / 'initial.json'))
    check('protected113_results_unchanged', s.protected() == read(prep / 'protected_records.json'))
    import research117_search_preparation as search_run
    search_run.b.verify(search)
    sc = read(search / 'preflight.json'); sp = read(search / 'protocol.json')
    check('search_preparation_passed_no_model_queries', sc['passed'] and sc['model_calls'] == sc['search_queries'] == 0)
    check('search_six_comparators_three_seeds_budget108', len(sp['methods']) == 6 and len(sp['seeds']) == 3 and sp['expected_maximum_search_queries'] == 108)
    check('search_has_generic_avoidance_and_fixed_coverage', {'ordinary_no_repeat', 'coverage_sweep'} <= set(sp['methods']))
    s.verify(prep)
    dump(out / 'preflight.json', dict(passed=True, checks=checks, count=len(checks), raw_native_rows_recomputed=rows,
        model_calls=0, audit_new_native_calls=0, prepared_sha256=sha(prep / 'sealed.json'), script_sha256=sha(Path(__file__))))
    (out / 'SUMMARY.md').write_text('\n'.join([
        '# research116–118：三规则前瞻先导及无模型搜索准备', '',
        f'本地资格：18次新原生编译/实验执行，复核{rows}条原生日志；{len(checks)}项请求/隔离/预算检查通过。真实模型调用0，新接受版本0，新独立测试0。', '',
        '任务在读取旧独立输入之前固定为research94的Ibex #166和部分BRANCH基线；不复制research113的成功性质。research113结果及冻结断言只作哈希保护，新独立输入仅用于避免重复，不用于候选选择或规则调整。', '',
        '公共生成流程固定：DeepSeek V3-0324、文本性质接口、采样绑定前后输出和跨周期反馈、不可改BRANCH、temperature0.2/max_tokens1024，无计划门槛。与已通过先导采用相同构造器；各组只按预定信息边界提供开发证据。', '',
        '|规则|接受依据|后续可见证据|', '|---|---|---|',
        '|O 普通|current9＋search36原生检查|公共证据|',
        '|H 同历史绝对|O＋完整151事务绝对检查|公共＋history115|',
        '|R 防退化|O＋原有保护保持和全性质门控|与H完全相同|', '',
        '原生正对照O/H/R均通过；已有过宽负对照O通过、H/R拒绝。这些是本地资格控制，绝不当作本轮新模型提案。H/R可能等价，不能把共同拒绝或后续随机生成差异称为相对门控独有优势。', '',
        '固定预算：1份共享新提案；被拒绝的O/H/R各最多独立细化1次。最多4次物理调用，每条轨迹最多2次；种子11607/11608，无重试，接受组停止，传输失败全局停止。新用途须另行授权，不挪用research113剩余1次。每次保守预留40000，总160000；价格不可用，记录实际token及原生成本。', '',
        '全部终态后若任一组接受，冻结所有组，用同一批96新指令、四配置测试；未接受的回退组仍列入分母。共享提案只测决定差异，独立后续调用测策略结局，两者分开。没有O接受→历史额外拒绝→同组预算内恢复→新独立通过链，就停止并保存阴性/无区分力结果；通过也不自动扩种子。', '',
        f'搜索准备：{sc["count"]}项本地检查通过，模型调用及新搜索查询均0。复用FIFO候选目录及策略，固定三个新种子、六策略、每任务每组3查询，最多108查询。公开控制资格决定是否选入，按原目录顺序取前两个合格任务，不读取research113数据；不是新增历史父案例。',
        '六策略：普通补测、真实候选对分歧、普通差分、固定覆盖、普通避重、契约搜索。按候选/义务/失效机制去重，公共已曝光缺口扣除，旧发现另行标记；记录首次发现原生次数、参考判定与选择成本，未发现按预算删失。旧零优势结果保持不变。', '',
        '前瞻模型请求：`' + (prep / 'request.preview.json').relative_to(ROOT).as_posix() + '`', '',
        '离线复核：', '```powershell',
        f'wsl -- python3 scripts/research118_prospective_preflight.py --prepared {prep.relative_to(ROOT).as_posix()} --search {search.relative_to(ROOT).as_posix()} --out deliverables/research118_preflight_NEW', '```', '',
        '授权后模型先导入口：', '```powershell',
        f'wsl -- python3 scripts/research116_prospective_deepseek.py run --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research116_real_20261025_r01 --authorization deliverables/research116_authorization_20261025_r01.json', '```', '',
        '搜索比较入口（不调用模型；当前仅完成准备，尚未执行查询）：', '```powershell',
        f'wsl -- python3 scripts/research117_search_preparation.py run --out {search.relative_to(ROOT).as_posix()}',
        f'wsl -- python3 scripts/research117_search_preparation.py audit --out {search.relative_to(ROOT).as_posix()} --audit-out deliverables/research117_native_audit_20261025_r01', '```',
    ]) + '\n', encoding='utf-8')
    print('PREFLIGHT118', len(checks), rows, 'model0', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('prepared', 'search', 'out'):
        ap.add_argument('--' + name, type=Path, required=True)
    a = ap.parse_args(); run(a.prepared.resolve(), a.search.resolve(), a.out.resolve())
