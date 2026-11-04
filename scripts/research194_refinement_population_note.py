"""Read-only reconciliation of case-card and refinement sensitivity populations."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def analyze(root):
    out=root/'deliverables/research194_refinement_posthoc_20261103_r01'
    card_path=root/'deliverables/reguard_mechanisms_20261103_r02/case_cards/case_cards.json'
    pair_path=out/'independent_refinement_pairs.json'
    cards=read(card_path)
    card=next(c for c in cards if c.get('mechanism')=='localized_refinement' and c.get('kind')=='positive')
    trajectory=card['trajectory'];case=trajectory['case_id'];seed=trajectory['seed']
    pairs=[p for p in read(pair_path)['pairs'] if (p['case_id'],p['seed'],p['comparison'])==(case,seed,'R3_vs_R0')]
    comparator=root/'deliverables/research194_campaign_execute_20261103_r01/base'/case/str(seed)/'S0_R0/refinement'
    rounds_path=comparator/'rounds.json'
    unknown_rounds=[dict(round=r['round'],outer_status=r['status'],model_status=r.get('model',{}).get('status'),
        critical_unknown=r['decision']['critical_unknown']) for r in read(rounds_path) if r.get('decision',{}).get('critical_unknown')]
    result=dict(status='completed_read_only',case_id=case,seed=seed,full_positive_chain=card['full_positive_chain'],
        card_selection_rule=card['selection_reason']['rule'],
        card_qualification=card['selection_reason']['qualification'],
        card_gained_count=len(card['selection_reason']['gained_ids']),card_lost_count=len(card['selection_reason']['lost_ids']),
        conservative_sensitivity_pairs=[dict(fault=p['fault'],eligible_comparable=p['eligible_comparable'],
            strict_execution_eligible=p['strict_execution_eligible'],strict_exclusion_reasons=p['strict_exclusion_reasons'],
            any_cycle_gained=len(p['any_cycle']['gained_ids']),any_cycle_lost=len(p['any_cycle']['lost_ids'])) for p in pairs],
        comparator_unknown_proposals=unknown_rounds,
        interpretation_zh=[
            '该Arbiter正面卡具有真实模型组合修改、开发证据改善、冻结保持及独立验收改善完整链；并非一次局部字段修改的单独收益。',
            '案例卡将正常收到模型响应且完成原生拒绝决定视为completed_round_decision。三轮是上限，比较臂两轮后停止不自动取消案例资格。',
            'refinement strict_execution是另一更保守的敏感性子集：即使提案被拒绝、保留版本最终独立可判定，任何开发提案critical_unknown也会排除该配对。',
            '因此应表述为“无任何开发提案unknown等情况的保守敏感性子集中未保留正增益”，不能表述为“没有合格正面链”或“严格案例卡无增益”。',
            '本例独立增益48均来自primary新输入；两个reserved新故障无新增检出，不将该例表述为新故障泛化收益。',
            '本核对不改变任一筛选规则、候选、模型记录或独立实验。'],
        source_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [card_path,pair_path,rounds_path]})
    (out/'population_qualification_reconciliation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(dict(status=result['status'],case_id=case,seed=seed,positive_chain=result['full_positive_chain'],gained=result['card_gained_count']))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    analyze(p.parse_args().root.resolve())
