"""Local-only checks of replication sealing, denominators and controller reuse."""
import argparse
import copy
import json
import socket
import urllib.request
from pathlib import Path
from unittest.mock import patch
import research146_stability_batch as b
import research143_controller_integration as integration

c=b.c
read,dump,digest,rel=b.read,b.dump,b.digest,b.rel


def audit(prep,out):
    opened=c.p.q.guard();b.prepmod.verify(prep)
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(name)
    def rejects(name,action):
        try:action()
        except (AssertionError,ValueError,KeyError):check(name,True)
        else:raise AssertionError(name)
    def forbidden(*args,**kwargs):raise AssertionError('network_or_real_model_forbidden_in_preflight')
    protocol=read(prep/'protocol.json');cells=read(prep/'cells.json');matrix=read(prep/'candidate_matrix.json')
    eligible=[r for r in matrix if r['eligible']]
    check('all_qualified_included',protocol['candidates']==[r['id'] for r in eligible])
    check('cartesian_schedule',[(r['seed'],r['candidate']) for r in cells]==[(s,r['id']) for s in b.prepmod.SEEDS for r in eligible])
    check('bounded_parent',protocol['parent_count']==1)
    check('all_exclusions_reasoned',all(r['exclusion_reasons'] for r in matrix if not r['eligible']))
    check('no_grant_in_preparation',not (prep/'authorization.json').exists())
    check('budget_exact',protocol['maximum_model_calls']==2*len(cells))
    original_seed,original_native=c.SEED,c.BASE_NATIVE
    for cell in cells:
        folder=prep/'cells'/cell['id'];req=read(folder/'request.preview.json')
        initial=read(folder/'initial.json');native=b.ROOT/cell['native']
        records={k:read(native/k/'result.json') for k in ('alignment','search','history')}
        with patch.object(c,'SEED',cell['seed']),patch.object(c,'BASE_NATIVE',native):
            check(cell['id']+'_exact_request',c.request(initial,records,native,False,0)==req)
            check(cell['id']+'_controller',c.controller_checks(req)==read(folder/'controller_checks.json'))
            check(cell['id']+'_baseline_binding',c.BASE_NATIVE==native)
        check(cell['id']+'_scope_restored',c.SEED==original_seed and c.BASE_NATIVE==original_native)
        body=json.loads(req['messages'][1]['content'])
        check(cell['id']+'_history_not_initial_feedback',set(body['actual_feedback']['visible_counts'])=={'alignment','search'})
        check(cell['id']+'_same_model',req['model']==protocol['model'])
        check(cell['id']+'_same_sampling',req['temperature']==protocol['temperature'] and req['max_tokens']==protocol['max_output_tokens'])
        check(cell['id']+'_mechanism_qualifications',bool(cell['mechanisms']))
    grant=dict(purpose=b.prepmod.PURPOSE,authorized_calls=protocol['maximum_model_calls'],endpoint=protocol['endpoint'],
        model=protocol['model'],prepared_sha256=digest(prep/'sealed.json'),run_output=rel(out/'never_run'))
    b.validate_grant(prep,out/'never_run',grant)
    for key,value in [('purpose',c.PURPOSE),('authorized_calls',2),('endpoint','https://invalid.example'),
                      ('model','changed'),('prepared_sha256','0'*64),('run_output','wrong')]:
        bad=dict(grant);bad[key]=value
        rejects('grant_'+key,lambda:b.validate_grant(prep,out/'never_run',bad))
    # Explicitly synthetic denominator cases, not experimental observations.
    fixture=[dict(first_dispatched=True,generation_full_accept=True,ordinary_accept=True,full_terminal=True,H_hash='same',independent_pass=True),
        dict(first_dispatched=True,ordinary_accept=True,qualified_recovery=True,recovery_dispatched=True,recovered=True,full_terminal=True,H_hash='same',independent_pass=True),
        dict(first_dispatched=True,ordinary_accept=True,qualified_recovery=True,recovery_dispatched=True,recovered=False),
        dict(first_dispatched=True,transport_failure=True),dict(first_dispatched=False),
        dict(first_dispatched=True,generation_full_accept=True,full_terminal=True,H_hash='missing',independent_pass=None,critical_unknown_points=2)]
    m=b.metrics(fixture)
    for key,n,d in [('generation_full_acceptance',2,5),('conditional_recovery',1,2),('independent_pass',2,3),
                    ('unique_version_independent_pass',1,2),('whole_schedule_success',2,6),('planned_coverage',5,6)]:
        check('denominator_'+key,m[key]==b.rate(n,d))
    check('missing_tests_not_excluded',m['independent_pending_or_unavailable']==1)
    check('unknown_count',m['critical_unknown_points']==2 and m['unknown_cells']==1)
    check('not_run_not_generation_denominator',m['not_run']==1)
    check('transport_in_generation_denominator',m['transport_failure_cells']==1)
    check('no_opportunity_null',b.metrics([fixture[0]])['conditional_recovery']['value'] is None)
    check('empty_schedule_null',b.metrics([])['generation_full_acceptance']['value'] is None)
    rejects('invalid_numerator',lambda:b.rate(2,1))
    # Real state machine with already audited native fixtures, network disabled.
    # This verifies branches/retention; it does not estimate model success rates.
    class DeferredLocal(integration.LocalBackend):
        def independent(self,prepared,output,active,baseline,records):
            dump(output/'local_deferred.json',dict(new_inputs=0,new_tests=0))
            return None
    scenarios={'both_accept':['permuted'],'recovery':['historical_loss','split'],
               'no_recovery':['branch_first_only'],'failed_recovery':['historical_loss','historical_loss']}
    with patch.object(c.Model,'call',forbidden),patch.object(urllib.request,'build_opener',forbidden),patch.object(socket,'create_connection',forbidden):
        for name,steps in scenarios.items():
            folder=out/'local_controller'/name;folder.mkdir(parents=True)
            backend=DeferredLocal(steps,c.ROOT/'deliverables/research142_prepare_20261027_r01')
            c.execute(c.ROOT/'deliverables/research142_prepare_20261027_r01',folder,backend)
            outcome=read(folder/'outcome.json')
            check(name+'_local_only',outcome['mode']!='real' and outcome['actual_model_calls']==0)
            check(name+'_no_independent',not outcome['new_independent_executed'])
            check(name+'_bounded',backend.index==len(steps))
            versions=b.terminal_versions(c.ROOT/'deliverables/research142_prepare_20261027_r01',folder)
            if name=='failed_recovery':
                check('rejected_preserves_old_H',versions['H']==read(c.ROOT/'deliverables/research142_prepare_20261027_r01/initial.json'))
            if name=='both_accept':check('shared_full_eligible',bool(outcome['first']['H']))
            if name=='recovery':check('recovered_full',outcome['recovered_full151'])
    # Freeze both accepted terminals before any test generation; hash dedup.
    fake=out/'local_freeze';fake.mkdir()
    fr=[dict(cell,full_terminal=True) for cell in cells[:2]]
    versions=b.freeze(prep,fake,fr)
    check('global_freeze_exists',(fake/'global_freeze.json').exists())
    check('hash_dedup',len(versions)<=2*len(fr))
    check('no_test_generation_local',not list(out.rglob('independent_cases.json')))
    check('no_actual_attempts',not list(out.rglob('attempt.json')))
    check('no_new_compiles',not list(out.rglob('compile.json')))
    check('no_new_executions',not list(out.rglob('execute.json')))
    b.prepmod.verify(prep)
    dump(out/'audit.json',dict(passed=True,checks=checks,check_count=len(checks),
        controller_checks_per_cell=len(read(prep/'cells'/cells[0]['id']/'controller_checks.json')),
        cells=len(cells),model_calls=0,new_native_executions=0,new_independent_tests=0,
        synthetic_metric_examples_not_results=True,prepared_sha256=digest(prep/'sealed.json')))
    dump(out/'read_audit.json',sorted(opened))
    (out/'SUMMARY.md').write_text('\n'.join(['# Stability replication local preflight','',
        f'Passed {len(checks)} checks. Prepared {len(eligible)} executable candidates × {len(b.prepmod.SEEDS)} requested seeds = {len(cells)} cells.',
        f"Distinct observed protection profiles: {protocol['distinct_observed_behavior_profiles']}; parent count: 1.",
        'Model calls: 0. New native executions: 0. New independent tests: 0.',
        'Candidate qualification reuses audited original development records. Local fixture transitions are not model generation/recovery results.',
        'A new explicit bounded grant is required before dispatch. No unused old quota is transferred.',
        'Zero recovery opportunities => null; tests not run remain unavailable, never pass. No cross-parent stability or new search benefit claimed.'])+'\n',encoding='utf-8')
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    print('PREFLIGHT147',len(checks),'checks; model0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.out.resolve())
