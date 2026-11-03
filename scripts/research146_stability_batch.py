"""Sealed candidate/seed replication. No dispatch without a bound new grant.

Generation acceptance, conditional recovery and frozen holdout have different
denominators. Local tests of this controller never count as model experiments.
"""
import argparse
import secrets
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import patch
import research145_stability_prepare as prepmod

c=prepmod.c
ROOT,read,dump,digest,rel=c.ROOT,c.read,c.dump,c.digest,c.rel


def rate(n,d):
    assert 0<=n<=d
    return dict(numerator=n,denominator=d,value=n/d if d else None)


def metrics(rows):
    attempted=[r for r in rows if r.get('first_dispatched')]
    opportunities=[r for r in rows if r.get('qualified_recovery')]
    eligible=[r for r in rows if r.get('full_terminal')]
    unique={r['H_hash']:r.get('independent_pass') for r in eligible}
    return dict(planned=len(rows),dispatched=len(attempted),
        planned_coverage=rate(len(attempted),len(rows)),
        ordinary_acceptance=rate(sum(bool(r.get('ordinary_accept')) for r in attempted),len(attempted)),
        generation_full_acceptance=rate(sum(bool(r.get('generation_full_accept')) for r in attempted),len(attempted)),
        conditional_recovery=rate(sum(bool(r.get('recovered')) for r in opportunities),len(opportunities)),
        recovery_attempts=sum(bool(r.get('recovery_dispatched')) for r in rows),
        independent_pass=rate(sum(r.get('independent_pass') is True for r in eligible),len(eligible)),
        unique_version_independent_pass=rate(sum(v is True for v in unique.values()),len(unique)),
        independent_pending_or_unavailable=sum(r.get('independent_pass') is None for r in eligible),
        whole_schedule_success=rate(sum(r.get('independent_pass') is True for r in rows),len(rows)),
        critical_unknown_points=sum(r.get('critical_unknown_points',0) for r in rows),
        unknown_cells=sum(r.get('critical_unknown_points',0)>0 for r in rows),
        transport_failure_cells=sum(bool(r.get('transport_failure')) for r in rows),
        native_or_integrity_failure_cells=sum(bool(r.get('execution_exception')) for r in rows),
        not_run=sum(not r.get('first_dispatched') for r in rows))


def validate_grant(prep,out,grant):
    protocol=read(prep/'protocol.json')
    assert grant['purpose']==prepmod.PURPOSE
    assert type(grant['authorized_calls']) is int and grant['authorized_calls']==protocol['maximum_model_calls']
    assert grant['endpoint']==protocol['endpoint'] and grant['model']==protocol['model']
    assert grant['prepared_sha256']==digest(prep/'sealed.json') and grant['run_output']==rel(out)


class DeferredBackend(c.RealBackend):
    def independent(self,prep,out,active,baseline,records):
        dump(out/'independent_deferred.json',dict(reason='All cells must finish before global freeze and new test generation.',
            test_inputs_generated=0,test_executions=0))
        return None


def collect_cell(cell,folder):
    row=dict(cell,first_dispatched=(folder/'shared/v0/model_call/attempt.json').exists(),
             recovery_dispatched=(folder/'history/v1/model_call/attempt.json').exists())
    outcome=read(folder/'outcome.json') if (folder/'outcome.json').exists() else {}
    first=outcome.get('first') or {}
    cost=c.physical_cost(folder)
    statuses=cost['model'].get('model_status',{})
    row.update(status=outcome.get('status','not_run'),ordinary_accept=bool(first.get('O')),
        generation_full_accept=bool(first.get('H')),qualified_recovery=first.get('branch')=='history_once',
        recovered=bool(outcome.get('recovered_full151')),
        full_terminal=bool(first.get('H') or outcome.get('recovered_full151')),
        transport_failure=any(n and k!='response_received' for k,n in statuses.items()),
        execution_exception=(folder/'exception.json').exists(),independent_pass=None,cost=cost)
    unknown=0
    for stage in ('shared/v0','history/v1'):
        f=folder/stage/'native/decision.json'
        if f.exists():unknown+=c.critical_unknown(read(f))
    row['critical_unknown_points']=unknown
    return row


def terminal_versions(prep,folder):
    initial=read(prep/'initial.json');versions={}
    for arm in ('O','H'):
        files=[folder/'arms'/arm/v/'active.json' for v in ('v0','v1')]
        existing=[f for f in files if f.exists()]
        versions[arm]=read(existing[-1]) if existing else initial
    return versions


def freeze(prep,out,rows):
    versions={};bindings={}
    for row in rows:
        active=terminal_versions(prep/'cells'/row['id'],out/'cells'/row['id'])
        bindings[row['id']]={}
        for arm,candidate in active.items():
            sha=c.x.old.acceptance.sha(candidate)
            dump(out/'terminal_frozen'/row['id']/arm/'candidate.json',candidate)
            bindings[row['id']][arm]=sha
            if row['full_terminal']:versions[sha]=candidate
        row['H_hash']=bindings[row['id']]['H']
    dump(out/'global_freeze.json',dict(time=time.time(),versions=bindings,
        eligible_cells=[r['id'] for r in rows if r['full_terminal']],
        unique_test_versions=sorted(versions),no_more_model_calls=True,
        prepared_sha256=digest(prep/'sealed.json')))
    return versions


def independent(prep,out,versions,deadline):
    assert (out/'global_freeze.json').exists()
    assert sorted(versions)==read(out/'global_freeze.json')['unique_test_versions']
    excluded=set()
    for cell in read(prep/'cells.json'):
        full=read(prep/'cells'/cell['id']/'baseline_full.json')
        excluded.update(r['sample']['instruction'] for r in full['ledger'])
        small=read(ROOT/cell['native']/'alignment/result.json')
        excluded.update(r['sample']['instruction'] for r in small['ledger'])
    proc=subprocess.run(['powershell.exe','-NoProfile','-Command','rg --files deliverables -g independent_cases.json'],
                        cwd=ROOT,capture_output=True,text=True,check=True)
    sources=[]
    for name in sorted(set(proc.stdout.splitlines())):
        f=ROOT/name.replace('\\','/')
        if any(v in str(f) for v in ('research133_','research134_')):continue
        values=read(f)
        if isinstance(values,list):
            words={v['instruction'] for v in values if isinstance(v,dict) and type(v.get('instruction')) is int}
            excluded.update(words);sources.append(dict(path=rel(f),sha256=digest(f),word_count=len(words)))
    dump(out/'exclusion_sources.json',sources);dump(out/'excluded_words.json',sorted(excluded))
    seed=secrets.randbits(63);txns=c.x.holdout.base.generate(seed,sorted(excluded))
    assert not ({t['instruction'] for t in txns}&excluded)
    dump(out/'independent_cases.json',txns)
    dump(out/'test_generation.json',dict(seed=seed,time=time.time(),freeze_sha256=digest(out/'global_freeze.json'),
        model_dispatch_finished=True,shared_across_versions=True))
    summaries={}
    for sha,candidate in sorted(versions.items()):
        if time.monotonic()>=deadline:raise TimeoutError('batch_wall_cap_before_independent')
        folder=out/'tested_versions'/sha
        dump(folder/'candidate.json',candidate)
        for rev in ('before','after'):shutil.copytree(prep/rev,folder/rev)
        result=c.x.old.replay(candidate,txns,'independent',folder/'independent',folder,configs=c.x.holdout.base.CONFIGS)
        raw=read(folder/'independent/before/result.json')
        dump(folder/'tool_config.json',dict(version=raw['tool_version']))
        c.mapping.validate_ledger(result,candidate)
        if result['healthy']:
            audit=c.x.holdout.base.native_audit(folder,result);dump(folder/'audit.json',audit)
            with patch.object(c.x.old,'CONFIGS',c.x.holdout.base.CONFIGS):guard=c.x.all_guard(folder/'independent',result,candidate)
            summary=c.x.holdout.summarize(result,guard)
        else:summary=dict(passed=False,counts=result['counts'],status='native_failure')
        assert c.x.old.acceptance.sha(read(folder/'candidate.json'))==sha
        dump(folder/'summary.json',summary);summaries[sha]=summary
        dump(out/'independent_summary.json',summaries)
        print('INDEPENDENT146',sha[:12],summary['passed'],flush=True)
    return summaries


def report(prep,out,rows):
    tests=read(out/'independent_summary.json') if (out/'independent_summary.json').exists() else {}
    frozen=read(out/'global_freeze.json') if (out/'global_freeze.json').exists() else {'versions':{}}
    for row in rows:
        if row['full_terminal']:
            for arm,sha in frozen['versions'].get(row['id'],{}).items():
                row[arm+'_independent']=tests.get(sha)
            if row.get('H_independent') is not None:row['independent_pass']=bool(row['H_independent']['passed'])
    groups={}
    for field in ('candidate','seed','behavior_profile','mechanisms'):
        values=sorted({v for r in rows for v in (r[field] if field=='mechanisms' else [str(r[field])])})
        groups[field]={v:metrics([r for r in rows if (v in r[field] if field=='mechanisms' else str(r[field])==v)]) for v in values}
    cost=c.physical_cost(out);protocol=read(prep/'protocol.json')
    assert cost['model']['model_calls']<=protocol['maximum_model_calls']
    assert cost['native_compiles']<=protocol['maximum_native_compiles']
    assert cost['native_executions']<=protocol['maximum_native_executions']
    result=dict(overall=metrics(rows),grouped=groups,cells=rows,actual_cost=cost,
        qualification=read(prep/'qualification.json'),monetary_cost=None,
        scope='One original Ibex decoder; correlated development candidates, not independent bugs. No claim of search added value or R over H. Native simulation is not formal proof.',
        holdout_unavailable_reason=read(out/'holdout_exception.json') if (out/'holdout_exception.json').exists() else None)
    dump(out/'results.json',result)
    lines=['# Fixed candidate/seed stability replication','',result['scope'],'',
           '| Measure | Numerator | Denominator | Value |','|---|---:|---:|---:|']
    for key,value in result['overall'].items():
        if isinstance(value,dict):lines.append(f"| {key} | {value['numerator']} | {value['denominator']} | {value['value']} |")
    lines += ['',f"Physical model calls: {cost['model']['model_calls']}; native compiles/executions: {cost['native_compiles']}/{cost['native_executions']}; formal calls: 0.",
              '', 'Zero recovery opportunities yields null, not a recovery success/failure rate. Missing independent results stay in the eligible denominator. Per-candidate, seed, mechanism, cluster, unknown and token details: results.json.']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return result


def run(prep,out,authorization):
    prepmod.verify(prep);grant=read(authorization);validate_grant(prep,out,grant)
    out.mkdir(parents=True,exist_ok=False);dump(out/'authorization.json',grant)
    cells=read(prep/'cells.json');protocol=read(prep/'protocol.json')
    rows=[];stop=None;deadline=time.monotonic()+protocol['maximum_wall_seconds']
    try:
        for cell in cells:
            folder=out/'cells'/cell['id'];folder.mkdir(parents=True)
            if stop is None:
                try:
                    if time.monotonic()>=deadline:raise TimeoutError('batch_wall_cap')
                    with patch.object(c,'SEED',cell['seed']),patch.object(c,'BASE_NATIVE',ROOT/cell['native']):
                        c.execute(prep/'cells'/cell['id'],folder,DeferredBackend(prep/'cells'/cell['id'],folder))
                except Exception as exc:
                    dump(folder/'exception.json',dict(type=type(exc).__name__,stage='batch_controller'))
                    stop='execution_or_integrity_exception'
            else:dump(folder/'not_run.json',dict(reason=stop))
            row=collect_cell(cell,folder);rows.append(row)
            if row['transport_failure']:stop='transport_failure'
            dump(out/'progress.json',dict(cells=rows,global_stop=stop))
            print('CELL146',cell['id'],row['status'],flush=True)
        versions=freeze(prep,out,rows)
        if versions:
            try:independent(prep,out,versions,deadline)
            except Exception as exc:dump(out/'holdout_exception.json',dict(type=type(exc).__name__,no_retry=True))
        report(prep,out,rows)
    finally:prepmod.verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
