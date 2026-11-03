"""Retrospective paired decisions on immutable research61/62 real model records.

No model requests, native compilation, new stimuli, or independent-test reads.
Ordinary rule is explicitly defined NOW; no historical ordinary-arm execution
or prospectively matched continuation budget is inferred from archived records.
"""
import argparse
import copy
import json
from pathlib import Path
import time
import research60_local_audit as original_audit
import research61_ast_local as ast
import research62_comparison as comparison

g=ast.g; old=g.old; ROOT=g.ROOT; P=ast.base.P
read,dump=old.read,old.dump
RUNS=('research61_ast_20261023_r01','research61_history_refine_20261023_r01',
      'research62_local_20261023_r01','research62_comparison_20261023_r01')
ROOTS=[ROOT/'deliverables'/s for s in RUNS]
BASE=ROOT/'deliverables/research52_prepare_20261022_r01'


def aggregate(h,s):return g.prior.prior.common.combine(h,s)


def ordinary(small,gate,search,search_guard,interface=True,novel=True):
    """Fixed retrospective R0: current9 + acquired36; never read history115."""
    checks=dict(interface=bool(interface),novel=bool(novel),
        current_native=old.admissible(small),current_phase_gate=bool(gate['accepted']),
        current_all_properties=bool(gate['all_property_guard']['accepted']),
        current_required_phases=bool(gate['focus12']['accepted']),
        current_bound_sampling=all(b['accepted'] for b in gate['bindings']),
        search_native=old.admissible(search),search_all_properties=bool(search_guard['accepted']))
    return dict(accepted=all(checks.values()),checks=checks)


def protection(result):
    info=old.acceptance.inspect(result['ledger'])
    return dict(counts=result['counts'],required_untriggered=len(result['required_untriggered']),
        per_obligation={ob:dict(detected=sum(info['rows'][k]['obligation']==ob for k in info['detections']),
                               missed=sum(info['rows'][k]['obligation']==ob for k in info['misses'])) for ob in old.OBLIGATIONS})


def checks_local(small,gate,search,guard):
    tests=[]
    def check(name,value):assert value,name;tests.append(name)
    check('actual_current_and_search_pass',ordinary(small,gate,search,guard)['accepted'])
    for label,key in [('current_false_alarm','false_positives'),('current_unknown','unknown'),('current_miss','misses')]:
        value=copy.deepcopy(small);value['counts'][key]+=1
        check(label,not ordinary(value,gate,search,guard)['accepted'])
    value=copy.deepcopy(small);value['required_untriggered']=['fixture']
    check('missing_trigger_rejected',not ordinary(value,gate,search,guard)['accepted'])
    value=copy.deepcopy(small);value['healthy']=False
    check('failed_native_rejected',not ordinary(value,gate,search,guard)['accepted'])
    value=copy.deepcopy(gate);value['focus12']['accepted']=False
    check('missing_phase_rejected',not ordinary(small,value,search,guard)['accepted'])
    value=copy.deepcopy(search);value['counts']['false_positives']+=1
    check('search_false_alarm_rejected',not ordinary(small,gate,value,guard)['accepted'])
    check('unprojected_alarm_rejected',not ordinary(small,gate,search,dict(guard,accepted=False))['accepted'])
    check('interface_rejected',not ordinary(small,gate,search,guard,interface=False)['accepted'])
    check('repeat_rejected',not ordinary(small,gate,search,guard,novel=False)['accepted'])
    return tests


def sources():
    files=[Path(__file__).resolve(),Path(original_audit.__file__),Path(ast.__file__),Path(comparison.__file__),
           P/'shared_initial.json',P/'baseline_full.json',P/'protected_branch.json',P/'component_binding.json',P/'sealed.json',
           P/'target_preservation.private.json',ROOT/'deliverables/research51_real_20261022_r01/outcome.json']
    for root in ROOTS:
        files.extend(root/n for n in ('protocol.json','outcome.json','cost.json','runner_snapshot.py'))
        for folder in root.glob('v[0-9]*'):
            for n in ('decision.json','alignment/result.json','alignment/alignment_gate.json','history/result.json',
                      'search/result.json','all_property_guard.json','mapping.json','model_call/model_edit.json',
                      'model_call/candidate.json','model_call/transport_result.json','model_call/request.json',
                      'model_call/response.stream.jsonl','model_call/response.raw.json'):
                if (folder/n).exists():files.append(folder/n)
    return sorted(set(files))


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'protocol.json',dict(analysis='retrospective paired audit; previously observed case',
        proposal='research61_ast_20261023_r01/v0; byte-identical candidate for both decisions',
        R0='Interface and novelty pass; native current9 including first3/held9, required triggers, all-property legal controls and sampling bindings; native acquired search36 with no misses, legal alarms, missing required triggers or unknown. No history115 access.',
        R1='Same R0 plus retained original complete151 acceptance, explicit420 OP+270 BRANCH protection, and all-property historical/legal/unknown guards.',
        sensitivity='R_full_absolute: ordinary rule extended to the SAME full151 evidence with zero legal alarms/unknown. Also test removing only relative new-false-positive reason while retaining absolute full-scope guards.',
        status='Rules fixed before this audit computation but AFTER observing original experiment. Not a preregistered causal trial or evidence that a historical ordinary arm accepted.',
        fallback='Audit immutable original baseline and protected BRANCH; never relabel baseline as a fully accepted set; report missing durable active-version/rollback record.',
        budget='Account original proposal plus all later calls through research62 acceptance, including interface failures/repeats; report separate protocol caps and representation/model configuration changes. Never retrofit a joint cap.',
        prospective_next='New unobserved cases/seeds, immutable R0/R1 and evidence allocation, persistent active-version hashes, identical model/representation/controller and per-arm call/token/native budgets sealed before results. No such new trial executed here.',
        new_model_calls=0,new_native_calls=0,independent_tests_read=False,prepared_at=time.time()))
    dump(out/'sources.json',{str(p.relative_to(ROOT)):old.digest(p) for p in sources()})
    dump(out/'sealed.json',{n:old.digest(out/n) for n in ('protocol.json','sources.json')})
    print('PREPARED retrospective rules and sources',flush=True)


def verify(out):
    for n,h in read(out/'sealed.json').items():assert old.digest(out/n)==h,n
    for n,h in read(out/'sources.json').items():assert old.digest(ROOT/n)==h,n


def run(out):
    verify(out);start=time.perf_counter();checks=[]
    def check(name,value):assert value,name;checks.append(name)
    # Reuse full auditors: raw model stream, syntax-only adapters, exact native
    # sample binding and source hashes; these functions only read saved logs.
    for root in ROOTS:original_audit.run(root,out/'record_audits'/root.name)
    current=read(P/'shared_initial.json');before=read(P/'baseline_full.json')
    baseline_native=[]
    for cohort in ('history','search'):
        folder=BASE/'baseline'/cohort
        n=g.prior.diagnostic.audit_native(folder,current,BASE,cohort)
        baseline_native.append(n)
        check('baseline_copy_identity/'+cohort,read(folder/'result.json')==read(P/'baseline'/cohort/'result.json'))
    check('baseline_full_combination',aggregate(read(BASE/'baseline/history/result.json'),read(BASE/'baseline/search/result.json'))==before)
    proposed=ROOTS[0]/'v0';candidate=read(proposed/'model_call/candidate.json')
    small=read(proposed/'alignment/result.json');gate=read(proposed/'alignment/alignment_gate.json')
    history=read(proposed/'history/result.json');search=read(proposed/'search/result.json')
    guards=read(proposed/'all_property_guard.json');combined=aggregate(history,search)
    local_checks=checks_local(small,gate,search,guards['search'])
    r0=ordinary(small,gate,search,guards['search'],novel=read(proposed/'model_call/novelty.json')['accepted'])
    actual=read(proposed/'decision.json')
    # Original full decision already regenerated exactly by original_audit above.
    r1=dict(accepted=r0['accepted'] and actual['accepted'],reason_kinds=[r['kind'] for r in actual['reasons']])
    check('paired_acceptance_difference',r0['accepted'] and not r1['accepted'])
    check('current_and_search_no_alarm',small['counts']['false_positives']==search['counts']['false_positives']==0)
    info=old.acceptance.inspect(combined['ledger']);prior=old.acceptance.inspect(before['ledger'])
    fkeys=info['false_positives']-prior['false_positives']
    new_fp=[info['rows'][k] for k in sorted(fkeys)]
    check('636_new_legal_rows',len(new_fp)==636)
    check('all_new_false_alarms_from_history',fkeys<=old.acceptance.inspect(history['ledger'])['false_positives'])
    check('no_lost_existing_target',not(prior['detections']-info['detections']))
    check('all_new_targets_fixed',len(info['detections'])==690 and not info['misses'])
    guard_absolute=all(v['accepted'] for v in guards.values())
    sensitivity=dict(full151_absolute_accept=old.admissible(combined) and guard_absolute,
        remove_only_relative_FP_reason_still_rejected=not old.admissible(combined) or not guard_absolute,
        explanation='History115 observation is decisive relative to R0. Relative non-regression comparator is NOT uniquely necessary when a full151 absolute no-false-alarm check is also present. Three rejection reason labels must not count as three benefits.')
    check('absolute_full_scope_also_rejects',not sensitivity['full151_absolute_accept'])
    representative=new_fp[0]
    dump(out/'paired_decisions.json',dict(candidate_sha256=old.acceptance.sha(candidate),
        candidate_file_sha256=old.digest(proposed/'model_call/candidate.json'),R0=r0,R1=r1,
        actual_historical_decision='rejected; no ordinary-arm execution',sensitivity=sensitivity,
        current=protection(small),search=protection(search),history=protection(history),full=protection(combined)))
    dump(out/'false_alarm_evidence.json',dict(evidence_ids=sorted(fkeys),representative=representative,
        transactions=len({r['sample']['instruction'] for r in new_fp}),
        definition='636 sample/configuration/revision records, not independent bugs; count of unique instruction words separately reported.'))
    check('baseline_not_fully_accepted',not old.admissible(before))
    check('baseline_original_model_rejected',read(ROOT/'deliverables/research51_real_20261022_r01/outcome.json')['status']=='no_accepted_version')
    check('rejected_proposal_not_published',not (ROOTS[0]/'accepted_candidate.json').exists() and read(ROOTS[0]/'outcome.json')['accepted_candidate_sha256'] is None)
    for root in ROOTS:
        code=(root/'runner_snapshot.py').read_text()
        check(root.name+'/unchanged_initial_load',"current=g.read(P/'shared_initial.json')" in code)
        check(root.name+'/only_accept_writes_published_candidate',"accepted=candidate;g.dump(out/'accepted_candidate.json',candidate)" in code)
    check('branch_component_identical',candidate['assertions'][0]==current['assertions'][0]==read(P/'protected_branch.json'))
    branch_rows=copy.deepcopy([r for r in before['ledger'] if r['obligation']=='illegal_branch_persists'])
    for r in branch_rows:r['native']['assertions']=[a for a in r['native']['assertions'] if a['id']=='a0']
    branch=old.acceptance.inspect(branch_rows)
    check('branch_component_finite_certificate',len(branch['detections'])==270 and not any(branch[k] for k in ('misses','false_positives','unknown')))
    fallback=dict(candidate_sha256=old.acceptance.sha(current),source=str((P/'shared_initial.json').relative_to(ROOT)),
        whole_set_accepted=False,partial_usable=True,protection=protection(before),
        branch_component=dict(detected=270,trigger_rows=len(branch['triggers']),false_alarms=0,unknown=0),
        persistent_active_version_pointer='unavailable: no explicit active candidate/rollback journal in original run',
        evidence='Original sealed baseline file unchanged, runner initializes current from it and only publishes on acceptance; every new run reloads it. Rejection leaves original source available. This is not an operational rollback test or a fully accepted fallback.')
    dump(out/'fallback.json',fallback)
    final=ROOTS[-1];accepted=read(final/'accepted_candidate.json')
    final_full=aggregate(read(final/'v0/history/result.json'),read(final/'v0/search/result.json'))
    finfo=old.acceptance.inspect(final_full['ledger'])
    check('final_accepted',read(final/'outcome.json')['accepted_candidate_sha256']==old.acceptance.sha(accepted) and read(final/'v0/decision.json')['accepted'])
    check('same_full_evidence_ids',set(info['rows'])==set(finfo['rows'])==set(prior['rows']))
    check('final_all_targets_and_legals',old.admissible(final_full) and len(finfo['detections'])==690)
    check('final_branch_identical',accepted['assertions'][0]==current['assertions'][0])
    check('all636_false_alarms_eliminated',not(fkeys&finfo['false_positives']))
    dump(out/'protection_ids.json',dict(baseline_detected=sorted(prior['detections']),
        proposed_detected=sorted(info['detections']),final_detected=sorted(finfo['detections']),
        avoided_legal_alarms=sorted(fkeys),newly_added_vs_baseline=sorted(finfo['detections']-prior['detections'])))
    budget=[];tokens_in=tokens_out=0;generation=0
    for root in ROOTS:
        protocol=read(root/'protocol.json');cost=read(root/'cost.json')['total'];calls=[]
        for folder in sorted(root.glob('v[0-9]*')):
            request=read(folder/'model_call/request.json');response=read(folder/'model_call/transport_result.json')
            if response is None:continue
            calls.append(dict(version=folder.name,status=response['status'],model=request['model'],options=request['options'],
                prompt_tokens=response.get('prompt_tokens'),completion_tokens=response.get('completion_tokens'),
                response_format_sha256=old.acceptance.sha(request.get('format')),reason_kinds=[r['kind'] for r in read(folder/'decision.json').get('reasons',[])]))
            tokens_in+=response['prompt_tokens'];tokens_out+=response['completion_tokens'];generation+=1
        check(root.name+'/individual_cap',len(calls)<=protocol['maximum_calls'])
        budget.append(dict(run=root.name,individual_cap=protocol['maximum_calls'],calls=calls,
            native_compiles=cost['native_compile_calls'],native_executions=cost['native_execute_calls'],
            scope=protocol['scope'],changes=protocol['changes']))
    dump(out/'budget.json',dict(sequence=budget,from_proposal_generation_calls=generation,
        after_rejection_generation_calls=generation-1,prompt_tokens=tokens_in,completion_tokens=tokens_out,
        local_management_calls=len(ROOTS),native_compiles=sum(r['native_compiles'] for r in budget),
        native_executions=sum(r['native_executions'] for r in budget),prospective_common_cap=None,
        uniform_budget_success=False,reason='Separate 1+1+2+1 call caps; adaptation from unrestricted OP AST to component category AST to explicit comparison. No jointly frozen matched arm budget. Sum is retrospective accounting, not authorization or prospective cap.',
        exclusion='Two earlier research61 text attempts precede chosen AST proposal; excluded from this bounded suffix, not omitted from total research61/62 project cost. Whole research61+62 has7 generation calls.'))
    dump(out/'final_repair.json',dict(candidate_sha256=old.acceptance.sha(accepted),protection=protection(final_full),
        false_alarms_eliminated=len(fkeys),baseline_target_detections_retained=len(prior['detections']&finfo['detections']),
        actual_acceptance=True,same_budget_controlled_success=False,
        scope='Model-selected component refinement; not a second independently generated whole set. No new independent-test results claimed.'))
    dump(out/'rule_checks.json',dict(passed=len(local_checks),checks=local_checks,scope='Synthetic rejection tests only; not hardware experiment evidence.'))
    verify(out)
    dump(out/'audit.json',dict(passed=True,checks=checks,original_record_checks=sum(len(read(out/'record_audits'/root.name/'audit.json')['checks']) for root in ROOTS),
        baseline_rows_rechecked=sum(baseline_native),elapsed_seconds=time.perf_counter()-start,
        new_model_calls=0,new_native_calls=0,formal_calls=0,scope='Retrospective paired audit; independent tests not read.'))
    write_report(out)
    print('PAIRED_AUDIT',len(checks),'checks;',generation,'historical generation calls; new calls 0',flush=True)


def write_report(out):
    pair=read(out/'paired_decisions.json');fallback=read(out/'fallback.json');budget=read(out/'budget.json')
    false=read(out/'false_alarm_evidence.json');audit=read(out/'audit.json');sample=false['representative']
    lines=['# research66：research61/62 回顾性配对审计','',
        '**已观察案例的回顾性分析，不能作为前瞻性受控消融。** 本次没有模型调用、新仿真或独立测试；原记录保持不变。', '',
        '|核查项|实际结果|限制|','|---|---|---|',
        '|同一提案按普通规则是否接受|固定回顾规则R0下接受：9事务小门48/48（含聚焦12/12），搜索36事务267/267，无误报/unknown/必检未触发|R0是本次明确冻结的分析规则；历史上未运行普通接受臂|',
        '|历史检查是否额外拒绝|R0+历史门控拒绝；历史115事务有636条新合法误报，目标仍690/690|决定性增量是历史合法事务曝光；同样读取151事务的绝对合法性检查也会拒绝，不能单独归功于相对防退化比较器|',
        '|是否保留可用上一版本|原始集合保留：BRANCH270/270、合法误报0；OP0/420|只有部分保护，原集合从未完整接受；缺少持久active-version/rollback日志，不能宣称完整版本回滚已验证|',
        '|后续是否修复并在统一预算内完成|research62最终OP420/420、BRANCH270/270、误报/漏报/unknown/必检未触发0|修复真实；统一预设预算验证未完成。多次单独限额和接口修改，不能拼成同预算消融成功|','',
        'R0固定规则：真实响应通过接口与重复检查；当前9事务原生编译/执行、采样绑定、首周期/保持触发与所有性质合法控制通过；已获得的36搜索事务全部目标检出、无合法误报、无关键unknown及必检未触发。R0不读取115历史事务。R1在同一份候选、同一份原生记录上增加原有完整151验收及历史保护检查。规则在本次审计计算前封存，但案例结果早已观察过，不能声称前瞻性预注册。', '',
        '敏感性核查：若普通接受规则本身也要求完整151事务无误报，则它同样拒绝该提案。仅删除new_legal_false_positive这一相对门控理由、保留full_scope和all_property绝对检查，仍会拒绝。这三个理由反映同一批误报，不能计成三个独立收益。', '',
        '实际性质：','```systemverilog',
        read(ROOTS[0]/'v0/model_call/candidate.json')['assertions'][1]['property'],
        '// 后续真实模型选择类别条件并组合；固定BRANCH未变',
        read(ROOTS[-1]/'accepted_candidate.json')['assertions'][1]['property'],'```','',
        f"636条合法误报涉及{false['transactions']}个不同指令字，不是636个独立Bug。代表样本：指令0x{sample['sample']['instruction']:08x}，phase={sample['sample']['phase']}，instr_new={sample['sample']['instr_new']}，配置{sample['configuration']}，{sample['revision']}，规格期望={sample['expected']}、RTL实际={sample['observed']}，原生性质却失败。完整采样及636个ID见false_alarm_evidence.json。",'',
        '原保留集合来自research51真实模型v1，其完整决定原本就是拒绝。research59的封存副本、原始回放与BRANCH组件证书均核对一致。runner初始化current为此集合；拒绝不发布accepted_candidate，后续运行仍重新加载该基线。这里确认的是源文件保留及有限组件保护，不补造“上一完整接受版本”或历史运行中的回滚事件。', '',
        '|阶段|调用/单独上限|实际结果|','|---|---:|---|',
        '|research61 AST提案|1/1|小门通过，历史636误报，拒绝|',
        '|research61历史反馈|1/1|重复提案，编译前拒绝|',
        '|research62类别AST|2/2|两版类别错分，原生前拒绝|',
        '|research62显式比较|1/1|完整接受|','',
        f"从被审计提案开始共{budget['from_proposal_generation_calls']}次真实生成（拒绝后追加{budget['after_rejection_generation_calls']}次）、输入/输出tokens={budget['prompt_tokens']}/{budget['completion_tokens']}，原生{budget['native_compiles']}编译/{budget['native_executions']}执行，模型加载管理{budget['local_management_calls']}次。此前research61两次文本失败不在该后缀内；research61+62全阶段总生成7次。预算与每次模型参数见budget.json。没有预先统一的跨阶段或双臂预算，事后求和不是统一限额验证。",'',
        f"本次核验{len(audit['checks'])}项配对/状态检查、{audit['original_record_checks']}项原始运行检查，并另复核基线{audit['baseline_rows_rechecked']}条原生记录。原始响应、模型渲染、事务参考、接受决定、来源及tokens均复用现有审计器重算；不只读取汇总表。",'',
        '后续前瞻性验证仍待执行：另选未观察案例/种子；先封存R0/R1、公共反馈与历史证据边界；相同提案配对判定，再按相同控制器/表示/模型及调用、token、原生预算继续细化；记录每轮active版本哈希和拒绝后的保留状态。新的独立测试只在最终冻结后执行。本轮没有启动该试验，也没有把旧案例当作新验证。','',
        '复核（新目录）：','```powershell',
        'wsl -- python3 scripts/research66_paired_audit.py prepare --out deliverables/research66_NEW',
        'wsl -- python3 scripts/research66_paired_audit.py run --out deliverables/research66_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();globals()[a.action](a.out.resolve())
