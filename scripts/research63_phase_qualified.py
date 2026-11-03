"""Fresh independent batch with source-qualified BRANCH phase exposure.

Preserves research63 r01 as failed against its overly strong preregistration.
That entire batch is now protocol-development data, never reused as holdout.
"""
import argparse
import collections
import copy
from pathlib import Path
import secrets
import shutil
from unittest.mock import patch

import research63_independent as base

ROOT, SOURCE, PREP = base.ROOT, base.SOURCE, base.PREP
OLD = ROOT/'deliverables/research63_independent_20261023_r01'
read, dump, sha = base.read, base.dump, base.sha


def summarize(result, guard):
    summary = base.summarize(result, guard)
    targets = [g for g in summary['groups'].values() if
               g['obligation']=='op_bit28_illegal' or
               (g['obligation']=='illegal_branch_persists' and g['phase']=='held')]
    exposed = all(g['actual_target_exposure']>0 for g in targets)
    first_checks=[]
    for cfg in base.CONFIGS:
        first=[r for r in result['ledger'] if r['configuration']==cfg and
               r['obligation']=='illegal_branch_persists' and r['sample']['phase']==0]
        first_checks.append(dict(configuration=cfg, rows=len(first), passed=bool(first) and all(
            r['expected']==r['observed']==1 and r['native']['attribution_status']=='confirmed' and
            any(a['trigger'] for a in r['native']['assertions']) and
            not any(a['failed'] for a in r['native']['assertions']) for r in first)))
    summary.update(target_exposure_complete=exposed,branch_first_correct_and_triggered=first_checks,
                   exposure_rule='OP: first AND held; BRANCH: held violation, first correct output AND native trigger. Required for every config.',
                   passed=bool(base.old.admissible(result) and guard['accepted'] and exposed and
                               summary['legal_control_exposure_complete'] and all(c['passed'] for c in first_checks)))
    return summary


def preflight():
    result=read(OLD/'independent/result.json')
    guard=read(OLD/'summary.json')['all_property_guard']
    checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(dict(name=name,passed=True))
    check('old_preregistration_stays_failed',not read(OLD/'summary.json')['passed'])
    check('source_qualified_rule_on_development_batch',summarize(result,guard)['passed'])
    bad=copy.deepcopy(result)
    bad['ledger']=[r for r in bad['ledger'] if not (r['obligation']=='illegal_branch_persists' and r['sample']['phase']>0)]
    check('reject_missing_branch_held_exposure',not summarize(bad,guard)['passed'])
    bad=copy.deepcopy(result)
    bad['ledger']=[r for r in bad['ledger'] if r['configuration']!=base.CONFIGS[-1]]
    check('reject_missing_new_configuration',not summarize(bad,guard)['passed'])
    for field in ('trigger','failed'):
        bad=copy.deepcopy(result)
        row=next(r for r in bad['ledger'] if r['obligation']=='illegal_branch_persists' and r['sample']['phase']==0)
        row['native']['assertions'][0][field]=(field=='failed')
        check('reject_branch_first_'+field,not summarize(bad,guard)['passed'])
    bad=copy.deepcopy(result)
    next(r for r in bad['ledger'] if r['obligation']=='illegal_branch_persists' and r['sample']['phase']==0)['native']['attribution_status']='unknown'
    check('reject_branch_first_unknown',not summarize(bad,guard)['passed'])
    check('reject_all_property_false_alarm',not summarize(result,dict(guard,accepted=False))['passed'])
    return dict(passed=True,checks=checks,source='Previous independent batch explicitly reclassified for protocol development; no candidate modification.')


def freeze(out):
    base.verify_freeze(OLD)
    checks=preflight()
    out.mkdir(parents=True,exist_ok=False)
    candidate=read(SOURCE/'accepted_candidate.json')
    assert read(SOURCE/'v0/decision.json')['accepted']
    assert base.old.acceptance.sha(candidate)==read(SOURCE/'outcome.json')['accepted_candidate_sha256']
    assert candidate==read(OLD/'candidate.json')
    for name in ('candidate.json','candidate.sva','source_binding.json','tool_config.json'):
        shutil.copy2(OLD/name,out/name)
    for rev in ('before','after'):
        shutil.copytree(OLD/rev,out/rev)
    binding=read(out/'source_binding.json')
    for name,digest in binding['source_sha256'].items():
        assert sha(out/name)==digest
    # Retain the exact source explanation, independent of candidate predicates.
    source=(out/'before/ibex_decoder.sv').read_text()
    branch=source.split('OPCODE_BRANCH: begin',1)[1].split('OPCODE_STORE:',1)[0]
    first,held=branch.split('end else begin',1)
    assert 'if (instr_new_i)' in first and "default: illegal_insn   = 1'b1;" in first
    assert 'illegal_insn' not in held
    dump(out/'phase_basis.json',dict(before_branch_source=branch,
        explanation='The original decoder sets illegal_insn=1 for reserved BRANCH in instr_new_i=1, but skips that check in the held phase. Therefore first-cycle violation is not a legitimate requirement for reproducing this original bug. OP missing bit28 qualification affects both phases.',
        previous_batch=OLD.relative_to(ROOT).as_posix(),previous_result_stays_failed=True,
        candidate_changed=False,protocol_change_only=True))
    excluded=read(OLD/'development_exclusion.json')
    prior_words=sorted(t['instruction'] for t in read(OLD/'independent_cases.json'))
    excluded['files'].append(dict(path=(OLD/'independent_cases.json').relative_to(ROOT).as_posix(),
        sha256=sha(OLD/'independent_cases.json'),words=prior_words,role='protocol_development_entire_previous_test_batch'))
    excluded['words']=sorted(set(excluded['words'])|set(prior_words))
    excluded['policy']+=' Entire research63 r01 independent batch reclassified as protocol development and excluded.'
    assert len(excluded['words'])==247
    dump(out/'development_exclusion.json',excluded)
    protocol=read(OLD/'protocol.json')
    protocol['acceptance']='Native completion; zero misses, false alarms across ALL properties, critical unknown, required-untriggered. Every configuration must expose OP violations in first AND held phases and BRANCH violations in held phase. BRANCH first samples must have correct illegal_insn=1 in both revisions, actual antecedent trigger, and no assertion failure. Legal controls must occur in every configuration and phase.'
    protocol['previous_batch']='r01 remains failed under its original rule; all 96 words excluded here. No assertion changes.'
    dump(out/'protocol.json',protocol)
    dump(out/'preflight.json',checks)
    original=read(OLD/'provenance.json')['source_files']
    for name in ('freeze.json','summary.json','independent_cases.json','audit.json'):
        original[(OLD/name).relative_to(ROOT).as_posix()]=sha(OLD/name)
    dump(out/'provenance.json',dict(source_files=original,
        python_sources={p.relative_to(ROOT).as_posix():sha(p) for p in sorted((ROOT/'scripts').glob('*.py'))}))
    dump(out/'freeze.json',dict(frozen_at=base.now(),candidate_sha256=base.old.acceptance.sha(candidate),
        files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()},
        assertion_origin='Same accepted real-model research62 collection; byte-identical to r01',
        git_commit=None,version_policy='Content hashes; historical Git revision unavailable'))


def audit(out):
    frozen=base.verify_freeze(out)
    generation=read(out/'generation.json')
    assert generation['freeze_sha256']==sha(out/'freeze.json') and generation['generated_at']>frozen['frozen_at']
    txns=read(out/'independent_cases.json');excluded=set(read(out/'development_exclusion.json')['words'])
    assert txns==base.generate(generation['seed'],excluded)
    assert len(txns)==len({t['instruction'] for t in txns})==96
    assert not excluded & {t['instruction'] for t in txns}
    assert collections.Counter(t['family'] for t in txns)==dict.fromkeys(base.FAMILIES,24)
    assert read(out/'independent/transactions.json')==txns
    result=read(out/'independent/result.json')
    verified=base.native_audit(out,result)
    with patch.object(base.old,'CONFIGS',base.CONFIGS):
        guard=base.guards.all_property_guard(result,{rev:read(out/'independent'/rev/'result.json') for rev in ('before','after')},read(out/'candidate.json'))
    summary=summarize(result,guard)
    if (out/'summary.json').exists():
        assert read(out/'summary.json')==summary
    dump(out/'summary.json',summary)
    dump(out/'audit.json',dict(**verified,freeze_unchanged=True,words_disjoint=True,
                             independent_passed=summary['passed'],old_batch_stays_failed=True))
    base.report(out,summary)
    report=(out/'SUMMARY.md').read_text()
    report=report.replace('scripts/research63_independent.py','scripts/research63_phase_qualified.py')
    report=report.replace('计数单位是采样',
        '首批r01因我设置的曝光规则错误而未通过，原记录保留且全部96词转为协议开发数据。本批重新冻结并排除这些词。BRANCH首周期原始RTL本来正确，检查输出正确及实际触发；保持阶段才要求历史违例曝光。OP两阶段都要求真实违例曝光。没有修改断言。\n\n计数单位是采样')
    (out/'SUMMARY.md').write_text(report,encoding='utf-8')
    # Illustrations use actual frozen-test records; no feedback or selection.
    examples=[]
    for family in base.FAMILIES:
        txn=next(t for t in txns if t['family']==family and (family!='branch_legal' or t['instruction']&(1<<28)))
        examples.append(dict(transaction=txn,instruction_hex=f"0x{txn['instruction']:08x}",
            records=[r for r in result['ledger'] if r['sample']['transaction_id']==txn['id']]))
    dump(out/'case_examples.json',examples)
    print('QUALIFIED_INDEPENDENT',summary['passed'],summary['counts'],flush=True)


def run(out):
    freeze(out)
    seed=secrets.randbits(63)
    dump(out/'generation.json',dict(seed=seed,generated_at=base.now(),freeze_sha256=sha(out/'freeze.json')))
    txns=base.generate(seed,read(out/'development_exclusion.json')['words'])
    dump(out/'independent_cases.json',txns)
    print('REFROZEN_THEN_GENERATED',len(txns),'excluded',247,flush=True)
    result=base.old.replay(read(out/'candidate.json'),txns,'independent',out/'independent',out,configs=base.CONFIGS)
    base.verify_freeze(out)
    dump(out/'cost.json',base.old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    if not result['healthy']:
        dump(out/'blocked.json',dict(status='native_execution_incomplete',native_status=result['native_status'],frozen_unchanged=True))
        return
    audit(out)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['run','audit'])
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    (run if a.action=='run' else audit)(a.out.resolve())
