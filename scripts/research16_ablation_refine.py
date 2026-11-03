"""Prospective uniform prompt-interface correction after syntax-only failures.

Reuse the qualified initial and actual search acquisition; no test outcomes
have been generated or consumed when this cohort is prepared.
"""
import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
import research16_ablation as run


def structured_existing(candidate):
    return dict(assertions=[dict(antecedent=a['derived_antecedent'],consequent=a['consequent'],
        timing='same_sample' if a['derived_delay']==0 else 'next_sample',obligations=a['obligations'],
        reason=a.get('reason','')) for a in candidate['assertions']])


def request(ctx):
    ctx=copy.deepcopy(ctx)
    ctx['current_assertions']=structured_existing(ctx['current_assertions'])
    task=('Return ONLY JSON with assertions. Each item has antecedent, consequent, timing, obligations, reason. '
          'Antecedent and consequent are Boolean expressions, NEVER SVA properties. '
          'Do not put |->, |=>, ##, assert, or clock syntax inside either expression. '
          'timing must be same_sample or next_sample. '
          'The currently accepted assertion is supplied in exactly this schema. '
          'If the issue list is empty, return exactly that assertion without adding anything. '
          'If the issue list is nonempty, preserve existing protection and add complementary assertions ONLY for the listed missing obligations. '
          'Do not add assertions for unreported obligations. Use at most three assertions. '
          'Return the complete set, not a patch. The feedback below is the entire evidence available to this proposal.')
    final=dict(task=task,current_assertions=ctx['current_assertions'],
        issues=ctx['issues'],counts=ctx['counts'])
    return dict(model=run.models.MODEL,stream=True,format='json',options=run.models.OPTIONS,
        messages=[dict(role='system',content='You revise structured Boolean-and-timing assertions. Obey the final task exactly. Never embed temporal operators in Boolean expression fields. Return JSON only.'),
                  dict(role='user',content=json.dumps(ctx)),dict(role='user',content=json.dumps(final))])


def prepare(source):
    assert not (source/'holdout').exists(),'Source tests already materialized; this preparation requires a pre-test source'
    assert (source/'all_arms_freeze.json').exists()
    run.prepare()
    base=run.BASE
    for name in ('shared_initial.json','shared_initial_freeze.json'):
        shutil.copy2(source/name,base/name)
    (base/'search').mkdir()
    shutil.copy2(source/'search/treatment_witness.json',base/'search/treatment_witness.json')
    shutil.copy2(__file__,base/'startup_source_snapshot/research16_ablation_refine.py')
    run.dump(base/'reused_evidence.json',dict(source_run=str(source),
        initial_sha256=hashlib.sha256((base/'shared_initial.json').read_bytes()).hexdigest(),
        source_initial_qualification=str(source/'initial_qualification/v0/decision.json'),
        source_search_cost=str(source/'search/cost.json'),
        source_failure='All four prior proposals rejected for nested temporal operators in Boolean fields; preserved, not relabelled.',
        search_queries_new=0,initial_model_calls_new=0,
        cost_accounting='Initial and search costs were incurred in source run; reused once, not repeated or claimed free in combined totals.',
        holdout_not_materialized=True))
    plan=run.read(base/'plan.json')
    plan.update(initial_selection='Reuse exact first qualified source candidate; no new selection',
        modifications='Uniform typed input/output for current assertions; final task prioritizes actual issues. No Boolean expressions or timing chosen by human for proposals.',
        source_run=str(source),max_initial_calls=0,calls_per_arm=1)
    run.dump(base/'plan.json',plan)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','baseline','arms','holdout'])
    p.add_argument('--run',default='research16_ablation_20261016_r03')
    p.add_argument('--source',default='research16_ablation_20261016_r02')
    args=p.parse_args()
    for value in (args.run,args.source):
        if Path(value).name!=value:raise ValueError('directory name required')
    run.configure(run.ROOT/'deliverables'/args.run)
    run.build_request=request
    if args.action=='prepare':prepare(run.ROOT/'deliverables'/args.source)
    else:getattr(run,args.action)()
