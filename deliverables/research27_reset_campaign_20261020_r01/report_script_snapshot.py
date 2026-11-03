"""Terminal-only multi-run boundary-refinement campaign wrapper.

Run reports use research21_report. Campaign costs keep current runs,
qualifications and earlier stopped attempts separate. No model/RTL execution.
All declared runs must be terminal before any run report/test is opened.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
import shutil
import sys

import research21_report as report
import research20_campaign_report as accounting

ROOT = report.ROOT
read, dump, digest = report.read, report.dump, report.digest


def folder(value):
    path = report.portable(value).resolve()
    if ROOT not in path.parents or not path.is_dir():
        raise ValueError('Existing workspace directory required: ' + str(value))
    return path


def cost_row(label, cost):
    return '| ' + label + ' | ' + ' | '.join(str(cost.get(k,'unavailable')) for k in (
        'model_calls','prompt_tokens_known_subtotal','completion_tokens_known_subtotal',
        'usage_unavailable_calls','native_compile_calls','native_execute_calls','formal_calls')) + ' |'


def render(result):
    lines = ['# 背压解除边界与复位后无请求输出：本轮实测汇总', '',
        '本轮沿用已冻结真实模型断言集合，执行新模型细化；没有重新生成初始集合。'
        '真实 axis_fifo RTL 加明确人工输出边界故障，父案例分母为 1。完整五义务保护和原始历史 Bug 修复均未建立。', '',
        '服务请求、模型响应、接口组装、原生执行和接受分别记录；接口拒绝不是原生违例，'
        '中止后的部分回放不作为验收。有限仿真未发现问题不等于形式证明；历史保护保持仅限已回放证据。', '',
        '| 运行 | 终态 | 后端/模型 | 实际调用 | 新接受编辑 | 新目标链 | 独立测试 |',
        '|---|---|---|---:|---:|---|---|']
    for item in result['runs']:
        lines.append(f"| {item['run']} | {item['status']} | {', '.join(item['models'])} | "
            f"{item['cost']['total']['model_calls']} | {item['new_accepted_target_edits']} | "
            f"{item['target_chain'].get('passed')} | {item['independent_status']} |")
    lines += ['', '模型或后端不同不能作为受控算法消融比较；多次失败全部保留，不挑选成功结果。', '',
        '离线词法 schema 检查与服务后端 grammar 执行分开；历史后端拒绝约束后仍返回文本的情况，'
        '不能只当成模型未遵守格式。后端没有报错也仅表示该调用日志未见错误。', '',
        '## 两项重点问题的独立回放', '',
        '下表为各运行冻结后本批输入的去重统计，不混成一个共享测试集；旧公开测试进入开发数据后不得再次计为独立。', '']
    for item in result['runs']:
        lines += [f"### {item['run']}", '']
        support = item.get('backend_support') or {}
        if support.get('posthoc_diagnosis'):
            lines += ['后端历史诊断：', '```json',json.dumps(support['posthoc_diagnosis'],ensure_ascii=False,indent=2),'```','']
        if not item['independent_counts']:
            lines += ['未完成独立测试；不能记作零漏报。', '']; continue
        lines += ['| 候选 | 义务 | 目标行 | 检出 | 漏报 | 误报 | unknown | 触发 |', '|---|---|---:|---:|---:|---:|---:|---:|']
        for name,data in item['independent_counts'].items():
            for obligation in report.TARGETS:
                counts = data.get('by_obligation',{}).get(obligation,{})
                lines.append(f'| {name} | {obligation} | ' + ' | '.join(str(counts.get(k,'unavailable')) for k in (
                    'target_oracle_rows','detections','misses','false_positives','unknown','triggers')) + ' |')
        lines += ['', f"实际冻结哈希：`{item['frozen_hash']}`。后续归因 unknown："
            + str({k:v.get('later_attribution_unknown_raw') for k,v in item['independent_counts'].items()}) + '。', '',
            f"完整原始 SVA、提案原文、相邻样本、历史门控和接受/拒绝轨迹：[本运行报告](../{item['run'].split('/')[-1]}/report/REPORT.md)。", '']
        for edit in item['trace']['records']:
            if not edit['accepted']:
                continue
            history=edit['history']
            lines += [f"真实接受轨迹 `{edit['version']}`，目标 `{history.get('requested_obligations')}`：", '', '```systemverilog']
            lines += [a.get('property',str(a)) for a in (edit.get('edit') or {}).get('assertions',[])]
            lines += ['```', '', f"开发回放：`{history.get('before')}` → `{history.get('after')}`；"
                f"门控记录：`{history.get('decision')}`。独立结果须以上表为准，开发接受不自动表示独立通过。", '']
    lines += ['背压新增的数据保持性质没有增加 valid 保持检查；复位性质采用 $past 队列计数时，'
        '不能将有限样本通过视为与当前拍未取消事务存在性的规范等价。缺少排空目标分母也不能算保护通过。', '']
    lines += ['## 实际成本（互不重复）', '',
        '| 类别 | 模型请求 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | 用量未知请求 | 编译 | 执行 | 形式化 |',
        '|---|---:|---:|---:|---:|---:|---:|---:|',
        cost_row('本轮运行',result['current_cost']),cost_row('本轮资格检查',result['qualification_cost']),
        cost_row('此前中止尝试（单列）',result['preceding_cost']), '',
        '编译 smoke 执行包含在执行次数内。不同类别目录重复会被拒绝；不递归加入运行报告内的来源成本。'
        '输入/输出用量缺失保持不可用。模型管理/服务加载和实际生成分开，不将模型服务可用等同于生成成功。', '',
        '## 未完成与范围限制', '',
        '- 完整五义务语义保护、全局无退化及形式证明未建立。',
        '- 本轮没有受控四组消融或搜索基线优势结论。',
        '- stat 及原始 FIFO presented 仍 unknown；仅人工边界故障工程案例计入当前分母。',
        '- 独立失败若用于以后修改，须转开发数据并另建新独立测试。', '']
    return '\n'.join(lines)


def build(args):
    runs = [folder(p) for p in args.runs]
    qualifications = [folder(p) for p in args.qualification]
    preceding = [folder(p) for p in args.preceding]
    all_paths = runs + qualifications + preceding
    if len(set(all_paths)) != len(all_paths):
        raise ValueError('A physical directory cannot be charged twice')
    # Check all terminal states before opening reports that contain tests.
    for run in runs + preceding:
        report.terminal(run)
    out = report.portable(args.out).resolve()
    if ROOT not in out.parents or out in all_paths:
        raise ValueError('Separate workspace campaign output required')
    if args.generate_run_reports:
        old_argv = sys.argv
        try:
            for run in runs:
                sys.argv = ['research21_report.py','--run',str(run)]
                report.main()
                sys.argv = ['research21_report.py','--run',str(run),'--verify']
                report.main()
        finally:
            sys.argv = old_argv
    records, references, underlying = [], {}, {}
    def reference(path):
        key = path.resolve().relative_to(ROOT).as_posix()
        if key not in references:
            references[key] = digest(path)
    def underlying_reference(key, expected):
        if key in underlying and underlying[key] != expected:
            raise ValueError('Conflicting archived hash: ' + key)
        underlying[key] = expected
    for run in runs:
        result = read(run/'report/results.json')
        seal = read(run/'report/verification.json',{})
        if not result or not seal.get('passed'):
            raise ValueError('Verified terminal report required: ' + str(run))
        for name in ('results.json','REPORT.md','verification.json','manifest.json','report_script_snapshot.py'):
            reference(run/'report'/name)
        reference(run/'outcome.json')
        for rel,expected in read(run/'report/manifest.json',{}).items():
            underlying_reference((run/rel).relative_to(ROOT).as_posix(),expected)
        for check in (report.source_checks(result.get('lineage',{})) + result.get('development_provenance',{}).get('file_checks',[])
                + result.get('inherited_feedback',{}).get('file_checks',[]) + result.get('backend_support',{}).get('linked_log_checks',[])):
            underlying_reference(check['path'],check['expected'])
        costs = result['cost']
        records.append(dict(run=run.relative_to(ROOT).as_posix(),status=result['status'],
            models=sorted({str(c.get('model')) for c in costs['model_calls']}),cost=costs,
            native_status_counts=costs['native_status_counts'],
            new_accepted_target_edits=result['trace']['accepted_new_target_edits'],
            target_chain=result['target_chain'],frozen_hash=(read(run/'core/freeze.json',{}) or {}).get('candidate_sha256'),
            independent_status=result['independent']['status'],independent_counts=result['independent_deduplicated'],
            prompt_evidence=result.get('prompt_evidence'),trace=result['trace'],
            backend_support=result.get('backend_support'),
            missing_evidence=result['missing_evidence'],whole_parent_case=result['whole_parent_case']))
    def audits(paths):
        results = []
        for path in paths:
            files = report.base.artifacts(path)
            cost = report.previous.extended_cost_audit(path, files)
            # Hash only actual cost/status source records here. Full current
            # run manifests are already inherited without repeated full scans.
            tracked = {path/c['path'] for c in cost['model_calls'] + cost['native_commands']}
            for c in cost['model_calls']:
                tracked.update(p for p in (path/c['path']).parent.glob('*.json'))
            tracked.update(p for name in ('summary.json','result.json','qualification.json','outcome.json','protocol.json','model_cost.json') if (p:=path/name).is_file())
            for artifact in tracked:
                reference(artifact)
            results.append(dict(path=path.relative_to(ROOT).as_posix(),cost=cost,
                outcome=read(path/'outcome.json'),result=read(path/'summary.json',read(path/'qualification.json',read(path/'result.json'))),
                scope='Actual physical costs only; no inference of successful generation from a request.'))
        return results
    qualification_records, preceding_records = audits(qualifications), audits(preceding)
    result = dict(generated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),runs=records,
        qualifications=qualification_records,preceding_attempts=preceding_records,
        current_cost=accounting.sum_cost([r['cost']['total'] for r in records]),
        qualification_cost=accounting.sum_cost([r['cost']['total'] for r in qualification_records]),
        preceding_cost=accounting.sum_cost([r['cost']['total'] for r in preceding_records]),
        engineering_parent_count=1,whole_parent_case_passed=False,
        scope='Separate run evidence, not controlled ablation. Source costs never recursively added.')
    out.mkdir(parents=True,exist_ok=True)
    dump(out/'results.json',result)
    (out/'SUMMARY.md').write_text(render(result),encoding='utf-8')
    shutil.copy2(__file__,out/'report_script_snapshot.py')
    dump(out/'manifest.json',dict(references=references,underlying=underlying,
        verification='--verify hashes each unique path once; current run manifest inheritance avoids rehashing while building.'))
    print(json.dumps(dict(current=result['current_cost'],qualifications=result['qualification_cost'],preceding=result['preceding_cost'],summary=str(out/'SUMMARY.md'))))


def verify(out):
    out = folder(out)
    manifest = read(out/'manifest.json',{})
    entries = {}
    for category in ('references','underlying'):
        for rel,expected in manifest.get(category,{}).items():
            if rel in entries and entries[rel]!=expected:
                raise ValueError('Conflicting campaign hash')
            entries[rel]=expected
    failures = []
    for rel,expected in entries.items():
        path = (ROOT/rel).resolve()
        if ROOT not in path.parents:
            raise ValueError('Unsafe campaign manifest path')
        actual = digest(path) if path.is_file() else None
        if actual != expected:
            failures.append(dict(path=rel,expected=expected,actual=actual))
    result = dict(passed=bool(entries) and not failures,checked_unique_files=len(entries),failures=failures,
        scope='One actual hash pass per unique referenced file; not a functional success claim.')
    dump(out/'verification.json',result)
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--runs',type=Path,nargs='*',default=[])
    parser.add_argument('--qualification',type=Path,action='append',default=[])
    parser.add_argument('--preceding',type=Path,action='append',default=[])
    parser.add_argument('--generate-run-reports',action='store_true')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    if args.verify:
        return verify(args.out)
    if not args.runs:
        parser.error('--runs is required for generation')
    build(args)


if __name__=='__main__':
    main()
