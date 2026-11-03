"""Audit executed preparation and causal input projection; no remote calls."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import research17_loop as loop
from research34_applicability import certificate,portable,native_target_gate
from research35_campaign import causal_request
from research17_report import cost_audit,artifacts


def audit(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(n,v):checks.append(dict(name=n,passed=bool(v)))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    read,dump=loop.read,loop.dump
    reuse=read(prep/'qualification_reuse.json') if (prep/'qualification_reuse.json').exists() else None
    actual=portable(reuse['source']) if reuse else prep
    if reuse:
        check('reused_qualification_bound',digest(actual/'qualification.json')==reuse['qualification_sha256'])
        check('reused_manifest_bound',digest(actual/'prepared_hashes.json')==reuse['source_manifest_sha256'])
        check('no_reexecution_claim',reuse['new_native_commands']==0)
    for name,h in read(prep/'prepared_hashes.json').items():check('prepared:'+name,digest(prep/name)==h)
    for name,h in read(prep/'source_snapshot/hashes.json').items():check('run_source:'+name,digest(prep/'source_snapshot'/name)==h)
    expected=read(prep/'expected.private.json');windows=read(prep/'windows.public.json')
    request=read(prep/'request.preview.json');check('causal_request_recomputed',request==causal_request(windows))
    public=json.loads(request['messages'][1]['content'])['windows']
    check('13_windows',len(expected)==len(windows)==len(public)==13)
    for truth,raw,visible in zip(expected,windows,public):
        path=portable(truth['source']);cert=certificate(read(path),truth['check_cycle'])
        check(truth['id']+':oracle_cert',digest(path)==truth['source_sha256'] and all(truth[k]==cert[k] for k in cert))
        check(truth['id']+':public_samples_unchanged',raw['anchor_sample']==cert['samples'][0] and raw['check_sample']==cert['samples'][1])
        check(truth['id']+':no_outcome_or_input_dependency',visible==dict(id=raw['id'],anchor_sample={k:raw['anchor_sample'][k] for k in ('cycle','rst','mvalid','mready')},check_sample={k:raw['check_sample'][k] for k in ('cycle','rst')}))
    before=read(prep/'target_baseline.json');check('eight_confirmed_misses',before['healthy'] and before['counts']['misses']==8)
    controls=[]
    for item in read(prep/'qualification.json')['controls']:
        name=item['name'];after=read(actual/'core'/name/'result.json')
        decision=native_target_gate(before,after,'a4' if name=='bad' else 'a2')
        saved=read(actual/f'{name}_control_gate.json')
        check(name+':source_candidate',digest(portable(item['source']))==item['sha256'])
        check(name+':native_gate',decision==saved and decision['accepted']==item['accepted'])
        check(name+':eight_targets',len(decision['target_rows'])==8)
        controls.append(dict(name=name,accepted=decision['accepted'],
            triggers=sum(bool(r['edited_assertion'] and r['edited_assertion']['trigger']) for r in decision['target_rows']),
            detections=sum(bool(r['edited_assertion'] and r['edited_assertion']['causal_detection']) for r in decision['target_rows']),counts=after['counts']))
    check('113_full_history_scenarios',len(read(prep/'full_cases.json'))==113)
    cost=cost_audit(actual,artifacts(actual));check('no_model_calls',cost['total']['model_calls']==0)
    check('native_commands_healthy',cost['total']['native_commands_failed_or_timed_out']==0)
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,controls=controls,cost=cost['total'],
        qualification_source=str(actual),next_run_source=str(prep),real_model_status='awaiting_budget_reassignment_and_additional_grant',
        independent_plan='After accepted freeze only: short/long valid, reset/order plus 18 fair-drain scenarios; report each obligation denominator and unknowns.',
        limitations='Archived controls and new native development only. No new model success; no new independent result.')
    dump(out/'verification.json',result);dump(out/'cost.json',cost)
    shutil.copy2(__file__,out/'audit_source.py')
    manifest={p.relative_to(actual).as_posix():digest(p) for p in artifacts(actual)}
    dump(out/'native_preparation_manifest.json',manifest)
    assert all(digest(actual/n)==h for n,h in manifest.items())
    lines=['# research35：适用性修正与完整验收准备','',f"本地核验 {sum(c['passed'] for c in checks)}/{len(checks)} 通过。",'',
        '13个真实适用性窗口，包含4个新增Depth=4/8开发反例；8条目标漏报是采样证据行，不是8个独立Bug。模型看到前一拍控制状态和本拍复位，不看到用于判断功能违例的本拍输出，也不看到输入侧无关信号。旧模型的真实拒绝反馈允许用于开发细化。',
        '归档错误提案仍漏报8/8，归档成功提案触发并检出8/8；这些均不算本轮模型成功。后续归因unknown212保留。',
        '周期标注最多2轮、SVA最多2轮；每轮都用实际拒绝诊断，达到验收即停止。标注全部通过才进入SVA，小批8条反例通过才进入113场景历史回放。新版本接受冻结后，才生成新的背压、复位、顺序和公平排空测试；不得根据结果改候选。',
        f"实际本地成本：编译 {cost['total']['native_compile_calls']} 次、执行 {cost['total']['native_execute_calls']} 次（含冒烟）；模型/形式化0次。r02复用r01资格记录，没有重复仿真或重复计费。",'',
        '首轮请求：'+str(prep/'request.preview.json'),
        '尚未执行真实模型或新独立验收；需要明确转用research34未使用的1次并新增最多3次授权。','',
        '```powershell',
        f'wsl -- python3 scripts/research35_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out deliverables/research35_real_20261021_r01 --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),files=len(manifest),controls=controls))
    assert result['passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.out.resolve())
