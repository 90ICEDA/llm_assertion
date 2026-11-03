"""Terminal service failure accounting and a no-retry transport guard.

Audit action performs no network/model/native calls. Error-capture tests use
synthetic HTTP objects, explicitly separate from experimental model records.
The guard is available for a newly sealed future controller, not retroactively
applied to the already completed research67 pilot.
"""
import argparse
from contextlib import contextmanager
import io
import json
from pathlib import Path
import urllib.error
import urllib.request
from unittest.mock import patch
import research67_controlled_campaign as run
import research67_preflight as preflight
ROOT=run.ROOT


class TerminalTransportFailure(RuntimeError):
    pass


def terminal_status(call):
    # An HTTP/network/truncated/budget failure is not a failed SVA proposal.
    # Only a complete successful transport can lead to model refinement.
    return call.get('status')!='response_received'


@contextmanager
def capture_http_error(folder):
    original=urllib.request.urlopen
    def wrapped(request,*args,**kwargs):
        try:return original(request,*args,**kwargs)
        except urllib.error.HTTPError as error:
            raw=error.read(65537)
            text=raw[:65536].decode('utf-8',errors='replace')
            auth=next((v for k,v in request.header_items() if k.lower()=='authorization'),'')
            for secret in (auth,auth.removeprefix('Bearer ')):
                if secret:text=text.replace(secret,'[REDACTED_CREDENTIAL]')
            run.dump(Path(folder)/'service_error_response.json',dict(http_status=error.code,
                body=text,truncated=len(raw)>65536,credential_redacted=True,
                scope='Sanitized upstream error body; not model output, not a successful generation.'))
            raise
    with patch.object(urllib.request,'urlopen',wrapped):yield


ParentModel=run.campaign.Model
class StopOnTransportModel(ParentModel):
    def call(self,folder,*args,**kwargs):
        with capture_http_error(folder):
            call,candidate=super().call(folder,*args,**kwargs)
        if terminal_status(call):
            run.dump(Path(folder)/'terminal_stop.json',dict(status=call.get('status'),
                another_transmission_allowed=False,refinement_not_started=True))
            raise TerminalTransportFailure('terminal transport failure; no automatic retry')
        return call,candidate


def checks(out,actual):
    names=[]
    def check(label,condition):assert condition,label;names.append(label)
    check('actual400 requires terminal stop',terminal_status(actual))
    for s in ('service_http_error','service_timeout','service_transport_error','pending','cancelled','unknown'):
        check(s+' cannot continue refinement',terminal_status(dict(status=s)))
    check('successful transport can reach SVA checks',not terminal_status(dict(status='response_received')))
    secret='synthetic-fixture-secret-not-a-credential'
    req=urllib.request.Request('https://fixture.invalid/',headers={'Authorization':'Bearer '+secret})
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        raise urllib.error.HTTPError('https://fixture.invalid/',400,'fixture',{},io.BytesIO(('fixture '+secret).encode()))
    with patch.object(urllib.request,'urlopen',fail):
        try:
            with capture_http_error(out/'http_fixture'):urllib.request.urlopen(req)
        except urllib.error.HTTPError:pass
        else:raise AssertionError('exception_suppressed')
    saved=run.read(out/'http_fixture/service_error_response.json')
    check('fixture transport invoked once',len(calls)==1)
    check('fixture error body preserved',saved['http_status']==400 and 'fixture' in saved['body'])
    check('fixture credential redacted',secret not in json.dumps(saved))
    check('capture did not swallow failure',saved['credential_redacted'])
    return names


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    prep=root/'prepared_v4'/f's{run.PILOT}'
    preflight.verify(root,prep)
    pilot=root/'pilot_run';saved=run.read(pilot/'outcome.json')
    calls=list(pilot.glob('**/model_call/attempt.json'))
    assert len(calls)==saved['calls']==1
    call=run.read(calls[0].parent/'transport_result.json')
    assert call['status']=='service_http_error' and call['error']['http_status']==400
    assert call['prompt_tokens'] is None and call['completion_tokens'] is None
    assert not list(pilot.glob('**/model_call/candidate.json'))
    assert not (pilot/'refinement/independent').exists()
    assert not (pilot/'refinement/core/freeze.json').exists()
    assert not any((root/'search'/f's{s}').exists() for s in run.SEEDS)
    active=run.read(pilot/'refinement/core/v0/active_candidate.json')
    assert active==run.read(root/'shared_initial.json')
    tests=checks(out,call)
    detail=dict(actual_sent_calls=1,pre_send_reservations=2,maximum_authorized_calls=3,
        unsent_reservations=1,unused_authorized_call_slots=2,
        additional_transmissions=False,model_proposals=0,usage='unavailable',
        why_second_did_not_send='Conservative token-budget guard raised before creating model_call/attempt.json or reading credential.',
        service_http_status=400,service_error_body='not saved by inherited transport; root cause unknown',
        request_bytes=run.read(prep/'request_metadata.json')['search']['bytes'],
        context_overflow='unconfirmed; do not infer HTTP400 reason from request size',
        model_stage_native_calls=0,new_independent_cases=0,pilot_passed=False,
        preserved_active_hash=run.loop.sha(active),active_version_is_partial_baseline=True,
        multiseed_not_started=True,unused_budget_not_automatically_transferred=True,
        source_sha256=run.search.digest(Path(__file__)),local_guard_checks=tests,
        guard_scope='Implemented and locally exercised only; original failed run is unchanged, not relabelled as a successful guard-controlled run.')
    run.dump(out/'terminal_audit.json',detail)
    cost=run.search.native_cost(root);run.dump(out/'all_work_cost.json',cost)
    summary=run.read(root/'search'/f's{run.PILOT}'/'summary.json')
    public=run.read(prep/'qualification.json');total=cost['total']
    rows=['# research67：实际完成状态与停止原因','',
        '**本轮完成了配对复核、协议封存、先导搜索及原生资格验证；模型先导因HTTP400终止，未完成四组消融或新独立验收。**','',
        '|任务|实际状态|','|---|---|',
        '|research61→62配对决定|复核成立，仍为回顾性分析|',
        '|统一公共辅助、搜索与两类消融协议|已封存，旧实验未覆盖改写|',
        '|先导搜索与有效证据资格|20次搜索查询＋2次公共查询已运行，原生352份日志复算通过|',
        '|真实模型先导|实际发送1次，HTTP400，未产生候选；第二轮在发送前被本地预算阻止|',
        '|新版本完整接受与冻结|未达到，旧部分保护基线仍保留|',
        '|先导新独立验收、多种子、四组冻结后测试|均未启动，不满足先导门槛|','',
        '配对复核：同一research61提案按已固定的回顾性R0接受；加入历史证据因636条新合法误报拒绝，旧目标检出没有丢失。读取完整历史的绝对无误报规则也会拒绝，因此不能把相对比较器单独说成唯一原因。旧版本保留270个BRANCH检出而非完整保护。research62后来实现690个目标检出，但跨阶段接口和单独额度发生变化，没有统一预算对照。', '',
        '|搜索方法|公共之外去重缺口|首发现查询|重复动作|关键unknown|后续归因unknown|','|---|---:|---|---:|---:|---:|']
    for m,v in summary['methods'].items():rows.append(f"|{m}|{len(v['keys'])}|{','.join(map(str,v['first_query'].values())) or '无'}|{v['repeated_actions']}|{v['unknown']}|{v['later_attribution_unknown']}|")
    rows+=['',f"契约搜索在所有对照并集之外的额外缺口数：{len(summary['contract_extra_vs_all'])}。它在第1次查询找到公共未曝光的持续背压valid撤销，但普通补测、分歧、差分及普通不重复搜索也找到同一机制。该缺口属于历史已知，不是新的历史Bug；单种子的先发现不能证明稳定优势。",'',
        f"公共资格回放检出{public['common']['detections']}个目标、遗漏{public['common']['misses']}个解除边界目标；契约新增持续背压见证仍遗漏{public['target']['misses']}个。两组请求都含公共反馈，仅搜索组增加新见证。无合法误报和关键unknown，公共后续归因unknown={public['common']['later_attribution_unknown']}仍保留。",'',
        '公共辅助已固定：同一Qwen72B配置、AST接口、单组件替换方式、公共规格、原生周期门控；所有组都不使用额外模型周期计划。单轮共享提案只用于配对接受决定；后续每组最多2轮独立真实调用才用于策略效果。三种子及四组的协议已定义，执行和验收没有完成。', '',
        f"本轮总成本（含失败准备、重跑和查询编译自检）：{total['native_compile_calls']}次编译、{total['native_execute_calls']}次执行、1次远程请求、0次形式化查询；模型tokens不可用，不能用0代替。搜索本身是2次编译/354次执行，其中352次查询执行、2次编译自检。参考模型逐次耗时保存在search/s6703/reference_costs.json；原始日志复核成本单列在research67_audit_20261024_r01/native_records/audit.json。",'',
        '三次本地准备失败均保留：独立correct案例路径冲突、请求构造未安装完整故障模式、开发轨迹未置于core目录而被旧隔离检查拒绝。prepared_v4修正编排后通过；未放宽隔离或替换SVA。真实调用继承的传输器没有保存HTTP400错误响应正文，具体原因unknown。当前只能确认请求被服务拒绝，不能认定模型能力失败或直接归因于上下文长度。', '',
        '新增本地传输终止适配器和脱敏错误正文采集检查；12项检查使用显式测试夹具，没有新增远程请求。已发送1次与预留2次分开统计；还有2个未发送授权槽，但原协议无传输重试，不自动转作新协议。', '',
        'research63 r02按文件字节哈希确认不变；没有将其输入或结果用于调参、选候选、请求或本轮验收。新测试未生成。本轮没有任何“冻结后通过”的新结论。', '',
        '**下一步**：先封存统一的错误响应采集与传输失败即停规则，诊断HTTP400请求兼容性后另立先导；不得在原失败结果上补写成功。先导目标＋105历史回放＋新独立验收全部通过后，才执行三种子的共享提案配对试验与独立多轮四组试验；各组全部冻结后生成新测试。后续机制收益仍可能为零。', '',
        '复核当前停止状态（使用新的输出目录）：','```powershell',
        'wsl -- python3 scripts/research67_terminal_audit.py --run '+root.relative_to(ROOT).as_posix()+' --out deliverables/research67_terminal_audit_NEW','```',
        '', '协议：../research67_controlled_20261024_r01/protocol.json；实际请求：../research67_controlled_20261024_r01/prepared_v4/s6703/search/request.preview.json；HTTP结果与拒绝保留状态：../research67_controlled_20261024_r01/pilot_run/；配对与资格审计：../research67_audit_20261024_r01/audit.json。']
    (out/'SUMMARY.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    run.dump(root/'current_status.json',dict(stage='pilot_transport_failed',report=str(out/'SUMMARY.md'),
        supersedes_status_only=str(root/'status.json'),pilot_passed=False,actual_model_calls=1,
        protocol_unchanged=True,old_failed_preparations_preserved=True,research63_bytes_unchanged=True))
    print('TERMINAL_AUDIT',len(tests),'checks; actual sent1, reserved2, model tokens unavailable',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
