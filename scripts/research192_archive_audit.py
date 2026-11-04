"""Read-only historical REGuard matrix; never re-label archived tests as new runs.

Outputs are exclusive, outside old experiment directories. No model/simulator/network.
This inventory is bounded to research archives through 191 and three named datasets.
"""
import argparse
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'deliverables'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main(out, index=None):
    out = out.resolve()
    if not out.is_relative_to(D) or out == D:
        raise ValueError('Use a new directory under deliverables')
    out.mkdir(exist_ok=False)
    bindings = {}
    started = time.monotonic()

    def read(relative):
        path = ROOT / relative
        bindings[rel(path)] = sha(path)
        return json.loads(path.read_text(encoding='utf-8-sig'))

    def save(name, value):
        (out/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    def table(name, rows):
        if not rows:
            return
        fields = list(dict.fromkeys(k for row in rows for k in row))
        with (out/name).open('w', newline='', encoding='utf-8-sig') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict,list)) else v for k,v in row.items()})

    # No broad rglob into simulator build trees or unrelated outputs.
    archives = []
    names = {'summary.json','outcome.json','result.json','results.json','protocol.json',
             'cost.json','audit.json','checks.json','obligation_matrix.json','acceptance.json',
             'candidate.json','candidate.sva','initial.json','initial.sva','assertions.json',
             'model_edit.json','feedback.json','decision.json','measurement.json','terminal_versions.json',
             'evidence_examples.json','obligation_catalog.json','pairs_frozen.json',
             'source_bindings.json','seal.json','freeze.json','result_seal.json','combined_summary.json'}
    pruned = {'native','execution','executions','selection','cycles','tools','obj_dir','__pycache__',
              'sources','before','after','correct','corrupt','tests','test','independent','holdout'}
    roots=[]
    if index:
        archives=read(rel(index))
        assert all((ROOT/a['path']).is_relative_to(D) for a in archives)
        bindings.update({a['path']:a['sha256'] for a in archives})
        roots=sorted({a['run'] for a in archives})
    for folder in ([] if index else sorted(D.glob('research*'))):
        m=re.match(r'research(\d+)',folder.name)
        if folder.is_dir() and (not m or int(m[1]) <= 191):
            roots.append(folder)
            for base, dirs, files in os.walk(folder):
                depth=len(Path(base).relative_to(folder).parts)
                # Full simulation trees have millions of files. Top-level
                # summaries preserve links into those immutable trees; selected
                # model/trace chains are separately bound in case_cards.json.
                dirs[:] = [x for x in dirs if x not in pruned and not x.startswith('obj') and depth<1]
                for name in sorted(set(files)&names):
                    p=Path(base)/name
                    digest=sha(p)
                    bindings[rel(p)]=digest
                    archives.append(dict(run=folder.name,path=rel(p),sha256=digest,bytes=p.stat().st_size,
                        role='candidate' if name in ('candidate.json','candidate.sva','initial.json','initial.sva','assertions.json','model_edit.json') else
                             'obligations' if 'obligation' in name else 'evidence' if name in ('feedback.json','measurement.json','evidence_examples.json') else 'acceptance_or_provenance'))
    save('archive_index.json',archives)

    search_path='deliverables/research_search_20261014_r01/'
    all_pairs=read(search_path+'pairs_frozen.json')
    pairs=[p for p in all_pairs if p['natural_pair'] and p['status']=='distinguished_on_checked_legal_inputs']
    save('all_25_archived_pairs.json',all_pairs)
    pair_rows=[]
    for p in pairs:
        obligation=p.get('obligation')
        if obligation and (ROOT/obligation).is_file():
            bindings[obligation]=sha(ROOT/obligation)
        pair_rows.append(dict(pair_id=p['pair_id'],parent_bug_id=p['parent_bug_id'],
            initial_a=p['assertion_a'],initial_b=p['assertion_b'],obligation=obligation,
            initial_source=search_path+'pairs_frozen.json',search_results=search_path+'pair_results.json',
            evidence=search_path+'evidence_examples.json',native_sva=False,role='historical_development'))
    save('initial_11_pairs.json',pair_rows)
    old=read(search_path+'summary.json')
    search_rows=[dict(cohort='historical_11_pairs_six_parents',strategy=k,queries=old['queries']//4,
        gaps=v['gaps'],unknown=v['unknown_spec_queries'],native_sva=False,new_result=False,
        unit='parent/candidate/confirmed-gap; not independent parents',source=search_path+'summary.json')
        for k,v in old['per_method'].items()]
    newer_path='deliverables/research125_search_expansion_report_20261025_r01/result.json'
    newer=read(newer_path)
    for k,v in newer['methods'].items():
        search_rows.append(dict(cohort='historical_fifo_search_expansion',strategy=k,queries=v['queries'],
            gaps=len(v['keys']),mechanism_gaps=len(v['mechanism_keys']),unknown=v['critical_unknown'],
            exclusive_gaps=len(newer['contract_exclusive_keys']) if k=='contract_novelty' else None,
            native_executions=v['native_executes'],native_seconds=v['native_wall_seconds'],
            new_result=False,unit='candidate+obligation+mechanism; one artificial fault cohort',source=newer_path))
    table('historical_search_matrix.csv',search_rows)

    # Summaries retain native count units; no sampled-cycle count is a parent count.
    fifo_path='deliverables/research190_fifo_independent_20261103_r01/summary.json'
    fifo=read(fifo_path)
    adapter_path='deliverables/research174_independent_run_20261028_r01/result.json'
    adapter=read(adapter_path)
    ibex_path='deliverables/research145_stability_real_20261027_r01/results.json'
    ibex=read(ibex_path)['overall']
    ibex_audit=read('deliverables/research151_stability_audit_20261027_r01/audit.json')
    readiness=[
        dict(parent_bug='onehot/multihot',design='onehot',historical_original_fix='unconfirmed_mutation_cohort',
             target_reachable=True,independent_reference=True,native_sva_qualified=False,
             required_obligations='multihot_detect',independent_acceptance='not_established',
             limitation='procedural search regression; no new full native learned-SVA acceptance',source=search_path+'parent_method_results.json'),
        dict(parent_bug='axis_fifo/artificial_boundary_family',design='complex_FIFO',historical_original_fix=False,
             target_reachable=True,independent_reference=True,native_sva_qualified=True,
             required_obligations='order_payload,drain_no_loss,stall_stability,no_unsolicited_output',
             independent_acceptance='bounded_prior_acceptance_and_development_supplement',
             limitation='same fault operators reused; seed holdout is not unseen-fault generalization',
             source='deliverables/research130_local_20261026_r01/outcome.json'),
        dict(parent_bug='axis_fifo/original_atomic_oversize_drop',design='complex_FIFO',historical_original_fix=True,
             target_reachable=True,independent_reference=True,native_sva_qualified=True,
             required_obligations='atomic_oversize_frame_drop',independent_acceptance='failed_exposure_20_of_32',
             limitation='initial reset only; no formal/global FIFO claim',source=fifo_path),
        dict(parent_bug='axis_adapter/original_TKEEP',design='protocol_adapter',historical_original_fix=True,
             target_reachable=True,independent_reference=True,native_sva_qualified=True,
             required_obligations='nonfinal_full_keep,final_nonempty_keep,legal_stall,legal_reset_cancel',
             independent_acceptance='failed_exposure_37_of_40',limitation='8to32 fixed; three legal scenes lacked actual backpressure',source=adapter_path),
        dict(parent_bug='lowRISC/ibex#166',design='Ibex_decoder',historical_original_fix=True,
             target_reachable=True,independent_reference=True,native_sva_qualified=True,
             required_obligations='illegal_branch_persists,op_bit28_illegal',independent_acceptance='7_frozen_versions_passed_one_parent',
             limitation='O/H equivalent; recovery0/0; decoder scope excludes flush and full pipeline',source=ibex_path),
        dict(parent_bug='lowRISC/ibex#54',design='Ibex_compressed_decoder',historical_original_fix=True,
             target_reachable=True,independent_reference=True,native_sva_qualified=True,
             required_obligations='ISA_HINT_and_shift_boundaries',independent_acceptance='historical_module_reproduction',
             limitation='strict unseen-low16 space exhausted in research164; no new learned-SVA acceptance',
             source='deliverables/research164_feasibility_20261028_r02/SUMMARY.md'),
        dict(parent_bug='new_arbiter',design='Arbiter',historical_original_fix=False,target_reachable='unqualified',
             independent_reference='not_audited',native_sva_qualified=False,independent_acceptance='not_run',
             limitation='materialized synthetic hold mutants and wave differences do not prove target obligation violations',
             source='rtl_cases_real_scale210_independent/case427_arbiter_temporal_hold_1/case_metadata.json'),
        dict(parent_bug='new_timer_counter',design='Timer_Counter',historical_original_fix='unqualified',target_reachable='unknown',
             independent_reference='unknown',native_sva_qualified=False,independent_acceptance='not_run',
             limitation='case recruitment needed; exact latency, reset cancellation, wrap boundary',source=None),
        dict(parent_bug='new_UART',design='UART',historical_original_fix='unqualified',target_reachable='unknown',
             independent_reference='unknown',native_sva_qualified=False,independent_acceptance='not_run',
             limitation='case recruitment needed; start/data/stop, busy handshake, reset',source=None),
    ]
    table('cross_design_readiness.csv',readiness)
    save('cross_design_readiness.json',readiness)
    acceptance=[
        dict(parent_bug='axis_fifo/original_atomic_oversize_drop',population_unit='scenario',planned=fifo['total_scenarios'],
             passed=fifo['passed_scenarios'],exposed_targets=fifo['target_exposure'],misses=fifo['target_misses'],
             false_positives=fifo['false_positive_records'],missing_exposure=fifo['missing_exposure'],
             unknown=fifo['critical_unknown_records'],whole_scope_pass=fifo['whole_scope_pass'],source=fifo_path),
        dict(parent_bug='axis_adapter/original_TKEEP',population_unit='scenario',planned=adapter['scenario_total'],
             passed=adapter['scenario_passed'],exposed_targets=adapter['target_exposure'],misses=adapter['target_misses'],
             false_positives=adapter['false_positive_before']+adapter['false_positive_after'],missing_exposure=3,
             unknown=len(adapter['unknown']),whole_scope_pass=False,source=adapter_path),
        dict(parent_bug='lowRISC/ibex#166',population_unit='proposal_seed_cell',planned=ibex['planned'],
             passed=ibex['whole_schedule_success']['numerator'],frozen_versions=ibex['unique_version_independent_pass']['denominator'],
             frozen_versions_passed=ibex['unique_version_independent_pass']['numerator'],
             misses=sum(x['counts']['misses'] for x in ibex_audit['independent_versions'].values()),
             false_positives=sum(x['counts']['false_positives'] for x in ibex_audit['independent_versions'].values()),
             unknown=ibex['critical_unknown_points'],whole_scope_pass='bounded_versions_only',source=ibex_path),
    ]
    for row in acceptance:
        row.update(parent_count=1,new_experiment=False,new_fault_generalization='not_established',formal_proof=False)
    table('historical_independent_acceptance.csv',acceptance)
    save('historical_independent_acceptance.json',acceptance)

    # Capture model revision outcomes and regression reasons without treating a gate
    # qualification fixture as a successful model-generated repair.
    gate_path='deliverables/research_integration_20261014_r01/gate_results.json'
    gate=read(gate_path)
    decisions=[dict(source=gate_path,arm=x['arm'],round=x['round'],accepted=x['accepted'],
        gate_enabled=x.get('gate_enabled'),model_status=x.get('model_status'),
        reasons=[r.get('kind') for r in x.get('gate_reasons',[])],
        result_kind='historical_procedural_not_native_SVA') for x in gate['decisions']]
    for source in ['deliverables/research189_fifo_pilot_run_20261102_r01/outcome.json',
                   'deliverables/research172_adapter_run_20261028_r01/outcome.json']:
        if (ROOT/source).exists():
            x=read(source)
            decisions.append(dict(source=source,result_kind='real_model_native',status=x['status'],
                decisions=x.get('first'),conditional_recovery=x.get('conditional_recovery_numerator'),
                recovery_denominator=x.get('conditional_recovery_denominator'),independent=x.get('independent')))
    save('historical_modification_decisions.json',decisions)

    # Recruitment metadata only: these archived mutation files are development
    # material. Do not reserve already inspected mutants as final holdout.
    mutants=[]
    for dataset in ('rtl_cases_real_scale210_independent','rtl_cases_real_scale160_temporal_boosted','rtl_cases_real'):
        for path in sorted((ROOT/dataset).glob('*/case_metadata.json')):
            meta=json.loads(path.read_text(encoding='utf-8-sig'))
            module=meta.get('source_module','')
            if not any(k in (module+' '+path.parent.name).lower() for k in ('arbiter','timer','counter','uart','fifo')):
                continue
            bindings[rel(path)]=sha(path)
            edits=meta.get('mutation_edits',[])
            mutants.append(dict(dataset=dataset,case=path.parent.name,source_project=meta.get('source_project'),
                source_module=module,source_commit=meta.get('source_commit'),obligation_text=meta.get('spec'),
                fault_operator=meta.get('mutation_kind'),locations=[e.get('line') for e in edits],
                edit_count=len(edits),metadata_status=meta.get('status'),
                historical_fix_confirmed=False,compile_confirmed=False,target_violation_confirmed=False,
                result_role='recruitment_metadata_only_not_new_execution',future_split='development_only_after_this_audit',
                source=rel(path)))
    save('fault_family_recruitment.json',mutants)
    table('fault_family_recruitment.csv',mutants)
    fifo_old=read('deliverables/research_fifo_20261014_r01/summary.json')
    dev={x['mutation'] for x in fifo_old['counts'] if x['split']=='development' and x['mutation']!='correct'}
    test={x['mutation'] for x in fifo_old['counts'] if x['split']=='independent_test' and x['mutation']!='correct'}
    split=dict(status='exploratory_no_independent_fault_family_gain_yet',historical_fault_operator_overlap=sorted(dev&test),
        historical_data_note='Fresh stimulus seeds share fault operators; not unseen-fault generalization.',
        observed_metadata=len(mutants),new_mutant_executions=0,new_generalization_results=0,
        required_protocol=dict(unit='parent_bug+obligation+operator+RTL_site',
            grouping='Reserve an entire operator or RTL site before any development execution; no random seed only split.',
            qualification='compile and execute, independent obligation monitor confirms reachable violation, correct paired RTL legal, unknown excluded from success',
            arms=['random_RTL_mutation','repair_region_mutation','obligation_guided_mutation'],
            denominator='All attempted mutations including compile errors, unreachable targets and unknowns',
            acceptance='Frozen SVA against newly generated unseen site/operator instances; no feedback from final tests',
            counting='Deduplicate transaction failures by parent+obligation+fault mechanism, not failure cycles'))
    save('fault_family_split_audit.json',split)
    findings=[
        dict(mechanism='search',kind='positive_bounded',finding='Historical 11-pair differential/contract find43 vs ordinary36; non-native, candidate-gap unit, not parent success',source=search_path+'summary.json'),
        dict(mechanism='search',kind='failure',finding='576-query expansion: contract has no exclusive gaps; disagreement/raw difference uncover two mechanisms vs one for contract',source=newer_path),
        dict(mechanism='refinement',kind='regression',finding='Disabled historical gate accepted proposal with new legal false positives; preserved as procedural evidence only',source=gate_path),
        dict(mechanism='refinement',kind='no_discrimination',finding='Ibex, adapter and original FIFO direct acceptances do not establish historical-gate increment; recovery0/0',source=ibex_path),
        dict(mechanism='acceptance',kind='exposure_failure',finding='FIFO12/32 unexposed because a second overflow masks drop-state loss, not12 SVA misses',source='deliverables/research191_fifo_exposure_audit_20261103_r02/summary.json'),
    ]
    save('mechanism_findings.json',findings)
    # Source files are hashed again after the report; immutable archive checks are
    # scoped to exactly the sources consumed, not a claim to verify every old seal.
    changed=[p for p,h in bindings.items() if sha(ROOT/p)!=h]
    assert not changed, changed
    assert len(pairs)==11
    assert fifo['passed_scenarios']+fifo['missing_exposure']==fifo['total_scenarios']
    assert len(ibex_audit['independent_versions'])==ibex['unique_version_independent_pass']['denominator']
    save('source_bindings.json',bindings)
    save('summary.json',dict(mode='read_only_retrospective_audit',archive_directories=len(roots),
        indexed_artifacts=len(archives),initial_pairs=len(pairs),cross_design_rows=len(readiness),
        original_parent_independent_rows=len(acceptance),source_files=len(bindings),sources_unchanged=True,
        model_calls=0,simulation_calls=0,new_independent_runs=0,new_mechanism_increment_claim=False,
        source_scope='research archives through191; top level plus one subdirectory; named deeper records separately bound',
        wall_seconds=time.monotonic()-started))
    def html_table(rows):
        keys=list(dict.fromkeys(k for row in rows for k in row))
        return '<table><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in keys)+'</tr>'+''.join(
            '<tr>'+''.join('<td>'+html.escape(str(row.get(k,'')))+'</td>' for k in keys)+'</tr>' for row in rows)+'</table>'
    body='<!doctype html><meta charset="utf-8"><title>REGuard historical evidence audit</title><style>body{font:15px system-ui;margin:28px;color:#172338}table{border-collapse:collapse;display:block;overflow:auto;margin:20px 0}th,td{border:1px solid #ccd4df;padding:8px;text-align:left;max-width:440px}th{background:#edf2f8}p{max-width:1100px}</style>'
    body+='<h1>REGuard 历史实验统一审计</h1><p>本页仅整理既有结果，未执行新仿真或模型调用。旧结果不覆写；样本周期、场景、版本与父 Bug 分母分别保存。无曝光和 unknown 不算通过。</p>'
    body+='<h2>跨设计独立验收</h2>'+html_table(acceptance)
    body+='<p>三个历史父 Bug 并非三个完整成功：FIFO20/32与adapter37/40仍整批未通过；Ibex7个独立通过版本来自同一父Bug。不能据此宣布两个核心机制已有整体优势。</p>'
    body+='<h2>历史搜索（不可替代新S0–S3）</h2>'+html_table(search_rows)
    body+='<h2>机制有效性与失败解释</h2>'+html_table(findings)
    body+='<h2>案例准备度</h2>'+html_table(readiness)
    body+='<h2>故障族隔离</h2><p>'+html.escape(json.dumps(split,ensure_ascii=False))+'</p>'
    body+='<p>完整初始候选、义务和历史产物索引见 initial_11_pairs.json、archive_index.json；修改接受与退化见 historical_modification_decisions.json。source_bindings.json 给出所有本轮读取源文件哈希。</p>'
    (out/'report.html').write_text(body,encoding='utf-8')
    save('seal.json',{rel(p):sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(output=rel(out),indexed=len(archives),sources=len(bindings),checks='passed')))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',required=True)
    parser.add_argument('--archive-index',help='Optional prior read-only index; every source hash is still rechecked')
    args=parser.parse_args()
    main(ROOT/args.out,ROOT/args.archive_index if args.archive_index else None)
