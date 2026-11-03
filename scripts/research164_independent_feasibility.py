"""Pre-call feasibility of the frozen Ibex54 unseen-low16 holdout contract.

Reads only development input integers and source/seal metadata, not old test
verdicts. Does not sample a new holdout, modify a seal, or call a model/toolchain.
"""
import argparse
from pathlib import Path
import research162_partial_candidate as q

PREP = q.ROOT/'deliverables/research162_partial_prepare_20261028_r01'
REPORT = q.ROOT/'deliverables/research162_partial_report_20261028_r01'


def target(word):
    quadrant=word&3
    funct=word>>13
    rd=(word>>7)&31
    imm=((word>>12)&1)*32+((word>>2)&31)
    if quadrant==1 and rd==0 and (funct==2 or (funct==3 and imm!=0)):
        return 'immediate_hint'
    if quadrant==2 and funct==0 and imm<32 and (rd==0 or imm==0):
        return 'shift_hint'
    if quadrant==1 and funct==4 and ((word>>10)&3) in (0,1) and imm==0:
        return 'shift_hint'
    return None


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    q.verify(PREP)
    for name,h in q.read(REPORT/'report_seal.json').items():
        check('unchanged research162 '+name,q.sha(REPORT/name)==h)
    protocol=q.read(REPORT/'pilot/protocol.json')
    check('sealed independent requirement still unchanged',
          '16 immediate HINTs,16 shift HINTs,64 legal/reserved controls' in protocol['independent'] and
          'exclude all recorded development low16 values' in protocol['independent'])
    pools={name:{w for w in range(65536) if target(w)==name} for name in ('immediate_hint','shift_hint')}
    # Independently enumerate semantic register/immediate coordinates.
    li={(2<<13)|((imm>>5)<<12)|((imm&31)<<2)|1 for imm in range(64)}
    lui={(3<<13)|((imm>>5)<<12)|((imm&31)<<2)|1 for imm in range(1,64)}
    slli={(rd<<7)|(sh<<2)|2 for rd in range(32) for sh in range(32) if rd==0 or sh==0}
    srli={(4<<13)|(rp<<7)|1 for rp in range(8)}
    srai={(4<<13)|(1<<10)|(rp<<7)|1 for rp in range(8)}
    check('two independent immediate pool enumerations',pools['immediate_hint']==li|lui)
    check('two independent shift pool enumerations',pools['shift_hint']==slli|srli|srai)
    check('full immediate cardinality',len(pools['immediate_hint'])==127)
    check('full shift cardinality',len(pools['shift_hint'])==79)
    check('all target encodings are legal HINTs per independent ISA oracle',
          all(q.old.ibex.oracle(w)['illegal']==0 for w in pools['immediate_hint']|pools['shift_hint']))
    sources=[q.old.ibex.OLD/'boundary_vectors.json',
             q.ROOT/'deliverables/research15_history_20261015_r01/ibex54_new_boundaries/vectors.json',
             q.PRIOR/'ibex54/vectors.json',PREP/'vectors.json']
    used=set();provenance=[]
    for p in sources:
        values=q.read(p)
        check('input list schema '+q.old.rel(p),isinstance(values,list) and all(type(r.get('instruction')) is int for r in values))
        words={r['instruction']&65535 for r in values}
        used.update(words)
        provenance.append(dict(path=q.old.rel(p),sha256=q.sha(p),records=len(values),unique_low16=len(words),
             immediate_pool_covered=len(words&pools['immediate_hint']),shift_pool_covered=len(words&pools['shift_hint']),
             inspected_fields=['instruction'],purpose='Prior observed engineering/development inputs for collision exclusion only; no prior verdict used.'))
    # Even this conservative known subset exhausts both target strata; adding
    # further development exclusions cannot restore any fresh target encoding.
    result=[]
    for name in pools:
        available=pools[name]-used
        result.append(dict(stratum=name,total_semantic_low16=len(pools[name]),already_observed=len(pools[name]&used),
                           required_fresh=16,remaining_fresh=len(available),feasible=len(available)>=16))
    check('both mandatory target strata exhausted',all(r['remaining_fresh']==0 for r in result))
    check('upper-half variants preserve compressed ISA oracle result',
          all(q.old.ibex.oracle(w|(0xabcd<<16))==q.old.ibex.oracle(w)
              for w in pools['immediate_hint']|pools['shift_hint']))
    decision=dict(status='STOP_BEFORE_MODEL_AUTHORIZATION_REQUEST',model_calls=0,model_calls_requested=0,
        native_compiles=0,native_executions=0,credentials_read=False,new_independent_cases_generated=0,
        local_semantic_qualification_remains_valid=True,
        frozen_pilot_end_to_end_feasible=False,
        reason='Both required independent target low16 pools have already been fully observed in development. Frozen 16+16 fresh target requirement cannot be satisfied.',
        old_reports_modified=False,old_failure_relabelled=False,
        oversight='research162 sealed an unseen-low16 independent plan before auditing the union of archived development inputs. research163 recorded the exclusion caveat but did not establish pool feasibility.',
        preserves='No weakening acceptance, no upper16/reordered repeat counted as new target, no independent claim from known samples. Existing H/R equivalence and search negative result remain unchanged.',
        future_options=[
            'Keep strict unseen-low16 standard: choose another sourced original RTL case with remaining semantic target capacity, repeat local qualification, then seal a new bounded pilot.',
            'If explicitly choosing a narrower research objective: seal a NEW protocol measuring real shared-proposal decision/recovery on known development evidence only; report no new independent-target validation. This does not complete the originally required chain.'
        ])
    q.dump(out/'source_input_inventory.json',provenance)
    q.dump(out/'target_space_feasibility.json',result)
    q.dump(out/'target_pool_already_observed.json',{k:sorted(v) for k,v in pools.items()})
    q.dump(out/'known_development_exclusion_low16.json',sorted(used))
    q.dump(out/'decision.json',decision)
    q.dump(out/'checks.json',checks)
    lines=['# research162 先导调用前：独立验收空间可行性', '',
        '**结论：停止，不申请或执行模型调用。原封存协议无法完成其规定的新独立目标曝光。**', '',
        'research162/163 的本地手写区分资格仍成立：部分候选有27个历史检出和69个当前漏报；但这不等于冻结后的独立验收计划可执行。本次在发送请求前核查了早期已用编码的并集，发现上轮封存漏做了这一项可行性检查。旧协议、旧报告和原始结果均保持不变。', '',
        '|必需独立分层|全部有效低16位编码|已有开发材料覆盖|仍未使用|协议要求|', '|---|---:|---:|---:|---:|']
    for r in result:lines.append(f"|{r['stratum']}|{r['total_semantic_low16']}|{r['already_observed']}|{r['remaining_fresh']}|{r['required_fresh']}|")
    lines += ['', '立即数类全部127种＝C.LI rd=x0 的64种＋C.LUI rd=x0 非零立即数的63种；移位类全部79种＝C.SLLI HINT 的63种＋C.SRLI/SRAI 零移位的各8种。两种独立枚举一致，ISA oracle确认这些均为合法HINT。早期 boundary_vectors 已覆盖所有立即数HINT；与research15已执行输入合并后，移位HINT也全部覆盖。', '',
        '原始压缩解码器在这些编码上没有可新增的参数、握手或保持阶段。改变无关高16位、顺序、重复次数不能满足原协议的“新低16位编码”要求。普通合法控制仍可有未用输入，但不能替代强制的两类目标曝光。', '',
        '本次只读取明确列出的已用开发输入整数作排除核查，没有利用旧独立结果调候选、规则或提示，也没有生成新测试。这里已核对的子集就穷尽了目标空间，补充更多排除材料不会改变不可行结论。', '',
        '## 当前应如何处理', '',
        '1. 保持原验收标准：暂停这份Ibex #54先导，选择仍有未用语义目标空间的可靠历史案例，重新本地资格审查后封存。',
        '2. 若另有明确研究目的，可重新封存“仅开发证据上的真实额外拒绝与恢复”实验，明确不报告新的独立目标验收；这属于范围变化，不能默认采用，也不能声称完成原完整链。', '',
        '不以更换措辞、追加调用或重标旧测试来绕过约束。本轮没有调用授权申请、模型调用、原生执行或独立验收；真实条件恢复仍0/0不可估计。H/R等价、既有FIFO独立结果和576查询负结果不变。', '',
        f'本地可行性检查 {len(checks)} 项通过。输入来源、哈希、有限目标空间及停止原因分别保存在本目录JSON。', '',
        '```powershell',
        'wsl -- python3 scripts/research164_independent_feasibility.py --out deliverables/research164_feasibility_recheck',
        '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    q.dump(out/'bindings.json',dict(audit_code=q.sha(Path(__file__)),prior_pilot_seal=q.sha(REPORT/'pilot/seal.json'),
        qualification_report_seal=q.sha(REPORT/'report_seal.json')))
    q.dump(out/'seal.json',{p.name:q.sha(p) for p in out.iterdir() if p.is_file()})
    print(dict(checks=len(checks),target_space=result,status=decision['status'],model_calls=0))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();run(a.out.resolve())
