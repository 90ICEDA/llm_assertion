"""Local fail-closed tests and actual native qualification; no remote calls."""
import argparse
import copy
import json
from pathlib import Path

import research81_recovery_comparison as c

b, g, ROOT, read, dump = c.b, c.g, c.ROOT, c.read, c.dump


def local(prep):
    checks, serial = [], 0
    request = read(prep / 'D/request.preview.json')
    def new():
        nonlocal serial
        serial += 1
        return c.Budget(prep / 'local_fixtures' / f'ledger{serial}.json', request['model'])
    def rejects(name, fn):
        try:
            fn()
        except c.BudgetError:
            checks.append(name)
        else:
            raise AssertionError(name)
    x = new()
    rejects('P cannot generate without whole plan', lambda: x.reserve('P', 'generate', request))
    x.reserve('P', 'plan', request)
    rejects('inflight cannot resend', lambda: x.reserve('P', 'plan', request))
    x.complete('P', 'plan', False)
    rejects('failed whole plan cannot generate', lambda: x.reserve('P', 'generate', request))
    for value in (None, 'unknown', 1):
        x = new(); x.reserve('P', 'plan', request); x.complete('P', 'plan', value)
        rejects('non-true plan blocked ' + str(value), lambda: x.reserve('P', 'generate', request))
    for key, value in [('seed', 7907), ('model', 'other'), ('max_tokens', 4096), ('temperature', 0.8)]:
        x = new(); req = copy.deepcopy(request); req[key] = value
        rejects('changed sampler ' + key, lambda: x.reserve('D', 'generate', req))
    x = new(); req = copy.deepcopy(request); req['messages'] = [dict(content='x' * 64001)]
    rejects('oversize fail closed', lambda: x.reserve('D', 'generate', req))
    x = new(); x.reserve('D', 'generate', request)
    rejects('acceptance needs actual full history', lambda: x.complete('D', 'generate', True))
    rejects('history before window/public', lambda: x.native('D', 'generate', 'history', 105))
    rejects('wrong native budget', lambda: x.native('D', 'generate', 'windows', 6))
    x.native('D', 'generate', 'windows', 5)
    rejects('native repetition', lambda: x.native('D', 'generate', 'windows', 5))
    x.complete('D', 'generate', False)
    x.reserve('D', 'refine', request); x.complete('D', 'refine', False)
    rejects('no third D call', lambda: x.reserve('D', 'refine', request))
    rejects('no transfer to plan', lambda: x.reserve('D', 'plan', request))
    x = new(); x.stop('local transport fixture')
    rejects('global transport stop', lambda: x.reserve('D', 'generate', request))
    rejects('no resume ledger', lambda: c.Budget(x.path, request['model']))
    x = new()
    rejects('no independent before freeze', x.independent)
    x.freeze('P', 'local'); x.freeze('D', 'local')
    rejects('no independent without new acceptance', x.independent)
    x = new(); x.reserve('P', 'plan', request); x.complete('P', 'plan', True)
    x.reserve('P', 'generate', request)
    for phase, count in c.CAPS.items():
        x.native('P', 'generate', phase, count); x.phase_pass('P', 'generate', phase)
    x.complete('P', 'generate', True); x.freeze('P', 'local')
    rejects('other arm must freeze too', x.independent)
    x.freeze('D', 'local'); x.independent()
    rejects('no second independent batch', x.independent)
    rejects('no calls after freeze', lambda: x.reserve('D', 'generate', request))
    checks.append('local fixture accepted path reaches one independent barrier')
    rows = read(prep / 'windows.private.json')
    fixture = dict(**g.fixture_rules(), windows=[r['expected'] for r in rows])
    good = g.validate(fixture, rows)
    assert good['accepted']
    template = read(prep / 'sva_template.json')
    unlocked = g.unlock(template, fixture, good, rows)
    assert json.loads(unlocked['messages'][1]['content'])['verified_model_hold_plan'] == fixture
    checks.append('local fixture full plan passed unchanged unlock')
    c.check_requests(read(prep / 'common_development.json'), read(prep / 'P/request.preview.json'), read(prep / 'D/request.preview.json'))
    checks.append('all first-stage public evidence exactly equal')
    cohort = []
    for arm in 'ABCD':
        folder = c.OLD / 'arms' / arm / 'plan/v0'
        plan = read(folder / 'model_call/hold_plan.json')
        truth = read(c.BASE / 'arms' / arm / 'windows.private.json')
        verdict = g.validate(plan, truth)
        assert verdict == read(folder / 'decision.json') and not verdict['accepted']
        try:
            g.unlock(template, plan, verdict, truth)
        except ValueError:
            pass
        else:
            raise AssertionError('old_failed_plan_unlocked')
        checks.append(arm + ' actual full failed plan remains rejected')
        cohort.append(dict(arm=arm, full_pass=False,
            executed_rules_correct=sum(x['rule_matches_certificate'] for x in verdict['details']),
            window_labels_correct=sum(x['window_matches_certificate'] for x in verdict['details']),
            native_SVA_effect='not_observed_no_generation',
            source=str(folder), response_sha256=b.search.digest(folder / 'model_call/hold_plan.json')))
    dump(prep / 'bottleneck_audit.json', dict(cohort=cohort,
        conclusion='3/4 complete rules execute correctly,0/4 full plans pass. Whether their generated SVA would pass remains unobserved. No repaired window answers or selected historical plan supplied to new requests.',
        retrospective=True, model_calls=0))
    dump(prep / 'local_checks.json', dict(passed=True, checks=checks, fixture_only=True, model_calls=0))
    print('LOCAL', len(checks), flush=True)


def qualify(prep):
    assert not (prep / 'qualification.json').exists(), 'do not repeat completed qualification'
    controls, raw, checks = [], 0, []
    with b.extension.installed():
        for name, slot, want in [('archived_positive', 'c05', True), ('archived_queue_head_negative', 'c04', False)]:
            src = g.old.sem.SOURCE / slot
            source = read(src / 'source.json')
            candidate_path = ROOT / source['path']
            candidate, edit = read(candidate_path), read(candidate_path.parent / 'model_edit.json')
            assert b.search.digest(candidate_path) == source['candidate_sha256']
            assert candidate == read(src / 'candidate.json')
            folder = prep / 'native_controls' / name
            dump(folder / 'candidate.json', candidate)
            verdict, wr, small, full = c.native_admission(prep, folder, candidate, edit)
            assert verdict['accepted'] == want, (name, verdict)
            for phase, filename, result in [('windows', 'window_cases.json', wr), ('public', 'cases.json', small), ('history', 'history_cases.json', full)]:
                if result is not None:
                    raw += g.old.raw_replay(folder / phase, read(prep / filename), candidate, checks)
            if not want:
                call = dict(status='response_received', candidate_status='archived_model_control_not_new_response')
                req = c.refinement_request(read(prep / 'sva_template.json'), read(prep / 'initial.json'), folder,
                                          call, edit, verdict, wr, small, full)
                assert sum(len(m['content']) for m in req['messages']) <= 64000
                dump(folder / 'feedback_size_check.json', dict(characters=sum(len(m['content']) for m in req['messages']),
                    passes_cap=True, control_only=True, request_not_sent=True))
            controls.append(dict(name=name, accepted=verdict['accepted'], expected=want,
                candidate_source=str(candidate_path), source_sha256=source['candidate_sha256'],
                windows=wr['counts'] if wr else None, public=small['counts'] if small else None,
                history=full['counts'] if full else None))
    dump(prep / 'qualification.json', dict(passed=True, controls=controls, checks=checks,
        raw_native_records=raw, new_model_calls=0, new_model_acceptances=0,
        scope='Fresh native replays of archived controls only; positive never supplied to either model arm. Not recovery success.'))
    print('QUALIFIED', raw, 'raw native records', flush=True)


def seal(prep):
    assert not (prep / 'sealed.json').exists(), 'sealed protocol immutable'
    assert read(prep / 'local_checks.json')['passed'] and read(prep / 'qualification.json')['passed']
    assert read(prep / 'model_config.json')['call_timeout'] == 300
    common, plan, direct = read(prep / 'common_development.json'), read(prep / 'P/request.preview.json'), read(prep / 'D/request.preview.json')
    c.check_requests(common, plan, direct)
    checks = ['same common evidence', 'same initial candidate', 'same model/seed/sampler', 'same final native acceptance',
              'P failure blocks SVA', 'D two calls maximum', 'no cross-arm response', 'no private plan answers',
              'no archived successful SVA', 'no independent data in either prompt', 'fresh tests only after both freezes']
    # Check actual source equality rather than searching labels alone.
    assert common['current_assertions'] == [{k:v for k,v in a.items() if k != 'reason'} for a in read(prep / 'initial.json')['assertions']]
    assert common['hold_development_samples'] == [r['public'] for r in read(prep / 'windows.private.json')]
    for name, count in [('window_cases.json', 5), ('cases.json', 14), ('history_cases.json', 105)]:
        assert read(prep / name) == read(c.BASE / name) and len(read(prep / name)) == count
    for key in ('output_schema', 'rtl_and_common_contract'):
        assert common[key] == json.loads(read(c.BASE / 'arms/A/sva_template.json')['messages'][1]['content'])[key]
    assert g.old.old.screen.protected() == read(prep / 'protected.json')
    dump(prep / 'preflight.json', dict(passed=True, checks=checks, new_model_calls=0))
    dump(prep / 'cost.json', g.old.cost_audit(prep, b.paired.files(prep)))
    q, cost = read(prep / 'qualification.json'), read(prep / 'cost.json')['total']
    lines = ['# research81：恢复流程对照准备与实跑资格', '',
        '状态：本地实现与原生资格验证完成；真实对照尚未执行，需新授权。新接受模型版本0，新独立验收0。', '',
        '## 固定协议', '',
        '|组|第一调用|第二调用条件|最终标准|',
        '|---|---|---|---|',
        '|P 完整计划流程|输出完整规则和11窗口答案|完整判断通过后生成一次SVA；失败即停|5窗口场景＋14公共＋105历史|',
        '|D 直接生成流程|直接生成SVA|首版拒绝后依据自己的原生/接口诊断细化一次；接受即停|完全相同|', '',
        '固定种子8107、Qwen72B、temperature0.2、输出上限2048 tokens、每次输入64000字符、300秒总超时。两组各最多2次，总计最多4次；不重试、不挪用额度，传输/执行异常全局停止。',
        '两组共用逐字一致的公共开发内容：RTL、规格、初始候选、接口、开发观察和11窗口。每个请求中阶段任务与输出格式不同；P的实际通过计划是该流程自己的处理产物，不泄露给D。',
        '这是固定两次调用预算下的辅助流程比较，不是仅移除一个门控开关的纯因果实验：D最多两次性质提案，P将一次额度用于计划。必须同时报告性质机会数、调用、tokens和原生成本。单种子结果不能证明稳定效应，也不是两个核心机制的增量验证。', '',
        '## 本地实跑资格', '',
        f"预算/门控/隔离检查{len(read(prep / 'local_checks.json')['checks'])}项；新增原生日志复核{q['raw_native_records']}份。", '',
        '|归档对照|接受|窗口检出/漏报|公共检出/漏报|历史检出/漏报|',
        '|---|---|---|---|---|']
    for control in q['controls']:
        cells = []
        for phase in ('windows', 'public', 'history'):
            counts = control[phase]
            cells.append(f"{counts['detections']}/{counts['misses']}" if counts else '未执行')
        lines.append('|'+ '|'.join([control['name'], str(control['accepted'])] + cells) + '|')
    lines += ['', '以上是归档模型版本的本地正负对照，不是本轮真实生成成功；成功性质未进入任何模型请求。关键unknown与后续归因unknown分别保留，具体数值见qualification.json。',
        f"准备成本：原生编译{cost['native_compile_calls']}次，执行{cost['native_execute_calls']}次（启动自检{cost['compile_smoke_execute_calls']}次），模型{cost['model_calls']}次，形式化{cost['formal_calls']}次。", '',
        '## 接受、冻结与停止', '',
        '两组均必须实际通过原生目标检出、必要触发、合法误报和105历史保护检查。unknown不算通过；重复可执行性质在编译前拒绝。拒绝继续保留公共基线。',
        '两组都终止并冻结后，仅在至少一个新接受版本存在时生成同一批全新56场景，覆盖Depth2/4/8及五义务；同哈希只物理回放一次。已有开发与旧独立输入按哈希排除，新测试不反馈、不选候选。新独立失败或无新接受即停止，不追加种子或提示修正。',
        'research80的原失败保持不变：B/C/D规则可执行正确并不等于完整模型判断通过，也不能推断未生成SVA的结果。完整门控究竟有利于生成尚未得到本轮对照结果。', '',
        '## 入口', '', '```powershell',
        'wsl -- python3 scripts/research81_recovery_comparison.py verify --prepared deliverables/research81_prepare_20261025_r01',
        '# 获得本协议专用授权并保存绑定记录后才可运行；既有research80剩余额度不能转用。',
        'wsl -- python3 scripts/research81_recovery_comparison.py run --prepared deliverables/research81_prepare_20261025_r01 --authorization deliverables/research81_prepare_20261025_r01/authorization.json --out deliverables/research81_real_20261025_r01',
        'wsl -- python3 scripts/research81_audit.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --out deliverables/research81_audit_20261025_r01',
        '```', '', '来源与代码版本通过SHA256封存；当前工作区没有可用Git历史，不补造过去提交号。']
    (prep / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    bindings = read(prep / 'source_bindings.json')
    for a in 'ABCD':
        for rel in ('decision.json', 'model_call/hold_plan.json'):
            path = c.OLD / 'arms' / a / 'plan/v0' / rel
            bindings[str(path)] = b.search.digest(path)
    dump(prep / 'source_bindings.json', bindings)
    dump(prep / 'code_versions.json', {str(p): b.search.digest(p) for p in (ROOT / 'scripts').glob('*.py')})
    files = list(prep.rglob('*.json')) + [prep / 'SUMMARY.md']
    dump(prep / 'sealed.json', {p.relative_to(prep).as_posix(): b.search.digest(p) for p in files})
    c.verify(prep)
    print('SEALED_VERIFIED', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['local', 'qualify', 'seal'])
    p.add_argument('--prepared', type=Path, required=True)
    a = p.parse_args()
    globals()[a.action](a.prepared.resolve())
