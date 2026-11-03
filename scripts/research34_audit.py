"""Verify local applicability certificates and native controls without model calls."""
import argparse
import hashlib
from pathlib import Path
import shutil
import research17_loop as loop
from research34_applicability import certificate,portable,validate_plan,native_target_gate
from research17_report import cost_audit,artifacts


def audit(prep,out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    expected=loop.read(prep/'applicability.expected.private.json')
    public=loop.read(prep/'windows.public.json');qualification=loop.read(prep/'qualification.json')
    check('nine_windows',len(expected)==len(public)==9)
    for truth,window in zip(expected,public):
        path=portable(truth['source']);record=loop.read(path)
        cert=certificate(record,truth['check_cycle'])
        check(truth['id']+':source_bound',digest(path)==truth['source_sha256'])
        check(truth['id']+':recomputed_independent_truth',all(truth[k]==cert[k] for k in cert))
        check(truth['id']+':samples_unchanged',window['anchor_sample']==cert['samples'][0] and window['check_sample']==cert['samples'][1])
        check(truth['id']+':no_label_in_public_window',not {'applicability','oracle_checks','category','reason'}&set(window))
    check('required_cancelled_not_required_covered',{r['applicability'] for r in expected}=={'required','cancelled','not_required'})
    tests=loop.read(prep/'local_plan_gate_tests.json')
    check('six_plan_gate_unit_cases',len(tests)==6 and tests[0]['decision']['accepted'] and all(not t['decision']['accepted'] for t in tests[1:]))
    # Wrong index types and duplicate IDs must not pass the schema gate.
    fixture=dict(windows=[{k:r[k] for k in ('id','anchor_cycle','check_cycle','applicability')} for r in expected])
    fixture['windows'][0]['anchor_cycle']=str(fixture['windows'][0]['anchor_cycle'])
    check('string_cycle_rejected',not validate_plan(fixture,expected)['accepted'])
    fixture['windows'][1]['id']=fixture['windows'][0]['id']
    check('duplicate_ids_rejected',not validate_plan(fixture,expected)['accepted'])
    binding=loop.read(prep/'baseline_binding.json');before=loop.read(portable(binding['path']))
    check('baseline_bound',digest(portable(binding['path']))==binding['sha256'])
    check('cases_bound',loop.sha(loop.read(prep/'target_cases.json'))==binding['cases_hash'])
    check('candidate_bound',loop.sha(loop.read(prep/'shared_initial.json'))==binding['candidate_hash'])
    controls=[]
    for item in qualification['native_controls']:
        name=item['name'];after=loop.read(prep/'local_controls/core'/name/'result.json')
        edited='a4' if name=='archived_bad' else 'a2'
        verdict=native_target_gate(before,after,edited)
        check(name+':source_model_candidate_bound',digest(portable(item['source']))==item['sha256'])
        check(name+':native_gate_recomputed',verdict==item['decision'])
        check(name+':four_targets_checked',len(verdict['target_rows'])==4)
        controls.append(dict(name=name,accepted=verdict['accepted'],
            triggered=sum(bool(r['edited_assertion'] and r['edited_assertion']['trigger']) for r in verdict['target_rows']),
            detected=sum(bool(r['edited_assertion'] and r['edited_assertion']['causal_detection']) for r in verdict['target_rows']),
            correct_triggered=sum(r['correct_side_trigger'] for r in verdict['target_rows']),counts=after['counts']))
    check('bad_rejected_and_good_passed',not controls[0]['accepted'] and controls[1]['accepted'])
    for name,h in loop.read(prep/'prepared_hashes.json').items():check('prepared:'+name,digest(prep/name)==h)
    for name,h in loop.read(prep/'source_snapshot/hashes.json').items():check('source:'+name,digest(prep/'source_snapshot'/name)==h)
    cost=cost_audit(prep,artifacts(prep))
    check('no_model_requests_during_local_qualification',cost['total']['model_calls']==0)
    check('no_native_command_failure',cost['total']['native_commands_failed_or_timed_out']==0)
    check('plan_not_saved_as_sva',not (prep/'local_plan_output_hook/candidate.sva').exists())
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,controls=controls,
                labels={label:sum(r['applicability']==label for r in expected) for label in ('required','cancelled','not_required')},
                cost=cost['total'],real_model_applicability='not_run',
                source_scope='Archived development windows only; expected labels are fixtures, not claimed model output.')
    loop.dump(out/'verification.json',result);loop.dump(out/'cost.json',cost)
    files=artifacts(prep);manifest={p.relative_to(prep).as_posix():digest(p) for p in files}
    loop.dump(out/'prepared_manifest.json',manifest)
    assert all(digest(prep/n)==h for n,h in manifest.items()),'manifest_changed'
    shutil.copy2(__file__,out/'audit_source.py')
    lines=['# research34 本地验收','',f"审计 {sum(c['passed'] for c in checks)}/{len(checks)}。真实模型调用0，模型周期标注是否正确尚未验证。",'',
           '9个真实开发窗口，包含4条目标反例和5条适用性控制窗口。标签来自独立端口事务模型及复位取消语义，不读取候选性质来确定答案。',
           '第一关逐窗口核验模型标注的前置周期、检查周期及 required/cancelled/not_required 状态；unknown、漏项和周期错位均拒绝。第一关失败即停止，不进行SVA生成。',
           '第二关执行对应RTL上的原生SVA，核验新性质在目标时序边界的真实触发、正确侧触发及故障侧因果检出。任何失败均不能进入完整历史回放；通过后仍需完整历史门控，才能接受并冻结。','',
           '| 归档原生对照 | 目标触发 | 目标检出 | 正确侧触发 | 小批门控 |','|---|---:|---:|---:|---|']
    for c in controls:lines.append(f"| {c['name']} | {c['triggered']}/4 | {c['detected']}/4 | {c['correct_triggered']}/4 | {c['accepted']} |")
    lines+=['','以上对照不是新的模型细化成功。人工构造的错误标注只用于测试校验器，不冒充模型响应。',
            f"实际原生编译 {cost['total']['native_compile_calls']}，执行 {cost['total']['native_execute_calls']}（含编译冒烟），形式化0。有限回放不能证明全局保护。",'',
            '请求预览：'+str(prep/'plan_request.preview.json'),
            '准备命令（输出目录须不存在）：','```powershell',
            'wsl -- python3 scripts/research34_campaign.py prepare --out deliverables/research34_prepare_NEW','```','',
            '真实运行入口（需要新的最多2次授权，第一关失败即停）：','```powershell',
            f'wsl -- python3 scripts/research34_campaign.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out deliverables/research34_real_20261021_r01 --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(dict(passed=result['passed'],checks=len(checks),files=len(manifest),controls=controls))
    assert result['passed'],'audit_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.out.resolve())
