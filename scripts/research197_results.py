"""R197 reports retain historical controls, isolation arms, and unknown costs."""
import argparse
import ast
from collections import Counter
import copy
from html import escape
import inspect
import json
from pathlib import Path
from research195_refinement_adapter import clone
from research194_refinement_runner import read,dump
from research194_report import trajectories,aggregate,cross_design_table,table


def analysis_runtime():
    m=clone('research196_results')
    tree=ast.parse(inspect.getsource(m.search_analysis))
    class Baselines(ast.NodeTransformer):
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='paid' for t in node.targets):node.value=ast.Name(id='protocol',ctx=ast.Load())
            return self.generic_visit(node)
    tree=Baselines().visit(tree);ast.fix_missing_locations(tree);exec(compile(tree,__file__,'exec'),m.__dict__)
    m.GROUPS=copy.deepcopy(m.GROUPS);m.GROUPS['T']={a:'isolation_'+a for a in ('F','P','T')}
    return m


def build(prepared,execution,acceptance,cost,out):
    from research197_prepare import verify
    p=verify(prepared);execution,acceptance,cost,out=map(Path,(execution,acceptance,cost,out))
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen' or read(acceptance/'outcome.json')['status']!='completed':raise ValueError('unfinished_experiment')
    rr=trajectories(execution);aa=read(acceptance/'results.json');m=analysis_runtime()
    if len(rr)!=66:raise ValueError('frozen_population')
    arm_by_id={e['id']:e.get('arm') for e in p['entries']}
    # Re-label only in-memory analysis copies. Frozen records stay untouched.
    for row in rr:
        arm=arm_by_id.get(row.get('registered_id'))
        if arm:row.update(search_strategy='isolation',strategy=arm)
    for row in aa:
        arm=arm_by_id.get(row['id'])
        if arm:row.update(search_strategy='isolation',strategy=arm)
    search=m.search_analysis(p,execution);paired=m.paired(aa)
    tables=dict(search=search['table'],refinement=aggregate(rr,[(f'R{i}','S0',f'R{i}') for i in range(4)],aa),
        isolation=aggregate(rr,[(a,'isolation',a) for a in ('F','P','T')],aa),
        ablation=aggregate(rr,[('A0','S0','R1'),('A1','S3','R1'),('A2','S0','R3'),('A3','S3','R3')],aa),
        cross_design=cross_design_table(aa),paired=paired['summary'],interactions=paired['interactions'])
    attempts=[];operations=[];paths=[];calls=[]
    for e in p['entries']:
        folder=execution/e['id']/'refinement';rounds=m.optional(folder/'rounds.json',[]);stages=[]
        for index in range(1,e['max_rounds']+1):
            record=next((r for r in rounds if r['round']==index),None)
            attempts.append(dict(id=e['id'],arm=e.get('arm'),round=index,classification=m.classify_round(record) if record else 'not_attempted',
                stage=record.get('stage') if record else None,terminal=read(folder/'outcome.json').get('termination_reason')))
            if record:
                stages.append(record.get('stage'));edit=m.optional(folder/f'round{index:02}/model_edit.json',None)
                operations.append(dict(id=e['id'],round=index,stage=record.get('stage'),status=record['status'],
                    classification=m.classify_round(record),edit=edit,decision=record.get('decision')))
        paths.append(dict(id=e['id'],actual_stages=stages,full_three_stage_path=all(s in stages for s in ('local','compose','regenerate'))))
        for path in folder.glob('round*/model_call/result.json'):calls.append(dict(id=e['id'],**read(path)))
    ledger=read(execution/'ledger.json');attempt_files=list(execution.glob('*/*/*/refinement/round*/model_call/attempt.json'))
    missing=[str(path) for path in attempt_files if not (path.parent/'result.json').exists()]
    summary=dict(status='registered_experiment_executed_not_necessarily_accepted',frozen_trajectories=len(rr),main_trajectories=48,isolated_trajectories=18,
        physical_dispatch_attempts=len(attempt_files),reserved_calls=len(ledger),maximum_calls=p['maximum_model_calls'],missing_result_records=missing,
        known_tokens=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in calls),
        unknown_usage_calls=len(missing)+sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
        call_statuses=dict(Counter(c['status'] for c in calls)),attempt_classifications=dict(Counter(r['classification'] for r in attempts)),
        accepted_local=sum(r['stage']=='local' and r['status']=='accepted' for r in operations),actual_full_fallback_trajectories=sum(r['full_three_stage_path'] for r in paths),
        independent_version_fault_records=len(aa),independent_unknown_records=sum(bool(r['unknown_records']) for r in aa),
        independent_full_scope_pass_records=sum(r['full_planned_transaction_scope_pass'] for r in aa),
        limits=p['limits']+['Two historical repairs and one explicitly injected ID-queue defect; no universal or formal correctness claim.',
          'Main R3 includes localization, local editing, history and composition. F/P/T separately isolates prompt and edit-permission effects.',
          'Handwritten qualification and fallback probes are excluded from model result counts.',
          'A missing actual fallback branch is reported as not attempted, even when its handwritten qualification passed.'])
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('summary',summary),('tables',tables),('search_analysis',search),('paired_analysis',paired),('trajectory_index',rr),
            ('attempt_matrix',attempts),('operation_audit',operations),('fallback_paths',paths),('calls',calls),
            ('cost_analysis',read(cost/'analysis.json')),('request_diagnostics',m.request_diagnostics(execution))]:dump(out/(name+'.json'),value)
    body=['<!doctype html><meta charset="utf-8"><title>REGuard R197 results</title><style>body{font:15px/1.6 system-ui;max-width:1300px;margin:32px auto;padding:20px}.scroll{overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #bbc9d2;padding:7px}pre{white-space:pre-wrap;background:#edf3f7;padding:16px}</style>',
        '<h1>REGuard R197：真实窗口、在途匹配与历史修复</h1><p>实验执行完成不等于验收通过；模型结果与手写资格验证分别统计。</p>',
        '<p><a href="../reguard_mechanisms_20261104_r05/report.html">此前统一报告</a> · <a href="../research197_case_cards_20261104_r01/cards.html">本轮机制案例</a> · <a href="cost_analysis.json">实际共同成本截面</a></p>',
        '<pre>'+escape(json.dumps(summary,ensure_ascii=False,indent=2))+'</pre>']
    for key in ('search','refinement','isolation','ablation','cross_design','paired'):
        rows=tables[key];body+=['<h2>'+escape(key)+'</h2>',table(rows,[(k,k) for k in rows[0]]) if rows else '<p>No eligible records.</p>']
    body+=['<p><a href="operation_audit.json">实际操作与拒绝原因</a> · <a href="attempt_matrix.json">逐轮未尝试/失败/无收益分类</a> · <a href="fallback_paths.json">真实模型回退覆盖</a></p>']
    (out/'report.html').write_text('\n'.join(body),encoding='utf-8')
    print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for k in ('prepared','execution','acceptance','cost','out'):parser.add_argument('--'+k,required=True,type=Path)
    a=parser.parse_args();build(a.prepared,a.execution,a.acceptance,a.cost,a.out)
