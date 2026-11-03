"""Read-only cross-check of partial protection against raw original RTL records."""
import argparse
import json
from pathlib import Path
import re
import research185_drop_partial as q


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False);base=run/'qualification';report=base/'report';checks=[]
    def ck(name,ok):checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    for folder,seal in ((run,'protocol_seal.json'),(base/'prepared','seal.json'),(report,'seal.json'),(base/'compatibility_audit','seal.json')):
        for name,h in q.s.read(folder/seal).items():ck('sealed '+q.s.rel(folder/name),q.s.sha(folder/name)==h)
    witness=[]
    for depth in q.DEPTHS:
        for policy in q.POLICIES:
            for rev in ('before','after'):
                folder=base/'native'/str(depth)/policy/rev;r=q.s.read(folder/'result.json');tr=q.s.traces(folder)
                ck(f'complete {depth}/{policy}/{rev}',r['compile_status']=='passed' and r['execution_status']=='completed')
                tagged=q.reference(tr,depth);raw=q.s.oracle(tr,'frame_fifo_drop',depth)
                ck(f'input legality {depth}/{policy}/{rev}',raw['legal'] and not tagged['unknown'])
                # Different reference implementations: per-TID reconstruction vs
                # payload/input-frame reconstruction inherited from research183.
                leaked=sum(len(ev['outputs']) for ev in tagged['events'])
                raw_leaked=sum(v['obligation']=='oversize_frame_atomic_drop' for v in raw['violations'])
                ck(f'reference agreement {depth}/{policy}/{rev}',leaked==raw_leaked)
                if rev=='after':ck(f'fixed original pair {depth}/{policy}',raw['complete_scope_pass'])
                if rev=='before':
                    for ev in tagged['events']:
                        f=ev['first'];candidate='first_ready' if policy=='ready_first' else 'first_stalled'
                        markers={(x['id'],int(re.search(r'cycle=(\d+)',x['detail'])[1])) for x in r['failures']}
                        triggers={(x['id'],int(re.search(r'cycle=(\d+)',x['detail'])[1])) for x in r['triggers']}
                        ck(f'native detection {depth}/{policy}',(candidate,f['cycle']) in markers and (candidate,f['cycle']) in triggers)
                        wrong='first_stalled' if policy=='ready_first' else 'first_ready'
                        ck(f'complement misses whole frame {depth}/{policy}',not any(a==wrong and c>=f['cycle'] and c<=ev['outputs'][-1]['cycle'] for a,c in markers))
                        witness.append(dict(depth=depth,policy=policy,first_cycle=f['cycle'],first_ready=f['ready'],
                            first_input_accept=ev['accepted'][0]['cycle'],last_input_accept=ev['accepted'][-1]['cycle'],
                            first_output_handshake=ev['outputs'][0]['cycle'],last_output_handshake=ev['outputs'][-1]['cycle'],
                            leaked_beats=leaked,detecting_property=candidate))
    matrix=q.s.read(report/'candidate_matrix.json');names={x['candidate']:x for x in matrix}
    ck('partial has old targets and misses public',names['partial_stalled']['historical_detected']>0 and names['partial_stalled']['public_detected']==0 and names['partial_stalled']['public_total']>0)
    ck('extra local rejection',names['replacement_ready']['ordinary_accept'] and not names['replacement_ready']['historical_accept'])
    ck('union and full accept',names['union']['historical_accept'] and names['full']['historical_accept'])
    ck('overbroad rejected for actual legal FP',names['overbroad']['false_positive_records'] and not names['overbroad']['ordinary_accept'])
    ck('vacuous rejected for absent target triggers',names['vacuous']['missing_trigger_ids'] and not names['vacuous']['ordinary_accept'])
    ck('no key unknown',all(not x['critical_unknown'] for x in matrix))
    decision=q.s.read(report/'decision.json');ck('qualification decision',decision['local_structural_qualification'])
    q.s.dump(out/'checks.json',checks);q.s.dump(out/'concrete_traces.json',witness)
    q.s.dump(out/'decision.json',decision)
    q.s.dump(out/'source_bindings.json',{q.s.rel(p):q.s.sha(p) for p in [Path(__file__),Path(q.__file__),Path(q.s.__file__),report/'seal.json',run/'protocol_seal.json']})
    lines=['# 部分保护资格：独立实现交叉复核','',f'{len(checks)}项本地复核通过；原始端口数据参考与按TID重建参考一致。没有模型或额外原生执行。','',
        '|深度|首拍场景|输入接受起止|首拍呈现|首个输出握手|泄漏拍|检出性质|','|---|---|---|---|---|---|---|']
    for w in witness:lines.append(f"|{w['depth']}|{w['policy']}|{w['first_input_accept']}–{w['last_input_accept']}|{w['first_cycle']}|{w['first_output_handshake']}|{w['leaked_beats']}|{w['detecting_property']}|")
    lines+=['','本地结构资格成立：仅检查首拍背压的候选保留历史目标，遗漏首拍就绪目标；仅就绪替换普通通过、历史拒绝；联合/完整正对照通过。没有模型真实额外拒绝或恢复，不能计入0/0条件恢复的分子/分母。',
        '', '两个就绪上下文及深度配置属于同一丢帧根因，不能当作四个独立Bug或四个新增机制；原始FIFO presented仍unknown。需要另外核查接口/预算控制器与未用语义空间，之后才决定是否封存模型先导。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    q.s.dump(out/'seal.json',{p.name:q.s.sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(checks=len(checks),target_frames=len(witness),qualified=True,model_calls=0)))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--run',required=True,type=Path);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args();q.s.isolation();audit(a.run.resolve(),a.out.resolve())
