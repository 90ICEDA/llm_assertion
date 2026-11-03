"""Local-only sealed many-properties-per-obligation qualification. No LLM calls."""
import argparse
import copy
import itertools
import json
from pathlib import Path
import time
import research139_obligation_mapping as m

p = m.prior
ROOT, read, dump, digest, rel = p.ROOT, p.read, p.dump, p.digest, p.rel
PREVIOUS = ROOT/'deliverables/research136_prepare_20261026_r01'
FAILED = ROOT/'deliverables/research136_real_20261027_r01'


def edit(items):
    return dict(operation='replace', reason='Explicit local interface qualification fixture; not model output.', assertions=copy.deepcopy(items))


def verify(prep):
    p.verify(PREVIOUS)
    for name, sha in read(prep/'source_bindings.json').items():
        assert digest(ROOT/name) == sha, name
    for name, sha in read(prep/'sealed.json').items():
        assert digest(prep/name) == sha, name


def prepare(out):
    opened = p.q.guard()
    p.verify(PREVIOUS)
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, ok):
        assert ok, name
        checks.append(name)
    positive = read(p.QUAL/'native_controls/local_positive/candidate.json')
    items = p.q.as_edit(positive)['assertions']
    split = []
    for item in items:
        for phase in ('instr_new', '!instr_new'):
            a = copy.deepcopy(item)
            a['antecedent'] = '('+a['antecedent']+') && ('+phase+')'
            split.append(a)
    permuted = [split[i] for i in (2, 0, 3, 1)]
    wrong = copy.deepcopy(split)
    for a in wrong:
        a['obligations'] = [m.OP if a['obligations'] == [m.BRANCH] else m.BRANCH]
    false_alarm = copy.deepcopy(items[0])
    false_alarm.update(antecedent="instr[6:0] == 7'h13", consequent='illegal_insn', obligations=[m.OP])
    # Add a broad alarm whose declared label is false; all-property guard must
    # catch it even if the target projection would omit that alarm.
    false_alarm['antecedent'] = "1'b1"
    negative = read(p.QUAL/'native_controls/local_history_loss/candidate.json')
    fixtures = {
        'split': (edit(split), [True, True]),
        'permuted': (edit(permuted), [True, True]),
        'duplicate': (edit(split+[split[0], split[2]]), [True, True]),
        'branch_first_only': (edit([split[0], split[2], split[3]]), [False, False]),
        'wrong_labels': (edit(wrong), [False, False]),
        'legal_false_alarm': (edit(split+[false_alarm]), [False, False]),
        'historical_loss': (p.q.as_edit(negative), [True, False]),
        'archived136_exact': (read(FAILED/'shared/v0/model_call/model_edit.json'), None),
    }
    for name, (value, expected) in fixtures.items():
        candidate = m.adapt(value)
        check('verbatim/'+name, all(all(a[k] == b[k] for k in p.q.FIELDS) for a, b in zip(value['assertions'], candidate['assertions'])))
        dump(out/'fixtures'/name/'edit.json', value)
        dump(out/'fixtures'/name/'candidate.json', candidate)
    for i, order in enumerate(itertools.permutations(split)):
        c = m.adapt(edit(list(order)))
        check('order_invariance/'+str(i), len(m.ids(c, m.BRANCH)) == len(m.ids(c, m.OP)) == 2)
    cases = [
        ('missing_label', lambda v: v['assertions'][0].pop('obligations')),
        ('unknown_label', lambda v: v['assertions'][0].update(obligations=['unknown'])),
        ('duplicate_label', lambda v: v['assertions'][0].update(obligations=[m.BRANCH, m.BRANCH])),
        ('ambiguous_label', lambda v: v['assertions'][0].update(obligations=[m.BRANCH, m.OP])),
        ('empty_label', lambda v: v['assertions'][0].update(obligations=[])),
        ('missing_obligation', lambda v: v.update(assertions=[split[0], split[1]])),
        ('too_many', lambda v: v.update(assertions=split+split)),
        ('extra_field', lambda v: v['assertions'][0].update(id='manual_id')),
        ('unknown_signal', lambda v: v['assertions'][0].update(antecedent='no_such_signal')),
        ('bad_timing', lambda v: v['assertions'][0].update(timing='eventually')),
    ]
    for name, mutate in cases:
        value = edit(split); mutate(value)
        try:
            m.adapt(value)
        except (ValueError, KeyError, AssertionError, TypeError):
            checks.append('reject/'+name)
        else:
            raise AssertionError(name)
    # Compatibility: all three original qualified fixtures must retain the
    # exact executable representation. Fresh native runs below test generality.
    for name in ('baseline', 'local_positive', 'local_history_loss'):
        c = read(p.QUAL/'native_controls'/name/'candidate.json')
        check('legacy_render/'+name, m.adapt(p.q.as_edit(c)) == c)
        result = read(p.QUAL/'native_controls'/name/'native/alignment/result.json')
        old_focus = p.x.g.focus_gate(result, read(p.x.P/'focus.private.json'))
        new_focus = m.focus_gate(result, read(p.x.P/'focus.private.json'), c)
        check('legacy_focus/'+name, {k:v for k,v in old_focus.items() if k != 'scope'} == {k:v for k,v in new_focus.items() if k != 'scope'})
    req = read(PREVIOUS/'request.preview.json')
    changed = copy.deepcopy(req)
    body = json.loads(changed['messages'][1]['content']); body['output_contract'] = m.CONTRACT
    changed['messages'][1]['content'] = json.dumps(body, separators=(',', ':'))
    a, b = json.loads(req['messages'][1]['content']), json.loads(changed['messages'][1]['content'])
    a.pop('output_contract'); b.pop('output_contract')
    check('only_interface_contract_changed', a == b and req['messages'][0] == changed['messages'][0]
          and {k:v for k,v in req.items() if k!='messages'} == {k:v for k,v in changed.items() if k!='messages'})
    dump(out/'request.preview.json', changed)
    dump(out/'protocol.json', dict(created_at=time.time(), kind='local_mapping_qualification_only', model_calls=0,
        native_cases={name:dict(expected_O_H=expected, provenance='archived unedited response; retrospective diagnostic only' if name=='archived136_exact' else 'local hand-built control, not model success') for name, (_,expected) in fixtures.items()},
        native_scope='current9 + search36 + history115; unchanged RTL, oracle, ordinary and full151 requirements; 420OP+270BRANCH, no FP/critical unknown and required triggers',
        invariants='Label-bound selection; any causally detecting mapped property protects each required sample. Counts deduplicate by evidence identity, not assertion count. Every native failure checked, regardless of declared labels.',
        regression_tests='split/order/duplicates pass; lost held coverage/wrong labels/legal FP reject; historical-loss fixture O passes H rejects; exact136 response outcome not predetermined',
        old_results='Never modify or reinterpret research136 as accepted. Retrospective execution is not a new generated proposal, recovery, prospective O/H trial or independent validation.',
        stop='Run each sealed local fixture once; native failure stays failure; no model/network calls, no holdout access, no new seed or automatic proposal correction.',
        future='This seals the interface and local validation only. Any new remote pilot requires its own controller integration verification, protocol and explicit authorization; no old quota transfer.'))
    dump(out/'checks.json', checks); dump(out/'read_audit.json', sorted(opened))
    sources = list((ROOT/'scripts').glob('*.py')) + [PREVIOUS/'sealed.json', p.QUAL/'sealed.json']
    sources += [f for f in FAILED.rglob('*') if f.is_file()]
    dump(out/'source_bindings.json', {rel(f):digest(f) for f in sources})
    dump(out/'sealed.json', {f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    verify(out)
    print('SEALED140', len(checks), 'local checks;8 fixed native fixtures;model0', flush=True)


def run(prep, out):
    opened = p.q.guard(); verify(prep)
    out.mkdir(parents=True, exist_ok=False)
    baseline = read(PREVIOUS/'baseline_full.json')
    results = {}; records_by_name = {}; checks = []; raw_rows = 0
    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
        dump(out/'checks.json', checks)
        assert ok, name
    for name, spec in read(prep/'protocol.json')['native_cases'].items():
        candidate = read(prep/'fixtures'/name/'candidate.json')
        folder = out/name
        dump(folder/'candidate.json', candidate)
        ev, records = m.evaluate(candidate, folder/'native', baseline)
        n, again, _ = m.inspect_version(folder/'native', candidate, baseline); raw_rows += n
        check(name+'/raw_recompute', ev == again)
        decision = [ev['ordinary']['accepted'], ev['full_absolute']]
        if spec['expected_O_H'] is not None:
            check(name+'/expected_decisions', decision == spec['expected_O_H'])
        info = m.old.acceptance.inspect(p.x.paired.aggregate(records['history'], records['search'])['ledger'])
        results[name] = dict(O_H=decision, detections=len(info['detections']), misses=len(info['misses']),
            false_positives=len(info['false_positives']), unknown=len(info['unknown']),
            lost_detections=len(ev['lost_detection_ids']), new_false_alarms=len(ev['new_false_alarm_ids']),
            all_property_false_alarms=sum(len(v['false_alarms']) for v in ev['all_property_guards'].values()),
            focus12=ev['current_gate']['focus12']['phases'], provenance=spec['provenance'])
        records_by_name[name] = records
        dump(out/'results.json', results)
        print('NATIVE140', name, results[name], flush=True)
    # Compare evidence identities and counts, not unstable assertion IDs.
    canonical = records_by_name['split']
    for name in ('permuted', 'duplicate'):
        for cohort in canonical:
            a, b = m.old.acceptance.inspect(canonical[cohort]['ledger']), m.old.acceptance.inspect(records_by_name[name][cohort]['ledger'])
            for field in ('detections', 'misses', 'false_positives', 'unknown', 'triggers'):
                check(name+'/'+cohort+'/'+field+'_same_evidence', a[field] == b[field])
    for cohort in canonical:
        whole = read(p.QUAL/'native_controls/local_positive/native'/cohort/'result.json')
        check('whole_vs_split/'+cohort, whole['counts'] == canonical[cohort]['counts'])
    c = read(prep/'fixtures/permuted/candidate.json')
    r = records_by_name['permuted']['alignment']
    manifest = read(p.x.P/'focus.private.json')
    check('OP_a0_is_counted', any(a['id']=='a0' for a in c['assertions'] if a['obligations']==[m.OP]))
    check('legacy_position_filter_would_reject', not p.x.g.focus_gate(r, manifest)['accepted'] and m.focus_gate(r, manifest, c)['accepted'])
    for name, mutate in [
        ('unknown', lambda row: row['native'].update(attribution_status='unknown')),
        ('untriggered', lambda row: [a.update(trigger=False, causal_detection=False) for a in row['native']['assertions']]),
        ('undetected', lambda row: [a.update(causal_detection=False) for a in row['native']['assertions']]),
    ]:
        bad = copy.deepcopy(r)
        row = next(z for z in bad['ledger'] if z['sample'] == manifest['targets'][0]['sample'] and z['configuration']==manifest['targets'][0]['configuration'] and z['revision']=='before')
        mutate(row)
        check('local_gate_mutation/'+name, not m.focus_gate(bad, manifest, c)['accepted'])
    for name, mutate in [
        ('missing_assertion', lambda row: row['native']['assertions'].pop()),
        ('foreign_id', lambda row: row['native']['assertions'][0].update(id='a999')),
        ('duplicate_id', lambda row: row['native']['assertions'].append(copy.deepcopy(row['native']['assertions'][0]))),
    ]:
        bad = copy.deepcopy(r); row = next(z for z in bad['ledger'] if z['obligation']==m.OP); mutate(row)
        try: m.validate_ledger(bad, c)
        except ValueError: check('local_binding_mutation/'+name, True)
        else: check('local_binding_mutation/'+name, False)
    check('history_discrimination_preserved', results['historical_loss']['O_H']==[True,False] and results['historical_loss']['lost_detections']==141)
    check('FP_label_evasion_blocked', results['legal_false_alarm']['all_property_false_alarms'] > 0)
    files = sorted(out.rglob('compile.json'))
    executions = sorted(out.rglob('execute.json'))
    cost = dict(model_calls=0, formal_calls=0, native_compiles=len(files), native_executions=len(executions),
                compile_seconds=sum(read(f)['wall_seconds'] for f in files), execute_seconds=sum(read(f)['wall_seconds'] for f in executions),
                scope='Inline bench execution counted once, not again as smoke; no prior qualification costs included.')
    check('physical_cost', len(files)==len(executions)==48)
    verify(prep)
    dump(out/'cost.json', cost)
    dump(out/'outcome.json', dict(passed=True, checks=len(checks), native_rows_reaudited=raw_rows,
        local_fixture_versions=len(results), new_model_versions=0, new_prospective_acceptances=0,
        new_independent_tests=0, research136_unchanged=True, research133_read=False))
    dump(out/'read_audit.json', sorted(opened))
    lines=['# 义务映射多性质本地资格验收', '',
           '已移除新接口及两处OP触发门控中的位置假设；同一义务可以有多条性质，顺序不决定义务。总集合仍限2–6条，每条声明一个已知义务，必须包含两项义务。',
           '原research51组装/账本本已支持多对一；research54固定BRANCH的旧流程使research55/59用a0以外代表OP，research135/136据此限制槽位。旧脚本和旧结果没有修改。', '',
           '|对象|普通O/完整H|完整151检出|漏报|账本误报|关键unknown|丢失旧检出|', '|---|---|---:|---:|---:|---:|---:|']
    for name, v in results.items():
        lines.append(f"|{name}|{v['O_H']}|{v['detections']}/690|{v['misses']}|{v['false_positives']}|{v['unknown']}|{v['lost_detections']}|")
    lines += ['', 'split/permuted/duplicate为本地正对照，成功不计为模型成功；重复性质没有增加有效证据数。缺失保持周期、错误义务标签、全性质合法误报仍被拒绝，历史损失夹具仍为O接受/H拒绝。',
              'archived136_exact是旧模型响应逐字段不变的回顾性原生诊断。它不是新生成、恢复或前瞻试验，绝不追改research136接口失败。详情及原生波形见对应目录。',
              '每项义务的每条性质分别记录触发/违例证据；独立ISA判定和所有性质误报检查保持不变。原始RTL、当前9、搜索36、历史115及420OP+270BRANCH要求未改变。',
              f'本轮{len(checks)}项执行核查、{raw_rows}条原生记录复核；48次编译、48次实际仿真，模型0、形式化0、独立测试0。局部损坏账本/unknown检查是标明的程序负测试，不冒充原生结果。',
              '请求预览仅更改输出映射约定，其余开发信息、候选、模型和采样相同。封存本地协议与代码；尚未封存或启动新的远程先导。未来接入须同样替换完整执行及审计入口，不可只放宽JSON接口。旧条件性额度不用于本轮。', '',
              '复核封存（无模型调用）：', '```powershell', f'wsl -- python3 scripts/research140_mapping_qualification.py verify --prepared {rel(prep)}', '```',
              '重新执行本地原生资格（新输出目录）：', '```powershell', f'wsl -- python3 scripts/research140_mapping_qualification.py run --prepared {rel(prep)} --out deliverables/research140_native_recheck', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    dump(out/'source_bindings.json', {rel(prep/'sealed.json'):digest(prep/'sealed.json')})
    dump(out/'sealed.json', {f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file() and 'obj_dir' not in f.parts})
    print('QUALIFIED140', len(checks), 'checks', raw_rows, 'native rows; model0', flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('prepare','run','verify'))
    ap.add_argument('--prepared', type=Path); ap.add_argument('--out', type=Path)
    a=ap.parse_args()
    if a.action=='prepare': prepare(a.out.resolve())
    elif a.action=='run': run(a.prepared.resolve(), a.out.resolve())
    else: verify(a.prepared.resolve()); print('VERIFIED140; model0')
