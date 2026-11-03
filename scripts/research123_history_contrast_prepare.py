"""Seal a scoped O-versus-history pilot; R is decision-only shadow, no model calls.

This entry prepares and verifies requests/protocol/controller. It never dispatches.
No H/R random continuation comparison is represented as a distinct rule effect.
"""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch

import research122_discrimination_audit as audit

s, x = audit.s, audit.x
ROOT, read, dump, sha = audit.ROOT, audit.read, audit.dump, audit.sha
PREP = audit.PREP
SEED = 12307
PURPOSE = 'research123_scoped_history_increment_pilot'


def continuation(decisions, status, measured=True):
    if status != 'response_received': return 'stop_transport'
    if not measured: return 'stop_interface_or_repeat'
    if decisions['H'] != decisions['R']: return 'stop_rule_integrity_disagreement'
    if decisions['O'] and not decisions['H']: return 'history_once'
    return 'stop_no_discriminating_proposal'


class Budget:
    def __init__(self): self.entries = []

    def reserve(self, path, request, first_decisions=None, first_status=None):
        index = len(self.entries)
        if index >= 2: raise ValueError('two_physical_call_cap')
        if path != ('shared/v0' if index == 0 else 'history/v1'): raise ValueError('wrong_or_repeated_dispatch')
        if index and continuation(first_decisions, first_status) != 'history_once': raise ValueError('no_recovery_qualification')
        if request['model'] != s.MODEL or request['seed'] != SEED + index: raise ValueError('fixed_model_seed')
        if request['temperature'] != 0.2 or request['max_tokens'] != 1024: raise ValueError('fixed_sampling')
        amount = sum(len(m['content'].encode()) for m in request['messages']) + 2048 + request['max_tokens']
        if amount > 40000 or sum(e['reservation'] for e in self.entries) + amount > 80000: raise ValueError('token_cap')
        self.entries.append(dict(path=path, reservation=amount, request_sha256=x.old.acceptance.sha(request)))


def tests(request):
    checks = []
    def check(name, value):
        if not value: raise AssertionError(name)
        checks.append(name)
    extra = dict(O=True, H=False, R=False)
    for o in (False, True):
        for h in (False, True):
            for r in (False, True):
                d = dict(O=o, H=h, R=r)
                expected = ('stop_rule_integrity_disagreement' if h != r else
                            'history_once' if o and not h else 'stop_no_discriminating_proposal')
                check(str(d), continuation(d, 'response_received') == expected)
                check('transport/' + str(d), continuation(d, 'timeout') == 'stop_transport')
    check('interface_stop', continuation(extra, 'response_received', False) == 'stop_interface_or_repeat')
    b = Budget(); b.reserve('shared/v0', request)
    second = copy.deepcopy(request); second['seed'] += 1
    b.reserve('history/v1', second, extra, 'response_received')
    failures = [('third_call', lambda: b.reserve('history/v1', second, extra, 'response_received'))]
    for name, decisions, status in [('both_accept', dict(O=True,H=True,R=True), 'response_received'),
                                    ('ordinary_rejects', dict(O=False,H=False,R=False), 'response_received'),
                                    ('transport_failure', extra, 'timeout')]:
        fresh = Budget(); fresh.reserve('shared/v0', request)
        failures.append((name, lambda b=fresh,d=decisions,st=status: b.reserve('history/v1', second,d,st)))
    for name, action in failures:
        rejected = False
        try: action()
        except ValueError: rejected = True
        check(name + '_blocked', rejected)
    check('two_calls_reserved_before_dispatch', len(b.entries) == 2)
    return checks


def verify(out):
    for name, digest in read(out / 'sealed.json').items():
        if sha(out / name) != digest: raise AssertionError(name)
    for name, digest in read(out / 'input_bindings.json').items():
        if sha(ROOT / name) != digest: raise AssertionError(name)
    req = read(out / 'request.preview.json')
    checks = tests(req)
    if read(out / 'checks.json')['controller_checks'] != checks: raise AssertionError('controller_recheck')
    return len(checks)


def prepare(source_audit, out):
    audit.guard_reads()
    for name, digest in read(source_audit / 'sealed.json').items():
        assert sha(source_audit / name) == digest, name
    qualification = read(source_audit / 'rule_audit.json')
    assert qualification['contrasts']['O_vs_history_qualified']
    assert not qualification['contrasts']['H_vs_R_semantic_increment_qualified']
    assert read(source_audit / 'audit.json')['passed']
    initial = read(PREP / 'initial.json')
    records = {c: read(PREP / 'baseline_native' / c / 'result.json') for c in ('alignment','search')}
    with patch.object(s, 'SEED', SEED): req = s.payload(initial, records, PREP / 'baseline_native', False, 0)
    previous = read(PREP / 'request.preview.json')
    expected = copy.deepcopy(previous); expected['seed'] = SEED
    assert req == expected  # Same qualified frontend/development scope. Only a new predeclared seed.
    body = json.loads(req['messages'][1]['content'])
    assert set(body['actual_feedback']['visible_counts']) == {'alignment', 'search'}
    checks = tests(req)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'request.preview.json', req)
    dump(out / 'initial.json', initial)
    protocol = dict(name=PURPOSE, status='sealed_not_executed_no_authorization',
        parent='original Ibex #166 decoder; known selected development task, not a new parent',
        qualification=source_audit.relative_to(ROOT).as_posix(),
        estimand='Added historical checks versus ordinary public acceptance; not unique relative-preservation effect and not a model-success population rate.',
        rules=dict(O='Unchanged current9/search36 native phase/trigger/all-property acceptance.',
                   H='Unchanged O plus full151 absolute/no-false-alarm/miss/unknown/necessary-trigger and all-property guards.',
                   R='Unchanged relative-preservation rule measured on the same proposal, same151 evidence; decision-only shadow, no separate continuation.'),
        generation='Same qualified research116 DeepSeek text frontend, temporal sample binding, immutable BRANCH, public initial bit31 OP candidate. No new plan gate or representation change.',
        editable_scope='OP only. Fixed BRANCH cannot be deleted. Initial OP detections0, fixed BRANCH270. This cannot measure losing baseline OP detections or deleting BRANCH.',
        shared_proposal='One fresh response, paired O/H/R decisions from identical native measurement. Never select an archived proposal as the first response.',
        continuation='Only if first O accepts, H/R both reject and no infrastructure/interface failure: H gets exactly one fresh continuation with its own actual history diagnosis; O accepts/stops. H/R disagreement stops for integrity audit.',
        missing_opportunity='If all accept or O rejects, stop this pilot; do not add a call or seed to hunt a discriminating proposal.',
        fallback='H/R rejection keeps exact initial or last accepted active hash. Initial baseline is partial, not full-case success.',
        model=s.MODEL, endpoint=s.old.prior.transport.DEFAULT_URL, seeds=[SEED,SEED+1], temperature=0.2,
        maximum_physical_model_calls=2, maximum_calls_per_trajectory=2, maximum_recovery_calls=1,
        maximum_reserved_tokens_per_call=40000, total_reserved_tokens=80000, maximum_output_tokens=1024,
        call_timeout_seconds=300, maximum_wall_seconds=1200, retries=0, transfer_quota=False,
        native_compile_cap=16, native_experiment_execute_cap=16, native_smoke_execute_cap=16,
        cost='Count attempted calls including errors; report missing usage as unavailable. Shared proposal physical cost once, logical shared attribution separate. Preparation/audit costs separate. Actual costs can differ because O stops.',
        information='First public current9/search36 only. Historical continuation uses its own measured full151 diagnosis via the same research116 payload builder. No other-arm response or test outcome.',
        freeze='Freeze all terminal active versions and candidate/RTL/development hashes before generating any new test.',
        independent='If any arm accepts, after all terminals generate shared96 new words/four existing heldout configurations. Exclude all previously used inputs, including113/116 words for collision suppression only AFTER task/rules lock. No old outcomes read. Evaluate all terminal versions; partial fallback remains failure/incomplete in denominator.',
        expansion_gate='Fresh shared O-accept/H-reject plus same-H budget-bounded full151 acceptance plus new independent pass; otherwise stop. Passing only permits a separate multiseed protocol, never automatic expansion.',
        limitations='Known selected-case prospective proposals. Initial legal-false-alarm prevention/restoration is possible; lost-BRANCH or existing-OP detection recovery is structurally excluded. No claim R beats H.',
        funding='No model calls authorized by this preparation. Old purpose-restricted quota cannot be reused.',
        execution_status='Preparation and local controller tests only; no transport dispatch or new native run performed.')
    dump(out / 'protocol.json', protocol)
    search_candidates = read(source_audit / 'search_candidates.json')
    dump(out / 'search_extension_eligibility.json', dict(status='inventory_only_not_search_protocol',
        candidates=[c['name'] for c in search_candidates if c['qualified']],
        excluded=[dict(candidate=c['name'],reason=c['failure']) for c in search_candidates if not c['qualified']],
        selection='All8 eligible; never filter by discovered gap count. Six eligible candidates lack beyond-public search.',
        mandatory_before_run=['Seal full information scope, all known-development keys, parameter sets, seeds, selectors and fixed budgets.',
                              'Requalify legal reference and real target exposure for each new parameter configuration.',
                              'Keep ordinary_no_repeat and fixed coverage controls; count native/reference/selector costs.',
                              'Missing historical registry entry stays unknown; no global novelty assertion.'],
        model_calls=0, new_search_queries=0))
    inputs = [source_audit / 'sealed.json', source_audit / 'audit.json', source_audit / 'rule_audit.json',
              source_audit / 'search_candidates.json', source_audit / 'search_gap_registry.json',
              PREP / 'sealed.json', PREP / 'request.preview.json', PREP / 'initial.json',
              PREP / 'baseline_full.json', PREP / 'source_binding.json', x.P / 'target_preservation.private.json',
              PREP / 'baseline_native/decision.json']
    inputs += [PREP / 'baseline_native' / c / 'result.json' for c in ('alignment','search','history')]
    inputs += list((ROOT / 'scripts').glob('*.py'))
    dump(out / 'input_bindings.json', {p.relative_to(ROOT).as_posix():sha(p) for p in inputs})
    dump(out / 'checks.json', dict(passed=True, controller_checks=checks, exact_prior_frontend_except_seed=True,
        public_only_first_request=True, H_R_shadow_only=True, new_model_calls=0, native_executions=0,
        prior_holdout_inputs_or_outcomes_read=False))
    (out / 'SUMMARY.md').write_text('''# research123 有区分能力范围内的前瞻协议封存

仅封存，模型调用0、原生执行0。首轮请求request.preview.json；协议protocol.json；固定种子12307/12308，最多2次物理调用（共享新提案1次，满足条件后历史组恢复1次），无重试、不挪用、不扩种子。当前没有新调用授权。

本对照测O相对新增历史检查的效果。R只作同提案影子判断，不给H/R分别调用模型后比较随机差异。固定BRANCH、模型、生成表示、开发信息和原生接受标准不变；不人为修改候选制造退化。

只有共享新提案O接受、H/R均拒绝，才允许一次历史反馈恢复。其余结果直接停止该先导；没有机会不能写成恢复率0%。全部终态先冻结，有接受版本才生成新96指令四配置测试。全部目标和历史通过、且新独立通过后，才能另行准备多种子验证。

这不能验证R相对H的独有语义收益，也不能验证模型删除固定BRANCH造成的检出丢失。既有原生负对照只证明O/H可区分，不保证下一真实模型提案会产生区分。

搜索候选已保留全部8个公共合格候选及c07排除原因，见search_extension_eligibility.json；这份候选表尚不是新的搜索执行协议，没有执行新搜索。
''', encoding='utf-8')
    dump(out / 'sealed.json', {f.name:sha(f) for f in out.iterdir() if f.is_file()})
    n = verify(out)
    print('SEALED123', dict(controller_checks=n, model_calls=0, native_executions=0, maximum_future_calls=2,
                            scoped_comparison='O versus history; R shadow only', authorization=False), flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['prepare','verify'])
    ap.add_argument('--audit', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    if args.action == 'prepare': prepare(args.audit.resolve(), args.out.resolve())
    else: print('VERIFIED123', verify(args.out.resolve()))
