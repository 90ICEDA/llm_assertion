"""Local original-Ibex54 partial-candidate qualification. No model dispatch API.

All controls are handwritten engineering fixtures, never model proposals.
prepare -> run -> report; only successful qualification enables pilot sealing.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import research159_history_screen as old

ROOT, read, dump, sha = old.ROOT, old.read, old.dump, old.sha
PRIOR = ROOT/'deliverables/research159_history_prepare_20261028_r01'
FIELDS = {'label', 'antecedent', 'consequent', 'obligations'}
OBLIGATIONS = {'shift_hint_legal', 'immediate_hint_legal', 'passthrough'}
SIGNALS = {'instr_i', 'instr_o', 'is_compressed_o', 'illegal_instr_o'}
SHIFT = "((instr_i[1:0]==2'b10 && instr_i[15:13]==3'b000 && !instr_i[12] && (instr_i[11:7]==5'b00000 || instr_i[6:2]==5'b00000)) || (instr_i[1:0]==2'b01 && instr_i[15:13]==3'b100 && !instr_i[11] && !instr_i[12] && instr_i[6:2]==5'b00000))"
IMMEDIATE = "(instr_i[1:0]==2'b01 && instr_i[11:7]==5'b00000 && (instr_i[15:13]==3'b010 || (instr_i[15:13]==3'b011 && {instr_i[12],instr_i[6:2]}!=6'b000000)))"


def prop(label, ant, cons, obligation):
    return dict(label=label, antecedent=ant, consequent=cons, obligations=[obligation])


def controls():
    shift = prop('shift', SHIFT, '!illegal_instr_o', 'shift_hint_legal')
    immediate = prop('immediate', IMMEDIATE, '!illegal_instr_o', 'immediate_hint_legal')
    passthrough = prop('pass', "instr_i[1:0]==2'b11", 'instr_o==instr_i && !is_compressed_o', 'passthrough')
    return dict(baseline=[shift, passthrough],
                replacement=[immediate, passthrough],
                complementary=[shift, immediate, passthrough],
                overbroad=[prop('broad', "instr_i[1:0]!=2'b11", '!illegal_instr_o', 'immediate_hint_legal'), passthrough])


def validate(assertions):
    if not isinstance(assertions, list) or not 1 <= len(assertions) <= 6:
        raise ValueError('assertion_count')
    labels = set()
    for a in assertions:
        if set(a) != FIELDS or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,39}', a['label']):
            raise ValueError('fields_or_label')
        if a['label'] in labels:
            raise ValueError('duplicate_label')
        labels.add(a['label'])
        if not isinstance(a['obligations'], list) or not a['obligations'] or not set(a['obligations']) <= OBLIGATIONS:
            raise ValueError('obligations')
        for key in ('antecedent', 'consequent'):
            s = a[key]
            if not isinstance(s, str) or not s or len(s) > 1600:
                raise ValueError('expression_size')
            # Combinational bit-vector expression subset. No sample IDs, oracle signals,
            # declarations, functions, temporal syntax or injected action blocks.
            t = re.sub(r"\d+'[bBdDhH][0-9a-fA-F_]+", '0', s)
            if set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*', t)) - SIGNALS:
                raise ValueError('non_interface_identifier')
            if re.search(r'[^A-Za-z0-9_\s\[\]:(){}&|!~=<>+\-*/%,^]', t) or re.search(r'(?<![=!<>])=(?!=)|//|/\*|\*/|\+\+|--', t):
                raise ValueError('not_expression')
    return assertions


def vectors():
    rows = []
    def add(family, word, target=None):
        # Vary ignored upper half, never use full instruction constants as predicates.
        word |= ((len(rows)*4051+16207)&65535)<<16 if word&3 != 3 else 0
        rows.append(dict(sample=len(rows), family=family, instruction=word,
                         scope='history' if target == 'shift_hint_legal' else 'public',
                         target=target, expected=old.ibex.oracle(word)))
    for rd in (0,1,7,31):
        for imm in sorted(set(range(0,64,2)) | {1,31,63}):
            add('li', (2<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1,
                'immediate_hint_legal' if rd==0 else None)
    for rd in (0,1,3,31):
        for imm in sorted(set(range(0,64,2)) | {1,31,63}):
            add('lui', (3<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1,
                'immediate_hint_legal' if rd==0 and imm!=0 else None)
    for rd in (0,1,7,31):
        for hi in (0,1):
            for sh in sorted(set(range(0,32,2)) | {1,31}):
                add('slli', (hi<<12)|(rd<<7)|(sh<<2)|2,
                    'shift_hint_legal' if hi==0 and (rd==0 or sh==0) else None)
    for arithmetic in (0,1):
        for rp in (0,3,7):
            for hi in (0,1):
                for sh in (0,1,7,31):
                    add('srai' if arithmetic else 'srli', (4<<13)|(arithmetic<<10)|(hi<<12)|(rp<<7)|(sh<<2)|1,
                        'shift_hint_legal' if hi==0 and sh==0 else None)
    for w in (0x13,0x123456b7,0x00008067,0x00100073):
        add('passthrough', w)
    assert len({r['instruction'] & 65535 for r in rows if r['family']!='passthrough'})==len(rows)-4
    return rows


def bench(assertions, rows):
    validate(assertions)
    lines = ['module tb; bit clk=0;always #5 clk=~clk;logic [31:0] instr_i=0,instr_o;logic is_compressed_o,illegal_instr_o;integer sample=-1;ibex_compressed_decoder dut(.*);']
    for a in assertions:
        label, ant, cons = a['label'], a['antecedent'], a['consequent']
        lines += [f'{label}: assert property (@(posedge clk) (sample>=0 && ({ant})) |-> ({cons})) else $display("ASSERT_FAIL {label} sample=%0d",$sampled(sample));',
                  f'always @(posedge clk) if(sample>=0 && ({ant})) $display("TRIGGER {label} sample=%0d",sample);']
    lines += ['initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for r in rows:
        lines += [f"@(negedge clk); sample={r['sample']};instr_i=32'h{r['instruction']:08x};",
                  '@(posedge clk);$display("TRACE sample=%0d instr=%0d decoded=%0d compressed=%0d illegal=%0d",sample,instr_i,instr_o,is_compressed_o,illegal_instr_o);']
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def prepare(out):
    old.verify(PRIOR)
    out.mkdir(parents=True, exist_ok=False)
    for rev in ('before','after'):
        shutil.copytree(PRIOR/'ibex54'/rev, out/'rtl'/rev)
    rows = vectors()
    dump(out/'vectors.json', rows)
    for name, assertions in controls().items():
        dump(out/'local_controls'/f'{name}.json', dict(origin='handwritten_local_qualification_not_model', assertions=assertions))
        (out/'local_controls'/f'{name}.sv').write_text(bench(assertions, rows))
    tests=[]
    for name, assertions in controls().items():
        validate(assertions); tests.append(name)
    for field, bad in [('antecedent','sample==1'),('consequent','ei'),('antecedent','instr_i=0'),
                       ('antecedent','1; $finish'),('consequent','dut.internal'),('antecedent','instr_i /* mask */')]:
        a=copy.deepcopy(controls()['baseline']);a[0][field]=bad
        try:validate(a)
        except ValueError:tests.append('reject '+bad)
        else:raise AssertionError(bad)
    multi=copy.deepcopy(controls()['complementary']);multi.append(prop('shift_two',SHIFT,'!illegal_instr_o','shift_hint_legal'));validate(multi)
    tests.append('same obligation may have multiple properties')
    dump(out/'interface_checks.json',tests)
    dump(out/'protocol.json',dict(case='Ibex #54 original compressed decoder',
        parent='cd15ce88beba8ed8496f414af361f664764f47e2',fixed='5319734180ac4844e43d31ad19dc108aac503037',
        selection='From frozen three-case inventory: only Ibex54 exposes multiple actual repaired semantic instruction classes. Axis adapter lacks detected historical targets; pause FIFO lacks an additional exposed miss. Do not change RTL or inject faults.',
        baseline_origin='New explicitly handwritten semantic partial seed, not an archived model output, not claimed as natural frequency or real regression proposal.',
        design_rationale='Keep existing shift-HINT legality plus passthrough protection; missing LI/LUI HINT obligation. Split by instruction semantics, never full-word whitelist or sample IDs.',
        public='All immediate-HINT target samples plus ALL legal/reserved/passthrough controls across every selected family.',
        history='Shift-HINT target samples in addition to all public checks; no fixed component prevents shift edits.',
        ordinary='Interface/native success, all public targets detected and triggered, no false positives on public controls or fixed public samples; unknown rejects.',
        historical='Ordinary plus historical targets and necessary triggers retained and no historical false positives; measured actual violations, not property labels.',
        local_controls=['baseline: historical protection with public miss','replacement: semantic class overwrite loses shift protection','complementary: retain shift, add immediate','overbroad: rejects reserved legal controls'],
        cap=dict(compiles=8,executions=8,models=0),data='All generated words are development qualification; no prior independent data consumed.',
        holdout='Not generated this round; only after future real recovery accepts and freezes.',
        scope='Original combinational decoder, selected classes only; not full core or temporal FIFO. Native simulation is not proof.'))
    dump(out/'source_bindings.json',{old.rel(p):sha(p) for p in (Path(__file__),Path(old.__file__),Path(old.native.__file__),Path(old.ibex.__file__))})
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print('PREPARED',len(rows),'samples; targets',sum(r['target']=='immediate_hint_legal' for r in rows),sum(r['target']=='shift_hint_legal' for r in rows),flush=True)


def verify(prep):
    for n,h in read(prep/'seal.json').items():assert sha(prep/n)==h,n
    for n,h in read(prep/'source_bindings.json').items():assert sha(ROOT/n)==h,n


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    for name in ('baseline','replacement','complementary','overbroad'):
        for rev in ('before','after'):
            result=old.native.run_native((prep/'local_controls'/f'{name}.sv').read_text(),out/name/rev,
                extra_sources=[prep/'rtl'/rev/'ibex_defines.sv',prep/'rtl'/rev/'ibex_compressed_decoder.sv'])
            results.append(dict(control=name,revision=rev,result=result))
            dump(out/'progress.json',results)
            print('NATIVE162',name,rev,result['compile_status'],result['execution_status'],len(result.get('failures',[])),flush=True)
    dump(out/'results.json',results);verify(prep)


def positions(records):
    return {int(re.fullmatch(r'sample=(\d+)',r['detail'])[1]) for r in records}


def report(prep,executed,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    rows=read(prep/'vectors.json');results=read(executed/'results.json');index={};audits=[];checks=[]
    cost=dict(model_calls=0,model_tokens=0,formal_calls=0,native_compiles=len(results),native_executions=0,compile_seconds=0,execute_seconds=0)
    start=time.monotonic()
    for item in results:
        name,rev,n=item['control'],item['revision'],item['result']
        cost['compile_seconds']+=n['compile']['wall_seconds'];cost['execute_seconds']+=n.get('execute',{}).get('wall_seconds',0);cost['native_executions']+=n['native_simulation_calls']
        if n['compile_status']!='passed' or n['execution_status']!='completed':
            dump(out/'decision.json',dict(qualified=False,reason='native_failure_or_unknown',model_calls=0));return
        vals=old.trace(executed/name/rev);assert len(vals)==len(rows)
        fail=positions(n['failures']);trigger=positions(n['triggers']);violations=set();records=[]
        for v,r in zip(vals,rows):
            assert v['sample']==r['sample'] and v['instr']==r['instruction']
            e=old.ibex.oracle(v['instr']);wrong=[k for k in ('illegal','compressed','decoded') if not(k=='decoded' and e['illegal']) and e[k]!=v[k]]
            if wrong:violations.add(r['sample'])
            records.append(dict(**r,rtl=v,violated_fields=wrong,candidate_failed=r['sample'] in fail,candidate_triggered=r['sample'] in trigger))
        target={r['sample'] for r in rows if r['target']}
        assert violations==(target if rev=='before' else set())
        checks.append(f'{name}/{rev}: actual inputs and independent ISA agree')
        index[(name,rev)]=dict(fail=fail,trigger=trigger,violations=violations,values=vals)
        dump(out/f'{name}_{rev}_evidence.json',records)
    for rev in ('before','after'):
        assert all(index[(n,rev)]['values']==index[('baseline',rev)]['values'] for n in controls())
        checks.append(rev+' identical original RTL observations across all assertion controls')
    public={r['sample'] for r in rows if r['scope']=='public'}
    history=set(range(len(rows)))-public
    public_targets={r['sample'] for r in rows if r['target']=='immediate_hint_legal'}
    history_targets={r['sample'] for r in rows if r['target']=='shift_hint_legal'}
    for name in controls():
        a,b=index[(name,'before')],index[(name,'after')]
        fp=(a['fail']-a['violations'])|b['fail']
        pmiss=public_targets-a['fail'];hmiss=history_targets-a['fail']
        ptrigger=public_targets-a['trigger'];htrigger=history_targets-a['trigger']
        ordinary=not(pmiss or ptrigger or (fp & public))
        historical=ordinary and not(hmiss or htrigger or (fp & history))
        audits.append(dict(control=name,origin='handwritten_local_fixture',ordinary_accept=ordinary,historical_accept=historical,
            public_detected=len(public_targets & a['fail']),public_total=len(public_targets),history_detected=len(history_targets & a['fail']),history_total=len(history_targets),
            public_required_untriggered=len(ptrigger),history_required_untriggered=len(htrigger),false_positive_samples=len(fp),unknown=0,
            lost_baseline_detections=sorted((index[('baseline','before')]['fail'] & history_targets)-a['fail']),
            retained_version='baseline' if ordinary and not historical else name if historical else 'baseline'))
    by={r['control']:r for r in audits}
    qualified=(by['baseline']['history_detected']==len(history_targets) and by['baseline']['public_detected']==0 and not by['baseline']['false_positive_samples'] and
        by['replacement']['ordinary_accept'] and not by['replacement']['historical_accept'] and len(by['replacement']['lost_baseline_detections'])==len(history_targets) and
        by['complementary']['historical_accept'] and not by['overbroad']['ordinary_accept'])
    assert qualified,'Local semantic qualification failed; do not seal pilot'
    # Refusal retains exact baseline; replay is the already executed baseline, not the rejected candidate.
    basepath=prep/'local_controls/baseline.json'
    dump(out/'retained_version.json',dict(path=old.rel(basepath),sha256=sha(basepath),history_detections=len(history_targets),public_gap=len(public_targets),
        evidence=old.rel(executed/'baseline'),reason='Replacement control rejected only by additional history checks; baseline bytes remain unchanged.'))
    cost['local_oracle_audit_seconds']=time.monotonic()-start
    dump(out/'acceptance_matrix.json',audits);dump(out/'costs.json',cost);dump(out/'audit_checks.json',checks)
    # Seal future scope only; this file cannot dispatch or consume any model budget.
    pilot=out/'pilot';pilot.mkdir()
    baseline=read(basepath)['assertions']
    payload=dict(task='Return a complete replacement assertion set for the original combinational compressed decoder. Repair the current missing checks while preserving existing correct protection. All components are editable; adding complementary properties is allowed. No private oracle signals are available.',
        rtl={rev:(prep/'rtl'/rev/'ibex_compressed_decoder.sv').read_text() for rev in ('before','after')},
        definitions=(prep/'rtl/after/ibex_defines.sv').read_text(),
        obligations=dict(shift_hint_legal='C.SLLI with shamt[5]=0 and rd=x0 or shamt=0, and C.SRLI/SRAI with shamt=0 and shamt[5]=0 are HINTs, not illegal. Historical RV32 high shift bit remains reserved.',
                         immediate_hint_legal='C.LI with rd=x0 is a HINT for all immediate values. C.LUI with rd=x0 and nonzero immediate is a HINT; zero immediate remains reserved. Do not constrain other instruction categories incorrectly.',
                         passthrough='Uncompressed instruction words pass unchanged with is_compressed_o=0. This does not certify full-core instruction legality.'),
        timing='Combinational original decoder sampled at posedge clk; no request acceptance, reset, held transaction, or next-cycle response semantics exist on this interface.',
        current_assertions=baseline,origin='Explicitly handwritten partial seed; not model generated. All assertions may be edited or deleted; no hidden fixed protector.',
        output_schema=dict(assertions='1..6 items, each label, antecedent, consequent, obligations; expressions over instr_i,instr_o,is_compressed_o,illegal_instr_o only, same-cycle implication. Multiple labels may protect one obligation.',reason='string'),
        acceptance='Public native target detections, triggers and no legal false positives; history policy additionally checks prior protections. Unknown rejects. No successful local control or independent test is supplied.')
    evidence=read(out/'baseline_before_evidence.json');selected=[]
    for family in ('li','lui','slli','srli','srai','passthrough'):
        for violated in (True,False):
            selected += [e for e in evidence if e['scope']=='public' and e['family']==family and bool(e['violated_fields'])==violated][:3]
    payload['public_development_evidence']=selected
    assert all(x['scope']=='public' for x in selected)
    request=dict(model='deepseek/deepseek-v3-0324',temperature=0.2,seed=16207,max_tokens=1024,
        messages=[dict(role='system',content='Return only JSON with assertions and reason. Generate predicates yourself; the interface does not repair expressions.'),
                  dict(role='user',content=json.dumps(payload,separators=(',',':')))])
    dump(pilot/'request.preview.json',request)
    dump(pilot/'protocol.json',dict(status='sealed_pending_explicit_model_authorization',endpoint='https://api.highwayapi.ai/openai/chat/completions',
        model=request['model'],seed=[16207,16208],temperature=0.2,max_tokens=1024,max_calls=2,retries=0,
        common_flow='Same generation representation, model and public checks for ordinary/history. One shared real proposal; no plan stage. No properties fixed.',
        branch='Only ordinary acceptance + historical rejection + measured loss/new false positive + no unknown allows one historical-feedback recovery. Otherwise stop. Transport failure stops; no reallocation, no seed expansion.',
        preservation='History rejection retains exact original partial seed; recovery must repair public misses and restore all historical protections, no false positives or required trigger loss.',
        native_cap=dict(development_compiles=4,development_executions=4,independent_compiles=2,independent_executions=2),
        independent='Only after real full recovery: freeze assertion/RTL hashes, then generate 96 distinct unused low16 words from selected ISA families with 16 immediate HINTs,16 shift HINTs,64 legal/reserved controls; exclude all recorded development low16 values. Private evaluation never fed back; failure ends pilot.',
        qualification_reference=old.rel(out/'acceptance_matrix.json'),baseline_hash=sha(basepath),
        interpretation='Local fixtures demonstrate structural semantic opportunity, not occurrence probability or model recovery success. H/R equivalent here; evaluate added history only.'))
    dump(pilot/'bindings.json',dict(prepared_seal=sha(prep/'seal.json'),native_results=sha(executed/'results.json'),request=sha(pilot/'request.preview.json'),
        baseline=sha(basepath),code=sha(Path(__file__))))
    dump(pilot/'seal.json',{p.name:sha(p) for p in pilot.iterdir() if p.is_file()})
    dump(out/'decision.json',dict(local_qualification=True,pilot_sealed=True,model_calls=0,real_extra_rejections=0,real_recoveries=0,independent_runs=0,
        conditional_recovery='0/0 not estimable',fixture_status='handwritten semantic controls only',hr_unique_benefit=False))
    lines=['# 原始 Ibex #54 部分候选本地资格', '',
        '**本地资格成立，已封存待授权先导；模型调用 0。手写对照不是新模型提案，也不是模型恢复成功。**', '',
        f'从上轮固定三个案例中按实际保护行为选择 Ibex #54：同一真实修复涉及移位类与立即数类 HINT；adapter 缺已检出历史目标，pause FIFO 缺另一曝光漏报。新建手写部分基线检查移位 HINT 与直通，明确没有覆盖 LI/LUI。没有把完整 oracle 按指令字白名单屏蔽，没有修改原始 RTL。', '',
        f'{len(rows)} 个开发指令，{len(public_targets)} 个 LI/LUI 原始违例，{len(history_targets)} 个移位 HINT 原始违例。公共检查包含全部其余合法／保留编码及直通控制；历史追加移位 HINT 违例。原始前后采样与独立 ISA 规则逐项核验，修复后全部无违例。', '',
        '|本地手写对照|公共目标检出|历史目标检出|误报采样|普通接受|历史接受|', '|---|---:|---:|---:|---|---|']
    for r in audits:lines.append(f"|{r['control']}|{r['public_detected']}/{r['public_total']}|{r['history_detected']}/{r['history_total']}|{r['false_positive_samples']}|{r['ordinary_accept']}|{r['historical_accept']}|")
    lines += ['', 'replacement 按完整语义类别替换保护：修复当前 LI/LUI，同时删除旧移位检查。普通规则接受，历史规则因实际检出和触发丢失额外拒绝；不是靠公开指令字列表限制前件。拒绝后仍使用原部分基线，其哈希及原生检出证据在 retained_version.json。complementary 是人工正对照，只证明接口允许同时满足两组检查；不能算自动恢复。', '',
        '所有性质可以编辑，支持同义务多性质。性质只能读取原始接口信号，无法读取样本编号、类别、期望值或私有参考答案；接口非法字段、赋值／注入和重复义务支持已本地检查。实际触发由逐样本原生前件标记辅助观测，失败来自原生 assert property；不是形式化覆盖证明。', '',
        '公共／历史差别及全部原始采样在 *_evidence.json。缺口属于断言未触发；公开控制中的高位移位保留编码能拒绝 overbroad。不能仅用模型声明的 obligations 映射代替行为判定。', '',
        '## 已封存边界', '',
        '最多 2 次未来调用：共享真实提案 1 次；仅出现普通接受、历史拒绝且确认退化、无关键 unknown 时，历史反馈恢复 1 次。不重试，不扩种子。完整恢复接受后才冻结并生成新独立测试。当前无调用授权，不执行任何远程请求。', '',
        '没有放入手写 replacement/complementary/overbroad 正负对照或其执行结果，也没有发送旧成功 SVA 或独立测试；请求仅含部分基线、原始 RTL、公共规格及公共开发诊断。先导用于增加历史检查的作用，H/R 等价限制不变。全部新样本是开发资格数据，绝非独立结果。', '',
        f"本轮原生编译 {cost['native_compiles']}、执行 {cost['native_executions']}，编译墙钟 {cost['compile_seconds']:.3f}s、执行 {cost['execute_seconds']:.3f}s。模型 0、形式化 0。新模型接受版本／真实额外拒绝／恢复／独立通过均 0；条件恢复仍 0/0。", '',
        '只在未来取得明确预算后执行封存先导；不能用这些手写对照声称已证实防退化的前瞻收益。576次搜索负结果与原有 FIFO 独立验收保持不变。', '',
        '```powershell',
        'wsl -- python3 scripts/research162_partial_candidate.py prepare --out deliverables/research162_prepare_new',
        'wsl -- python3 scripts/research162_partial_candidate.py run --prepared deliverables/research162_prepare_new --out deliverables/research162_native_new',
        'wsl -- python3 scripts/research162_partial_candidate.py report --prepared deliverables/research162_prepare_new --executed deliverables/research162_native_new --out deliverables/research162_report_new',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    dump(out/'report_seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(qualified=qualified,rows=len(rows),matrix=audits,cost=cost),indent=2),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report']);ap.add_argument('--prepared',type=Path);ap.add_argument('--executed',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='run':run(a.prepared.resolve(),a.out.resolve())
    else:report(a.prepared.resolve(),a.executed.resolve(),a.out.resolve())
