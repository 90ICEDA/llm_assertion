"""Local input/identity/isolation tests and reused native-control audit; no calls."""
import argparse
import copy
import json
from pathlib import Path
import research100_presentation_pilot as pilot
import research88_cross_parent_audit as native_audit

p=pilot.p;x=pilot.x;fmt=pilot.fmt
ROOT,read,dump,sha=pilot.ROOT,pilot.read,pilot.dump,pilot.sha


def run(prep,out):
    pilot.verify(prep);checks=[];rows=0;profiles=[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    def rejects(name,fn):
        try:fn()
        except (ValueError,AssertionError,KeyError):checks.append(name)
        else:raise AssertionError(name)
    baseline=read(prep/'baseline_full.json');initial=read(prep/'initial.json')
    controls=[('baseline',pilot.SOURCE/'baseline_native',initial,dict(O=False,H=False,R=False))]
    for name,expected in [('positive',dict(O=True,H=True,R=True)),('known_overbroad',dict(O=True,H=False,R=False))]:
        f=pilot.SOURCE/'controls'/name;controls.append((name,f/'native',read(f/'candidate.json'),expected))
    for name,folder,candidate,expected in controls:
        n,ev,records=native_audit.inspect_version(folder,candidate,baseline);rows+=n
        check(name+'_native_rules_unchanged',p.decisions(ev)==expected)
        for history in (False,True):
            visible=p.feedback(ev,records,history)
            req={a:fmt.request(candidate,visible,records,a,0) for a in pilot.ARMS}
            bodies={a:json.loads(r['messages'][1]['content']) for a,r in req.items()}
            c,t=bodies['C'],bodies['T'];suffix=name+('_history' if history else '_public')
            expanded=fmt.expand_pairs(t['actual_feedback']['paired_sample_table'])
            check(suffix+'_paired_facts_identical',expanded==c['actual_feedback']['paired_development_records'])
            check(suffix+'_candidate_projection_only',t['current_op']==[{k:a[k] for k in fmt.FIELDS} for a in c['current_op']])
            check(suffix+'_output_keys_only',all(set(a)==set(fmt.FIELDS) for a in t['current_op']))
            check(suffix+'_same_sampling_options',{k:v for k,v in req['C'].items() if k!='messages'}=={k:v for k,v in req['T'].items() if k!='messages'})
            for key in c:
                if key not in ('current_op','actual_feedback'):check(suffix+'_same_'+key,c[key]==t[key])
            visible_c={k:v for k,v in c['actual_feedback'].items() if k!='paired_development_records'}
            visible_t={k:v for k,v in t['actual_feedback'].items() if k!='paired_sample_table'}
            check(suffix+'_same_feedback_counts',visible_c==visible_t)
            for arm,r in req.items():
                charge=sum(len(m['content'].encode()) for m in r['messages'])+2048+r['max_tokens']
                check(suffix+'_'+arm+'_fits_per_call_budget',charge<=30000)
                profiles.append(dict(control=name,history=history,arm=arm,reservation=charge))
            if not history:
                altered=copy.deepcopy(records);altered['history']={'PRIVATE_SENTINEL':'must_not_appear'}
                check(suffix+'_hidden_history_invariant',fmt.request(candidate,visible,altered,'T',0)==req['T'])
            if name=='baseline' and not history:
                for arm in pilot.ARMS:check('sealed_preview_'+arm,read(prep/arm/'request.preview.json')==req[arm])
                check('no_archive_success_or_test_reference',not any(s in json.dumps(req) for s in ('research93','research92_real','independent_cases','frozen/','prior_local_attempts')))
                pairs=c['actual_feedback']['paired_development_records'];table=t['actual_feedback']['paired_sample_table']
                # Concrete sample binding mutations must be rejected, not merely relabeled.
                for field in ('instruction','sample_id','instr_new','phase'):
                    bad=copy.deepcopy(visible);bad['development_counterexamples'][0]['sample'][field]^=1
                    rejects('bad_'+field+'_rejected',lambda bad=bad:fmt.bind_pairs(bad,records))
                bad=copy.deepcopy(visible);bad['development_counterexamples'][0]['evidence_id']='bad'
                rejects('wrong_evidence_id_rejected',lambda:fmt.bind_pairs(bad,records))
                bad=copy.deepcopy(visible);bad['development_counterexamples'][0]['configuration']['RV32E']^=1
                rejects('wrong_configuration_rejected',lambda:fmt.bind_pairs(bad,records))
                bad=copy.deepcopy(visible);bad['development_counterexamples'][0]['observed']^=1
                rejects('wrong_output_rejected',lambda:fmt.bind_pairs(bad,records))
                bad=copy.deepcopy(table);bit=next(iter(bad[0]['decoded']['bit_values']));bad[0]['decoded']['bit_values'][bit]^=1
                rejects('wrong_derived_bit_rejected',lambda:fmt.expand_pairs(bad))
                bad=copy.deepcopy(table);bad[0]['decoded']['phase_name']='not_a_phase'
                rejects('wrong_phase_label_rejected',lambda:fmt.expand_pairs(bad))
                # Formatter does not repair predicates, even an incorrect bit choice.
                check('wrong_initial_bit_preserved_not_repaired',all('instr[31]' in a['antecedent'] for a in t['current_op']))
                check('required_plan_bit_remains28',t['actual_model_op_rule']['bit_index']==28)
    # Missing or out-of-purpose authorization fails before creating a model or run.
    dummy=ROOT/'deliverables/research100_AUTH_TEST_NOT_RUN'
    grant=dict(purpose='research100_presentation_pilot',authorized_calls=4,endpoint=p.prior.transport.DEFAULT_URL,
        model=p.prior.transport.DEFAULT_MODEL,prepared_sha256=sha(prep/'sealed.json'),run_output=dummy.relative_to(ROOT).as_posix())
    pilot.grant_check(grant,prep,dummy)
    for key,value in [('purpose','research94_prospective_gate_pilot'),('authorized_calls',5),('prepared_sha256','bad'),('endpoint','https://invalid.example')]:
        bad=copy.deepcopy(grant);bad[key]=value
        rejects('bad_grant_'+key,lambda bad=bad:pilot.grant_check(bad,prep,dummy))
    check('grant_checks_do_not_create_run',not dummy.exists())
    protocol=read(prep/'protocol.json')
    check('two_calls_per_arm_four_total',protocol['maximum_calls']==4 and protocol['maximum_calls_per_arm']==2)
    check('same_fixed_seeds',protocol['seeds']==[10007,10008])
    check('prior_results_unchanged',p.protected_snapshot()==read(prep/'protected93.json'))
    pilot.verify(prep)
    out.mkdir(parents=True,exist_ok=False)
    result=dict(passed=True,checks=checks,count=len(checks),reused_native_rows_audited=rows,
        new_model_calls=0,new_native_executions=0,script_sha256=sha(Path(__file__)))
    dump(out/'preflight.json',result);dump(out/'reservation_profiles.json',profiles)
    (out/'SUMMARY.md').write_text('\n'.join([
        '# research99–101：请求构造修正与固定预算对照准备','',
        f'本地{len(checks)}项检查通过，复核既有{rows}条原生日志记录。新模型调用0、新原生执行0；尚不能报告呈现改动改善生成。', '',
        'T组current_op仅含antecedent/consequent/timing/obligations；旧候选在两组中均明确标为失败、不是规格。不会人工替换bit31、后件或时序。',
        '两组使用相同选中证据与配对前后RTL记录。C保留原内部候选字段和原始配对记录，T使用样本绑定表：位值、首/保持阶段、前后输出、实际触发和失败。T表能无损还原C原始配对记录，采样、配置、输出、ID和派生位值错误均拒绝。',
        '公平性限定：两组都新增明确失败标签、输出白名单及前后配对信息；因此不是直接重跑research94。仅比较“旧候选字段/原始记录”与“可编辑字段/解码表”的组合呈现，不能分别声称哪一个因素有效，更不能归因于两个核心机制。', '',
        '|项目|封存规则|','|---|---|',
        '|预算|最多4次真实调用；C/T各最多2次，不挪用|',
        '|顺序|C首轮、T首轮、各自被拒绝后最多1次细化|',
        '|模型与采样|同一Highway/Qwen72B；种子10007/10008；temperature=0.2；输出上限1024|',
        '|反馈|首轮同current9/search36；细化只见各自真实失败及同范围历史，不共享另一组提案|',
        '|接受|现有current9与完整151事务、必要触发、零误报/漏报/关键unknown及历史保持；接口不放宽|',
        '|停止|接受即停；传输失败全局停止；无重试、无扩种子|',
        '|独立测试|全部终态冻结后，有新接受版本才生成96新指令、四配置，回放两组|', '',
        '复核（无模型调用）：','```powershell',
        f'wsl -- python3 scripts/research101_presentation_preflight.py --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research101_preflight_NEW','```','',
        '获用途绑定授权后执行：','```powershell',
        f'wsl -- python3 scripts/research100_presentation_pilot.py run --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research100_real_20261025_r01 --authorization deliverables/research100_authorization_20261025_r01.json','```',
        '授权文件尚未创建；不得将旧预算转用或将本地对照当作新模型结果。'])+'\n',encoding='utf-8')
    print('PREFLIGHT101',dict(checks=len(checks),native_rows=rows,new_calls=0),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve())
