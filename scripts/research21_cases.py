"""Development evidence for release-edge stalls and zero-payload reset residue.

Only already public research20 independent inputs are promoted to development.
No new independent data, model calls, RTL edits or assertion edits are involved.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
import random
import shutil
import sys

import research20_cases as previous
import research20_stall_runtime as stall
import research17_loop as loop
import research17_report as report
from research15_acceptance import inspect

ROOT=loop.ROOT
dump,read=loop.dump,loop.read


def digest(path):return report.digest(Path(path))


def extra_cases():
    result=[]
    for name in ('research20_closed_loop_20261018_r05','research20_closed_loop_20261018_r06'):
        source=ROOT/'deliverables'/name/'core_independent/core/case_4/case.json'
        case=copy.deepcopy(read(source))
        assert case['depth']==4 and case['pipeline']==2 and case['mode']=='stall_glitch'
        original_id=case['id']
        case.update(id=f'dev21:promoted:{name}:{original_id}',split='development',
            source='previously_public_independent_test_promoted_to_development',
            target_obligation='stall_stability',family='published_release_edge_stall',
            provenance=dict(source_case=str(source),source_sha256=digest(source),original_id=original_id,
                promotion='Already reported research20 test is development from research21 onward; never claim this input as independent again.',
                row_changes=[]))
        result.append(case)
    for index in (3,4):
        folder=ROOT/'deliverables/research20_cases_20261018_r01/native'/f'case_{index}'
        source=folder/'case.json';oracle_source=folder/'reset_residue/oracle.json'
        case=copy.deepcopy(read(source));oracle=read(oracle_source)
        first=next(v for v in oracle['violations'] if v['obligation']=='reset_cancellation')
        txn=next(t for t in oracle['cancelled'] if t['transaction_id']==first['transaction_id'])
        assert txn['data']==first['observed_data'] and txn['accept_cycle']<txn['cancel_cycle']<first['cycle']
        rows=case['rows'];matches=[i for i,row in enumerate(rows) if row['data']==txn['data']]
        assert len(matches)==1 and not any(row['data']==0 for row in rows)
        changed=matches[0];before=rows[changed]['data'];rows[changed]['data']=0
        assert len({row['data'] for row in rows})==len(rows)
        original_id=case['id']
        case.update(id=f'dev21:d{case["depth"]}:p{case["pipeline"]}:unique_zero_reset_residue',
            split='development',source='oracle_identified_cancelled_payload_perturbation',
            target_obligation='reset_cancellation',family='reset_pending_unique_zero',
            provenance=dict(source_case=str(source),source_sha256=digest(source),
                source_oracle=str(oracle_source),source_oracle_sha256=digest(oracle_source),original_id=original_id,
                source_cancelled_transaction=txn,source_violation=first,
                row_changes=[dict(cycle=rows[changed]['cycle'],field='data',before=before,after=0)],
                qualification='Only one generated payload changes to unique zero; acceptance/cancellation/residue must be revalidated by native execution, not assumed.',
                semantics='Zero is an allowed 32-bit payload, not an indication of an absent or legal unsolicited response.'))
        result.append(case)
    return result


def cases():
    return previous.cases()+stall.extra_cases()+extra_cases()


def independent_cases(seed):
    """Pure prospective generator; caller invokes only AFTER candidate freeze.

    This function reads no files or old test outcomes. Its schedule families are
    defined before testing; its seed must be newly sampled after all candidates
    freeze. Merely defining this function does not construct any test inputs.
    """
    if type(seed) is not int or seed<0:raise ValueError('nonnegative integer seed required')
    rng=random.Random(seed);result=[];length=112
    def fresh_rows():
        values=rng.sample(range(1,2**31),length)
        return [dict(cycle=i,rst=int(i<2),intent=0,ready=1,data=values[i],
                     drain_due=int(i==length-1)) for i in range(length)]
    def append(depth,pipeline,family,mode,rows,**metadata):
        result.append(dict(id=f'independent21:s{seed}:d{depth}:p{pipeline}:{family}:{mode}',
            depth=depth,pipeline=pipeline,mode=mode,rows=rows,family=family,seed=seed,
            split='independent_test',source='prospective_post_freeze_generator',
            generation_rule='Call only after all candidates freeze; no feedback or selection from outcomes.',**metadata))
    for depth,pipeline in ((4,2),(8,2)):
        for stall_at in (7,11):
            rows=fresh_rows()
            # Continuous legal requests; actual driver retains valid/data if
            # a presented request cannot yet be accepted. Exactly one low-ready
            # edge, followed immediately by a ready output acceptance edge.
            for row in rows:
                row['intent']=int(3<=row['cycle']<64)
                row['ready']=int(row['cycle']!=stall_at)
            append(depth,pipeline,f'single_stall_{stall_at}','stall_glitch',rows,
                   target_obligation='stall_stability',stall_cycle=stall_at,release_cycle=stall_at+1)
        for zero in (False,True):
            rows=fresh_rows();resume=22+rng.randrange(3)
            for row in rows:
                c=row['cycle'];row['rst']=int(c<2 or c in (12,13))
                row['intent']=int(c==3 or c==resume)
                row['ready']=int(c>=14)
            if zero:rows[3]['data']=0
            append(depth,pipeline,'reset_cancel_zero' if zero else 'reset_cancel_nonzero',
                   'reset_residue',rows,target_obligation='reset_cancellation',
                   input_intent_cycle=3,reset_cycles=[12,13],release_cycle=14,
                   later_request_cycle=resume,unique_zero_payload=zero)
        random_seed=rng.randrange(2**31)
        rows=previous.search.stimulus(random_seed,'random')
        for mode in ('corrupt','duplicate_payload','drop','reset_residue','stall_glitch'):
            append(depth,pipeline,'fresh_random',mode,copy.deepcopy(rows),schedule_seed=random_seed)
    assert len(result)==18
    return result


def fixed_target_proof(fixed,target,cycle,violations):
    checks=[c for c in fixed['oracle']['checks'] if c['cycle']==cycle and c['obligation']==target]
    if target!='reset_cancellation':
        return dict(passed=bool(checks) and all(c['passed'] for c in checks),same_cycle_checks=checks)
    # A correct reset control often emits no response at the mutant's residue
    # cycle, so the pop-triggered oracle correctly emits no same-cycle check.
    # Confirm cancellation and absence of later accepted cancelled data instead.
    ids={v.get('transaction_id') for v in violations if v['obligation']==target}
    cancelled=[t for t in fixed['oracle']['cancelled'] if t['transaction_id'] in ids]
    forbidden=[s for t in cancelled for s in fixed['trace']
        if s['cycle']>=t['cancel_cycle'] and not s['rst'] and s['mvalid'] and s['mready'] and s['mdata']==t['data']]
    unique=all(sum(u['data']==t['data'] for u in fixed['oracle']['transactions'])==1 for t in cancelled)
    passed=bool(cancelled) and unique and not forbidden and not fixed['oracle']['unknown'] and not fixed['oracle']['violations']
    return dict(passed=passed,cancelled_transactions=cancelled,accepted_payload_identity_unique=unique,
        forbidden_accepted_responses=forbidden,same_cycle_checks=checks,
        rule='Accepted unique transaction is cancelled by reset and never accepted at output afterward in this execution. No output is allowed and is not an unknown check.')


def audit(out,candidate_path):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    candidate_path=Path(candidate_path).resolve();candidate=read(candidate_path)
    selected=cases();dump(out/'cases.json',selected)
    dump(out/'protocol.json',dict(candidate_source=str(candidate_path),candidate_sha256=digest(candidate_path),
        additional_cases=4,total_cases=len(selected),parameters=[[2,0],[5,1],[4,2]],
        model_calls=0,formal_queries=0,
        scope='Development only. Two public research20 independent schedules are explicitly promoted. Two zero-payload perturbations originate from actual accepted/cancelled transactions.',
        immutable_semantics=['Actual axis_fifo RTL','existing artificial boundary faults including opt-in stall_glitch','source handshake driver','reset and reference oracle','frozen candidate SVA'],
        limits='Finite simulation; artificial boundary defects are not original historical bug reproductions.'))
    snapshot=out/'source_snapshot';snapshot.mkdir()
    for path in (Path(__file__),Path(previous.__file__),Path(stall.__file__),Path(loop.__file__),
                 ROOT/'scripts/research17_fifo_feedback.py',ROOT/'scripts/research15_search_runtime.py',
                 ROOT/'scripts/research15_evidence.py',ROOT/'scripts/research15_native_interface.py',stall.runtime.RTL):
        shutil.copy2(path,snapshot/path.name)
    shutil.copy2(candidate_path,out/'unchanged_frozen_candidate.json')
    dump(snapshot/'hashes.json',{p.name:digest(p) for p in snapshot.iterdir()})
    with stall.installed():native=loop.replay(candidate,out/'native',selected)
    dump(out/'restoration.json',dict(stall_extension_restored=not stall._active,modes=stall.runtime.MODES))
    info=inspect(native['group']['ledger']) if native.get('group') else None
    additions=[]
    for index,case in enumerate(selected):
        if not case['id'].startswith('dev21:'):continue
        folder=out/'native'/f'case_{index}'
        fixed=read(folder/'correct/replay.json');buggy=read(folder/case['mode']/'replay.json')
        group=read(folder/'ledger.json');parsed=inspect(group['ledger'])
        missed=[parsed['rows'][key] for key in sorted(parsed['misses'])]
        target=case['target_obligation'];matched=[r for r in missed if r['obligation']==target]
        checks=dict(healthy_control=not fixed['oracle']['violations'] and not fixed['oracle']['unknown'] and fixed['oracle']['legality']=='legal',
            buggy_input_legal=buggy['oracle']['legality']=='legal' and not buggy['oracle']['unknown'],
            identical_accepted_inputs=group['stats']['paired_inputs_identical'],
            sampling_pass=fixed['sampling_qualification']['status']==buggy['sampling_qualification']['status']=='passed',
            target_missed=bool(matched))
        transactions=[]
        if case['family']=='reset_pending_unique_zero':
            zeros=[t for t in buggy['oracle']['cancelled'] if t['data']==0]
            zero_violations=[v for v in buggy['oracle']['violations'] if v['obligation']=='reset_cancellation' and v.get('observed_data')==0]
            checks.update(unique_accepted_zero=len([t for t in buggy['oracle']['transactions'] if t['data']==0])==1,
                zero_cancelled=bool(zeros),zero_resurrected=bool(zero_violations),
                no_unsolicited_missed=any(r['obligation']=='no_unsolicited_output' for r in missed))
            transactions=zeros
        targets=[]
        for row in matched:
            cycle=row['cycle']
            proof=fixed_target_proof(fixed,target,cycle,row['oracle_violation'])
            samples=[s for s in buggy['reference_trace'] if cycle-1<=s['cycle']<=cycle+1]
            by={s['cycle']:s for s in samples};p,c=by.get(cycle-1),by.get(cycle)
            release=bool(p and c and p['mvalid'] and not p['mready'] and c['mready'])
            targets.append(dict(evidence_id=row['evidence_id'],cycle=cycle,obligation=target,
                independent_fixed_pass=proof['passed'],independent_fixed_proof=proof,
                release_edge=release,oracle=row['oracle'],violation=row['oracle_violation'],
                buggy_samples=samples,fixed_samples=[s for s in fixed['reference_trace'] if cycle-1<=s['cycle']<=cycle+1],
                native=row['native']))
        if target=='stall_stability':checks['release_edge_miss']=any(t['release_edge'] for t in targets)
        checks['independent_fixed_target_pass']=bool(targets) and all(t['independent_fixed_pass'] for t in targets)
        additions.append(dict(case=case['id'],provenance=case['provenance'],checks=checks,passed=all(checks.values()),
            target_evidence=targets,zero_cancelled_transactions=transactions,
            missed_by_obligation={o:sum(r['obligation']==o for r in missed) for o in loop.model.SPECS},
            later_attribution_unknown=len(group['exclusions']),native_directory=str(folder)))
    physical=report.cost_audit(out,report.artifacts(out))['total']
    result=dict(passed=bool(native.get('healthy') and len(additions)==4 and all(c['passed'] for c in additions)),
        native_healthy=native.get('healthy'),counts=native.get('counts'),new_cases=additions,cost=physical,
        candidate_unchanged=digest(candidate_path)==digest(out/'unchanged_frozen_candidate.json'),
        caveat='Four qualified additions are parameter/scenario replications of two boundary conditions; not four new historical defects. All reused public tests now development.')
    dump(out/'summary.json',result)
    dump(out/'execution.command.json',dict(argv=[sys.executable,*sys.argv],cwd=str(Path.cwd())))
    (out/'REPORT.md').write_text(render(result),encoding='utf-8')
    print({k:result[k] for k in ('passed','counts','cost')},flush=True)
    return result


def render(result):
    physical=result['cost'];additions=result['new_cases']
    lines=['# Research21 开发证据资格审计','',
        '没有模型调用，没有改变RTL、SVA、握手驱动或规格。r20已公开独立输入从本轮起转为开发数据；不得再作为独立验证。',
        '',f"整体资格通过：{result['passed']}；原生计数：{result['counts']}。",'',
        '| 新案例 | 资格通过 | 目标周期 |','|---|---|---|']
    for item in additions:
        lines.append(f"| {item['case']} | {item['passed']} | {','.join(str(t['cycle']) for t in item['target_evidence'])} |")
    lines+=['','唯一零payload由旧原生oracle中已接受、随后取消且被residue故障重新输出的事务定位，再只改其输入数据字段。所有接受、取消和违例均通过新原生执行重新确认。零数据不是合法无请求输出的标记。',
        '',f"实际成本：{physical['native_compile_calls']}次编译，{physical['native_execute_calls']}次执行（含{physical['compile_smoke_execute_calls']}次smoke），0模型调用/0形式化查询。",'',
        '真实axis_fifo加既有人工输出边界故障；不能计作原始历史Bug成功。有限仿真不是形式证明。源码、来源哈希、原始输入差异、原生波形及每项独立判据见机器结果。','']
    if result.get('qualification_reanalysis'):
        lines+=['资格审计首次错误要求正确版本在违例同周期有pop触发的复位检查，导致无输出的正确行为被标成资格失败。原失败结果保存在summary.initial.json；重新分析实际取消事务及此后不存在该唯一payload的输出握手后纠正。没有重跑或改写原生记录、候选或规格。','']
    return '\n'.join(lines)


def reanalyze(out):
    """Correct admission analysis over immutable actual native artifacts."""
    out=Path(out).resolve();result=read(out/'summary.json');selected=read(out/'cases.json')
    if (out/'summary.initial.json').exists():raise RuntimeError('reanalysis already archived')
    shutil.copy2(out/'summary.json',out/'summary.initial.json')
    shutil.copy2(out/'REPORT.md',out/'REPORT.initial.md')
    for item in result['new_cases']:
        index=next(i for i,c in enumerate(selected) if c['id']==item['case'])
        fixed=read(out/'native'/f'case_{index}'/'correct/replay.json')
        for target in item['target_evidence']:
            proof=fixed_target_proof(fixed,target['obligation'],target['cycle'],target['violation'])
            target.update(independent_fixed_pass=proof['passed'],independent_fixed_proof=proof)
        item['checks']['independent_fixed_target_pass']=bool(item['target_evidence']) and all(t['independent_fixed_pass'] for t in item['target_evidence'])
        item['passed']=all(item['checks'].values())
    result['passed']=bool(result['native_healthy'] and len(result['new_cases'])==4 and all(c['passed'] for c in result['new_cases']))
    result['qualification_reanalysis']=dict(reason='Correct control emits no output at reset-residue violation cycle; inspect actual cancelled unique transaction and absence of forbidden response, rather than demanding a pop-triggered same-cycle check.',
        prior_result='summary.initial.json',new_model_calls=0,new_native_executions=0,
        native_artifacts_unchanged=True,independent_generator_defined_but_not_invoked=True)
    dump(out/'summary.json',result);(out/'REPORT.md').write_text(render(result),encoding='utf-8')
    shutil.copy2(__file__,out/'reanalysis_source.py')
    dump(out/'reanalysis.json',dict(argv=[sys.executable,*sys.argv],source_sha256=digest(Path(__file__)),scope=result['qualification_reanalysis']))
    print(dict(passed=result['passed'],reanalysis_only=True),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,default=ROOT/'deliverables/research20_closed_loop_20261018_r06/core/frozen_candidate.json')
    parser.add_argument('--reanalyze',action='store_true')
    args=parser.parse_args()
    result=reanalyze(args.out) if args.reanalyze else audit(args.out,args.candidate)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
