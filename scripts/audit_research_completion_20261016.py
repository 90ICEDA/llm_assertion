"""Read-only historical checks; write a new dated acceptance audit only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', default='deliverables/completion_audit_20261016_r01')
    args = parser.parse_args()
    out = (ROOT / args.out).resolve()
    if not out.is_relative_to(ROOT / 'deliverables'):
        raise ValueError('output must be under deliverables')
    out.mkdir(parents=True, exist_ok=False)

    def dump(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    checks = []
    for rel in ('research_integration_20261014_r01/delivery_manifest.json',
                'research15_integration_20261015_r01/delivery_manifest.json',
                'historical_record_recovery_20261015_r01/manifest.json'):
        for name, expected in read(ROOT/'deliverables'/rel).items():
            p = ROOT/name
            actual = digest(p) if p.is_file() else None
            checks.append(dict(manifest=rel, path=name, expected=expected,
                               actual=actual, passed=actual == expected))
    dump('historical_integrity.json', checks)

    from research15_acceptance_qualification import run as gate
    from research15_evidence_qualification import run as adapter
    from research15_acceptance import inspect
    qualifications = dict(gate=gate(), adapter=adapter())
    dump('qualification_rerun.json', qualifications)
    native = ROOT/'deliverables/research15_native_20261015_r01'
    integration = ROOT/'deliverables/research15_integration_20261015_r01'
    summary = read(native/'summary.json')
    versions = []
    for item, name in zip(summary['versions'], ('original','semantic_repair','initial_temporal_continuation')):
        record = inspect(read(integration/'native_readjudication'/name/'ledger.json')['ledger'])
        counts = {k:len(record[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')}
        call = native/'model_calls'/item['model_call']
        cohort = ROOT/item['evidence_directory']
        files = [call/n for n in ('request.json','response.raw.json','response.stream.jsonl',
                                  'candidate.sva','candidate.json','result.json')]
        files += [cohort/'compiled'/n for n in ('tb.sv','compile.json','tool_version.log')]
        files += [cohort/v/n for v in ('correct','corrupt')
                  for n in ('execute.json','execute.log','wave.vcd','oracle.json','replay.json')]
        raw = read(cohort/'correct/result.json')
        versions.append(dict(model_call=item['model_call'], counts=counts,
            summary_matches=counts == item['counts'], accepted=item['accepted'],
            native_status={k:raw[k] for k in ('engine','compile_status','tool_support_status',
                         'execution_status','trigger_status','property_status','formal_proof')},
            files={str(p.relative_to(ROOT)):digest(p) if p.is_file() else None for p in files}))
    dump('native_verification.json', versions)

    search = ROOT/'deliverables/research15_search_20261015_r01/fixed_initial_negative'
    methods = read(search/'summary.json')
    pairs = read(ROOT/'deliverables/research_search_20261014_r01/pair_results.json')
    absence = {name:not (native/name).exists() for name in
               ('shared_initial.json','all_arms_freeze.json','arms','holdout/summary.json')}
    matrix = read(integration/'completion_matrix.json')
    for row in matrix:
        row['audit_date'] = '2026-10-16'
    dump('completion_matrix.json', matrix)
    result = dict(audit_date='2026-10-16', scope='Existing artifacts and current code inspection; no new model or RTL simulation',
        historical_hash_checks=len(checks), historical_hash_checks_passed=all(c['passed'] for c in checks),
        qualification_checks=sum(len(r['tests']) for r in qualifications.values()),
        qualifications_passed=all(r['passed'] for r in qualifications.values()),
        native_summary_matches=all(v['summary_matches'] for v in versions),
        native_required_files_present=all(h for v in versions for h in v['files'].values()),
        accepted_model_versions=sum(v['accepted'] for v in versions),
        actual_search_queries=sum(r['queries'] for r in methods),
        actual_search_native_replays=sum(r['native_replays'] for r in methods),
        treatment_witness=read(search/'treatment_witness.json'),
        old_candidate_pairs=len({r['pair_id'] for r in pairs}), old_pair_method_rows=len(pairs),
        expected_missing_execution_artifacts=absence,
        original_parent_status=read(integration/'parent_status.json'),
        historical_costs=read(integration/'physical_cost_ledger.json')['model_totals'],
        historical_record_recovery=read(ROOT/'deliverables/historical_record_recovery_20261015_r01/recovery_status.json'),
        new_model_calls=0, new_native_simulation_calls=0, new_formal_calls=0,
        end_to_end_success_chain_established=False)
    dump('audit.json', result)
    code_names = ('research15_acceptance.py','research15_evidence.py','research15_native_interface.py',
                  'research15_native_models.py','research_native_model.py','research15_native_experiment.py',
                  'research15_search_experiment.py','research15_search_runtime.py','research15_pipeline.py')
    dump('inspected_code.json', {name:digest(ROOT/'scripts'/name) for name in code_names})
    lines = ['# 2026-10-16 任务完成情况核查', '',
        '**整体未完成；完整成功证据链尚未成立。** 本轮核查旧产物、重算已校正证据库统计，并重跑接受门/适配器逻辑检查；没有新调用模型或执行RTL实验。', '',
        f"完整性：{len(checks)}项历史清单校验，全部通过={result['historical_hash_checks_passed']}；逻辑资格检查{result['qualification_checks']}项通过。3版模型产物及原生执行必需文件齐备={result['native_required_files_present']}。",
        '', '| 要求 | 完成状态 | 证据及边界 |', '|---|---|---|']
    for row in matrix:
        lines.append(f"| {row['requirement']} | {row['status']} | {row['result']} |")
    lines += ['', '## 关键实测结果', '',
        '真实本地qwen2.5-coder:7b-instruct生成及两次修改均被Verilator原生编译执行。原始/语义修改/时序修改合法误报分别59/2/59，均拒绝；首版3条旧检出已经重判为归因unknown。计数单位为义务×采样周期，不是独立缺陷。',
        '四法实际48查询、240回放，每法12查询；均发现相同合法误报类，独立有效漏报缺口为0，treatment_witness=null。候选分歧臂因只有单property退化为探索。不能据此声称契约法优于基线。',
        '旧11对候选保留44个pair×method结果行，可逐项追踪新增缺口；其36/37/43/43为受限过程诊断结果，不是本轮原生SVA比较，也不等于独立父Bug数量。stat部分仍受本地规格和来源限制。',
        '复杂FIFO实测Depth2及Depth5（实际RAM容量8）、pipeline0/1，包含握手、背压、重叠、复位取消和人工丢失/重复/残留故障。属于有限工程验证；原始presented缺陷仍没有确认见证。',
        'Ibex #166原始decoder前后各1374检查：before423报警/42事务，after0。#54新增119编码中32条HINT前版违例、后版0，其余87控制通过。这些使用手写原生SVA/独立oracle，未进入LLM细化；不是全核或形式证明。', '',
        '## 实现仍有边界', '',
        '模型传输层有可配置接口，但只有本地Ollama路径实测，当前主流程仍固定该模型及参数。远程接口不能标为验证完成。原生前端仅允许单个显式|->或|=>、不支持##序列、限制前件时序函数，并最多5条SVA；这是受限原生接口，不是完整SVA语言支持。',
        '接受门检查历史记录身份、新误报、丢失检出/触发、当前缺口修复，并生成义务映射。25项逻辑检查不替代真实模型集合修改验收；触发保留只对回放证据成立，不能证明全局无退化。',
        '四臂及holdout代码存在，但没有shared_initial、四臂冻结文件和独立测试汇总。当前流程的公共初始资格失败、严格搜索处理见证为空，故不能运行到有效消融和独立结论。', '',
        '## 数据、成本及历史记录', '',
        '最近3次完整模型调用输入23274、输出272 tokens，约391.51秒、无重试；是20261015这3次的成本，不是全部历史累计。形式化调用0。20261014另有取消调用最终usage不可用，不能按零合并。',
        '旧开发观测不能改名为独立测试。尚无最终接受集合，因此无冻结后学习断言的独立测试结论；Ibex新向量是手写性质复现，不能代替该项。',
        '历史补录已恢复旧适配器版本和FIFO精确提交48ff7a7e2ef782cf778d47910cf85835c64b1bce。根Git提交仍不可用；取消调用usage部分缺失；stat上游映射未验证。历史补录不改变实验成功状态。',
        '六原始父Bug完整原生LLM流程成功为0/6：onehot仅回归；fifo原始目标无见证；filter原生全义务验收未建立；stat来源/规格未确认；spill仅局部collision-empty有证据；intr掩码/时序未确认。0/6表示尚未证实完整成功，并非六个都已完成实验且失败。', '',
        '## 剩余验收顺序', '',
        '1. 根据实际误报修正模型生成接口和采样语义，取得通过公共资格的真实初始SVA。',
        '2. 在该固定候选上获取合法对照通过、目标义务违例且候选漏检的新搜索见证。',
        '3. 实跑四组消融，隔离搜索处理信息，保留真实修改/拒绝和集合历史回放。',
        '4. 冻结接受集合后才生成并执行新独立测试，按父Bug和义务分别统计。',
        '5. 将可靠Ibex案例接入同一LLM流程，保留stat/FIFO presented等unknown，不剔除困难案例。', '',
        '本次核查命令（仓库根目录，输出目录必须未使用）：', '',
        '```powershell', 'wsl -- python3 scripts/audit_research_completion_20261016.py --out deliverables/completion_audit_20261016_r02', '```', '',
        '实验统一入口仍为scripts/research15_pipeline.py；旧集成报告中的audit/qualify/report会写旧目录，不用于本次只读复核。后续模型、搜索、历史实验应指定新的--run目录。', '',
        '详细证据：audit.json、native_verification.json、historical_integrity.json、qualification_rerun.json、completion_matrix.json。旧报告位置：../research15_integration_20261015_r01/REPORT.md；历史补录：../historical_record_recovery_20261015_r01/REPORT.md。', '']
    (out/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    shutil.copy2(__file__, out/'audit_script_snapshot.py')
    dump('manifest.json', {p.name:digest(p) for p in sorted(out.iterdir()) if p.is_file()})
    assert result['historical_hash_checks_passed'] and result['qualifications_passed']
    assert result['native_summary_matches'] and result['native_required_files_present']
    print(json.dumps({k:result[k] for k in ('historical_hash_checks','qualification_checks',
        'native_summary_matches','accepted_model_versions','actual_search_queries',
        'actual_search_native_replays','old_candidate_pairs','old_pair_method_rows',
        'expected_missing_execution_artifacts')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
