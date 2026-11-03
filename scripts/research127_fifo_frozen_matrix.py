"""Read-only inventory of archived complex-FIFO frozen acceptance evidence.

Never supplies test outcomes to a model, selector or acceptance rule. Counts
are recomputed from archived ledgers, not new native simulation. Discovery is
explicit and includes failures; unmatched records stay in the inventory.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import research17_loop as loop
from research30_ablation_report import metrics

ROOT, read, dump = loop.ROOT, loop.read, loop.dump
OBLIGATIONS = tuple(loop.model.SPECS)
PATTERNS = ('*/independent/summary.json', '*/*/independent/summary.json',
            '*/evaluation/*/independent/summary.json',
            '*/independent_by_hash/*/independent/summary.json',
            '*/arms/*/independent/summary.json', '*/arms/*/*/independent/summary.json')


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rel(path): return path.relative_to(ROOT).as_posix()


def freeze_files(root, location, expected):
    candidates = [location / 'core/frozen_candidate.json']
    for pattern in ('core/frozen_candidate.json', '*/core/frozen_candidate.json',
                    'arms/*/core/frozen_candidate.json', 'arms/*/*/core/frozen_candidate.json'):
        candidates.extend(root.glob(pattern))
    found = []
    for f in sorted(set(candidates)):
        if f.is_file() and loop.sha(read(f)) == expected:
            seal = f.with_name('freeze.json')
            if seal.exists() and read(seal).get('candidate_sha256') == expected:
                found.append((f, seal))
    return found


def run(out):
    files = sorted(set(f for pattern in PATTERNS for f in (ROOT / 'deliverables').glob(pattern)))
    out.mkdir(parents=True, exist_ok=False)
    inventory, versions, matrix, bindings = [], [], [], {}
    rows_audited = 0
    def bind(f): bindings[rel(f)] = digest(f)
    for f in files:
        summary = read(f)
        # Non-FIFO reports are inventoried, never coerced into this schema.
        if 'all_five_pass_on_first_attributed_evidence' not in summary:
            inventory.append(dict(summary=rel(f), status='different_schema_not_in_five_obligation_matrix'))
            continue
        root = ROOT / 'deliverables' / f.relative_to(ROOT / 'deliverables').parts[0]
        location = f.parent.parent
        needed = [f.parent / n for n in ('combined.json', 'split.json', 'drain_assessment.json')]
        if any(not q.exists() for q in needed):
            inventory.append(dict(summary=rel(f), status='missing_evidence', missing=[rel(q) for q in needed if not q.exists()]))
            continue
        combined, split, drain = map(read, needed)
        h = split.get('frozen_hash')
        freezes = freeze_files(root, location, h)
        if not freezes:
            inventory.append(dict(summary=rel(f), candidate_hash=h, status='unresolved_freeze_binding'))
            continue
        recomputed = metrics(combined)
        assert recomputed == summary['metrics'], rel(f)
        assert loop.counts(combined['group']) == combined['counts'], rel(f)
        finite = bool(combined['healthy'] and drain['passed'] and all(v['detections'] > 0 and v['triggers'] > 0
            and not any(v[k] for k in ('misses','false_positives','unknown')) for v in recomputed['obligations'].values()))
        assert finite == summary['all_five_pass_on_first_attributed_evidence'], rel(f)
        cases = split['boundary_cases'] + split['drain_cases']
        by_id = {c['id']: c for c in cases}
        assert len(cases) == summary['scenarios']
        info = loop.inspect(combined['group']['ledger'])
        assert not info['errors'], rel(f)
        rows_audited += len(info['rows'])
        exclusions = combined['group'].get('exclusions', [])
        tag = rel(location).removeprefix('deliverables/')
        for q in [f] + needed + [q for pair in freezes for q in pair]: bind(q)
        configs = sorted({(c['depth'], c['pipeline']) for c in cases})
        version = dict(version=tag, candidate_hash=h, candidate_file=rel(freezes[0][0]),
            freeze_files=[rel(pair[1]) for pair in freezes], summary=rel(f),
            independent_batch_hash=loop.sha(cases), scenarios=len(cases), configurations=configs,
            archived_finite_pass=finite, counts=recomputed['counts'],
            freeze_order_claim=split.get('created_after_freeze'),
            scope='Archived independent-at-the-time results; report only. No claim these data remain unseen for future experiments.')
        versions.append(version)
        inventory.append(dict(summary=rel(f), status='bound_and_recomputed', candidate_hash=h))
        for config in configs:
            ids = {c['id'] for c in cases if (c['depth'],c['pipeline']) == config}
            for ob in OBLIGATIONS:
                selected = {k for k,r in info['rows'].items() if r['scenario_id'] in ids and r['obligation'] == ob}
                counts = {k:len(selected & info[k]) for k in ('detections','misses','false_positives','unknown','triggers')}
                exposure = counts['detections'] + counts['misses']
                native_fail = sum(any(info['rows'][k]['native'].get(field) != value for field,value in
                    (('compile','ok'),('support','supported'),('execution','ok'))) for k in selected)
                excluded = [r for r in exclusions if r.get('scenario_id') in ids and r.get('obligation') == ob]
                evidence = {kind:sorted(selected & info[kind]) for kind in ('detections','misses','false_positives','unknown')}
                status = ('failed' if counts['misses'] or counts['false_positives'] else
                          'unknown' if counts['unknown'] or native_fail else
                          'not_exposed' if not exposure else
                          'untriggered' if not counts['triggers'] else 'finite_first_attribution_pass')
                mechanism_counts = Counter(by_id[info['rows'][k]['scenario_id']]['mode'] for k in selected & (info['detections'] | info['misses']))
                row = dict(version=tag, candidate_hash=h, depth=config[0], pipeline=config[1], obligation=ob,
                    actual_target_exposure=exposure, exposure_mechanisms=dict(mechanism_counts), **counts,
                    later_attribution_unknown=len(excluded), native_unhealthy_rows=native_fail, status=status,
                    evidence=evidence, exclusion_samples=[r.get('evidence_id') for r in excluded[:3]])
                matrix.append(row)
        # All rows, including absent exposure cells, must remain in denominator.
        local = [r for r in matrix if r['version'] == tag]
        assert sum(r['detections'] for r in local) == recomputed['counts']['detections']
        assert sum(r['misses'] for r in local) == recomputed['counts']['misses']
        assert sum(r['unknown'] for r in local) == recomputed['counts']['unknown']
        assert sum(r['later_attribution_unknown'] for r in local) == recomputed['counts']['later_attribution_unknown']
        print('MATRIX127', tag, h[:12], finite, len(configs), flush=True)
    dump(out / 'inventory.json', dict(discovery_patterns=PATTERNS, records=inventory,
        scope='All discovered compatible five-obligation frozen-summary records, including failed/fallback versions. Other formats listed, not silently excluded.'))
    dump(out / 'versions.json', versions); dump(out / 'matrix.json', matrix)
    dump(out / 'bindings.json', bindings)
    for name,h in bindings.items(): assert digest(ROOT / name) == h
    audit = dict(passed=True, physical_batches=len(versions), unique_candidate_hashes=len({v['candidate_hash'] for v in versions}),
        matrix_cells=len(matrix), row_counts_recomputed=rows_audited, source_files_unchanged=len(bindings),
        status_counts=dict(Counter(r['status'] for r in matrix)), native_executions=0, model_calls=0,
        new_accepted_versions=0, new_independent_batches=0, raw_native_reaudit=False,
        scope='Recomputed archived ledgers and summaries; not new simulation, new independent validation, or population success estimate.')
    dump(out / 'audit.json', audit)
    lines = ['# 复杂 FIFO 冻结验收矩阵（只读历史盘点）', '',
        f'核验 {len(versions)} 个物理测试批次、{audit["unique_candidate_hashes"]} 个不同冻结哈希；{len(matrix)} 个版本×参数×义务单元。包括失败和回退版本。',
        '本轮模型调用0、原生执行0、新接受版本0、新独立测试0。重算已有证据账本，未把归档结果用于 research123 选择或反馈；不重新声称旧测试对未来实验仍独立。', '',
        '对象为 axis_fifo 实际 RTL 加明确人工故障。通过仅指该批首个可归因证据；后续归因 unknown 保留，不能称全局完整保护或形式化证明。', '',
        '|版本|冻结哈希前12位|检出/曝光|误报|关键unknown|后续unknown|归档有限通过|',
        '|---|---|---:|---:|---:|---:|---|']
    for v in versions:
        c = v['counts']; lines.append(f'|{v["version"]}|{v["candidate_hash"][:12]}|{c["detections"]}/{c["detections"]+c["misses"]}|{c["false_positives"]}|{c["unknown"]}|{c["later_attribution_unknown"]}|{v["archived_finite_pass"]}|')
    lines += ['', '逐参数全部义务见 MATRIX.md / matrix.json；0曝光标为 not_exposed，不随总体通过继承为通过。原生执行异常、关键unknown与后续归因unknown分别记录。',
        '没有按收益选择版本；无法绑定冻结的记录和其他格式见 inventory.json。相同哈希、重复测试或共同测试不构成独立成功样本，不能将本表比例用作模型生成／恢复成功率。', '',
        '复核命令：', '```powershell', 'wsl -- python3 scripts/research127_fifo_frozen_matrix.py --out deliverables/research127_fifo_matrix_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    lines = ['# 冻结版本—参数—义务—曝光—失败/unknown', '',
        '|版本/哈希|Depth/Pipeline|义务|检出/曝光|触发|误报|漏报|关键unknown|后续unknown|状态|',
        '|---|---|---|---:|---:|---:|---:|---:|---:|---|']
    for r in matrix:
        lines.append(f'|{r["version"]} / {r["candidate_hash"][:12]}|{r["depth"]}/{r["pipeline"]}|{r["obligation"]}|{r["detections"]}/{r["actual_target_exposure"]}|{r["triggers"]}|{r["false_positives"]}|{r["misses"]}|{r["unknown"]}|{r["later_attribution_unknown"]}|{r["status"]}|')
    (out / 'MATRIX.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('AUDIT127', audit, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument('--out', type=Path, required=True)
    run(ap.parse_args().out.resolve())
