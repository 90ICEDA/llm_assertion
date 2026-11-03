"""Freeze the accepted research62 collection, then test fresh Ibex words.

No model calls, candidate edits, selection, or result-dependent regeneration.
WSL python3 scripts/research63_independent.py run --out deliverables/NEW_DIRECTORY
"""
import argparse
import collections
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import secrets
import shutil
from unittest.mock import patch

import research51_history_loop as old
import research54_complementary_sva as guards

ROOT = old.ROOT
SOURCE = ROOT/'deliverables/research62_comparison_20261023_r01'
PREP = ROOT/'deliverables/research59_prepare_20261023_r01'
CONFIGS = [dict(RV32E=0, RV32M=1), dict(RV32E=0, RV32M=0),
           dict(RV32E=1, RV32M=1), dict(RV32E=1, RV32M=0)]
FAMILIES = ('branch_reserved', 'op_bit28', 'branch_legal', 'op_control')
read, dump, sha = old.read, old.dump, old.digest


def now():
    return datetime.now(timezone.utc).isoformat()


def used_words(value):
    """Conservative exclusion of structured words and hex words in prompts."""
    found = set()
    def add(v):
        if type(v) is int and 0 <= v < 2**32:
            found.add(v)
        elif isinstance(v, str):
            try:
                found.add(int(v, 16) if v.startswith('0x') else int(v))
            except ValueError:
                pass
    def walk(v, key=''):
        if isinstance(v, dict):
            for k, child in v.items():
                walk(child, k)
        elif isinstance(v, list):
            for child in v:
                walk(child, key)
        elif isinstance(v, str):
            if key in ('instruction', 'instruction_hex', 'word', 'word_hex'):
                add(v)
            for token in re.findall(r"(?<![\w])(?:0x|32'[hH])([0-9a-fA-F]{8})(?![0-9a-fA-F])", v):
                found.add(int(token, 16))
            # Model requests serialize their user payload as a JSON string.
            if v.lstrip().startswith(('{', '[')):
                try:
                    walk(json.loads(v))
                except (ValueError, RecursionError):
                    pass
        elif key in ('instruction', 'word') or 'instructions' in key or key == 'unique_words':
            add(v)
    walk(value)
    return {x for x in found if 0 <= x < 2**32}


def inventory():
    roots = [p for p in (ROOT/'deliverables').iterdir() if p.is_dir() and
             (re.match(r'research(?:5[1-9]|6[0-2])_', p.name) or
              p.name == 'research15_history_20261015_r01')]
    words, files = set(), []
    selector = re.compile(r'transactions|samples|cases|request|payload|preview|windows|decoded|development_manifest')
    for root in sorted(roots):
        for parent, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in ('obj_dir', '__pycache__', '.git')]
            for name in sorted(names):
                if not name.endswith('.json') or not selector.search(name):
                    continue
                path = Path(parent)/name
                local = used_words(read(path))
                files.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                                  words=sorted(local)))
                words.update(local)
    known = {t['instruction'] for cohort in ('history', 'search', 'alignment')
             for t in read(PREP/(cohort+'_cases.json'))}
    assert known <= words
    return dict(roots=[p.relative_to(ROOT).as_posix() for p in sorted(roots)],
                policy='All transaction/sample/case/request/payload/preview/window/decoded/development-manifest JSON in original15 and research51..62; structured words plus conservative 8-digit hex literals in prompts. Includes rejected trials and any prior test words in this lineage. Does not claim unseen by model pretraining.',
                files=files, words=sorted(words), known_preparation_words=len(known))


def generate(seed, excluded):
    rng = random.Random(seed)
    used = set(excluded)
    txns = []
    for index in range(96):
        family, stratum = FAMILIES[index % 4], index // 4
        while True:
            word = (rng.randrange(16) << 20) | (rng.randrange(16) << 15) | (rng.randrange(1, 16) << 7)
            if family.startswith('branch'):
                f3 = (2, 3)[stratum % 2] if family == 'branch_reserved' else (0, 1, 4, 5, 6, 7)[stratum % 6]
                # Branch immediate bits are unrestricted; half explicitly have bit28=1.
                high = rng.randrange(128)
                high = (high & ~8) | ((stratum % 2) << 3)
                word |= (high << 25) | (f3 << 12) | 0x63
            else:
                f7 = (8, 9, 0x28)[stratum % 3] if family == 'op_bit28' else (0, 1, 0x20)[stratum % 3]
                f3 = (stratum // 3) % 8
                if f7 == 0x20:
                    f3 = (0, 5)[(stratum // 3) % 2]
                word |= (f7 << 25) | (f3 << 12) | 0x33
            if word not in used:
                break
        used.add(word)
        txns.append(dict(id=index, instruction=word, family=family,
                         hold_samples=2 + stratum % 8, generation_source='frozen_protocol_holdout'))
    return txns


def freeze(out):
    assert read(SOURCE/'outcome.json')['status'] == 'accepted_development_only'
    assert read(SOURCE/'v0/decision.json')['accepted']
    assert read(ROOT/'deliverables/research63_acceptance_audit_20261023_r01/audit.json')['passed']
    out.mkdir(parents=True, exist_ok=False)
    candidate = read(SOURCE/'accepted_candidate.json')
    assert old.acceptance.sha(candidate) == read(SOURCE/'outcome.json')['accepted_candidate_sha256']
    shutil.copy2(SOURCE/'accepted_candidate.json', out/'candidate.json')
    (out/'candidate.sva').write_text('\n'.join(a['property'] for a in candidate['assertions'])+'\n')
    for rev in ('before', 'after'):
        shutil.copytree(PREP/rev, out/rev)
    binding=read(PREP/'source_binding.json')
    for name,digest in binding['source_sha256'].items():
        assert sha(out/name)==digest, name
    dump(out/'source_binding.json', binding)
    binary,env=old.native.runner.native_environment()
    tool_record,version=old.native.runner.command([binary,'--version'],out,'tool_version',15,env)
    assert tool_record['exit_code']==0
    dump(out/'tool_config.json',dict(binary=binary,binary_sha256=sha(binary),version=version.strip(),
        verilator_root=env.get('VERILATOR_ROOT'),verilator_bin=env.get('VERILATOR_BIN'),
        flags=['--binary','--timing','--assert','--trace','-j','2','-Wno-fatal'],timeout_seconds=240))
    dump(out/'development_exclusion.json', inventory())
    protocol = dict(case='original Ibex #166 decoder', count=96, family_counts=dict.fromkeys(FAMILIES,24),
        configurations=CONFIGS, new_configuration=dict(RV32E=1,RV32M=0),
        phases='Each word has 2..9 samples; first instr_new=1 then same bits held with instr_new=0. Each hold length occurs three times per family.',
        strata='BRANCH covers all legal/reserved funct3, 12 words per branch family have bit28=1. OP target cycles funct7=8,9,40 and all funct3. OP controls include base operations, legal SUB/SRA, and M encodings (illegal when RV32M=0). All register operands <16.',
        generation='Seed drawn only after freeze.json exists. Reject only word collisions, never native outcomes. No regeneration or candidate selection.',
        acceptance='Native completion; zero misses, false alarms across ALL properties, critical unknown, required-untriggered. Each target obligation must have actual buggy violation/fixed satisfaction and detection in every config, first AND held. Each config must expose legal controls.',
        independence='Instruction-word disjoint from recorded lineage development and prior tests; same known bug mechanisms, not new bug discovery. No model calls or feedback.',
        failure_policy='Retain frozen candidate and all test failures. If later used for modifications, entire batch becomes development and fresh tests are required.',
        scope='Combinational original decoder only, not FIFO, whole-core execution, trap/retire, or formal proof.')
    dump(out/'protocol.json', protocol)
    provenance = [SOURCE/'accepted_candidate.json', SOURCE/'outcome.json', SOURCE/'v0/decision.json', SOURCE/'cost.json']
    provenance += [p for p in (SOURCE/'v0/model_call').iterdir() if p.is_file()]
    code = sorted((ROOT/'scripts').glob('*.py'))
    dump(out/'provenance.json', dict(source_files={p.relative_to(ROOT).as_posix():sha(p) for p in provenance},
                                   python_sources={p.relative_to(ROOT).as_posix():sha(p) for p in code}))
    files = [p for p in out.rglob('*') if p.is_file()]
    dump(out/'freeze.json', dict(frozen_at=now(), candidate_sha256=old.acceptance.sha(candidate),
        files={p.relative_to(out).as_posix():sha(p) for p in files},
        assertion_origin='Actual research62 component-refinement model output, no predicate edits',
        git_commit=None, version_policy='Content hashes; historical Git revision unavailable'))


def verify_freeze(out):
    frozen = read(out/'freeze.json')
    for name, digest in frozen['files'].items():
        assert sha(out/name) == digest, name
    provenance = read(out/'provenance.json')
    for group in provenance.values():
        for name, digest in group.items():
            assert sha(ROOT/name) == digest, name
    tool=read(out/'tool_config.json')
    assert sha(tool['binary'])==tool['binary_sha256']
    return frozen


def native_audit(out, result):
    """Recompute row attribution from raw logs; fixed disagreement stays unknown."""
    candidate = read(out/'candidate.json')
    folder = out/'independent'
    rows = old.samples(read(out/'independent_cases.json'), 'independent')
    assert read(folder/'samples.json') == rows
    trace, marks = {}, {}
    for rev in ('before','after'):
        path = folder/rev
        n = read(path/'result.json')
        assert n['compile_status'] == 'passed' and n['execution_status'] == 'completed'
        assert n['tool_version']==read(out/'tool_config.json')['version']
        assert (path/'tb.sv').read_text() == old.bench(candidate, rows, CONFIGS, folder/'stimulus.txt')
        assert all(str(out/rev/name) in n['compile']['argv'] for name in ('ibex_decoder.sv','ibex_defines.sv'))
        trace[rev] = {}
        log = (path/'execute.log').read_text()
        assert 'NATIVE_RUN_COMPLETE' in log and (path/'wave.vcd').stat().st_size > 0
        for line in log.splitlines():
            if line.startswith('TRACE '):
                fields = dict(v.split('=') for v in line.split()[1:])
                sid = int(fields['sample'])
                assert sid not in trace[rev]
                trace[rev][sid] = fields
        assert set(trace[rev]) == set(range(len(rows)))
        marks[rev] = {kind:{(m[0],int(m[1])) for m in re.findall(r'^'+kind+r' (\w+) cycle=(-?\d+)$',log,re.M)}
                      for kind in ('TRIGGER','ASSERT_FAIL')}
        for kind, label in [('TRIGGER','triggers'),('ASSERT_FAIL','failures')]:
            assert marks[rev][kind] == {(x['id'],int(re.search(r'cycle=(-?\d+)',x['detail'])[1])) for x in n[label]}
    for r in result['ledger']:
        s, cfg, rev = r['sample'], r['configuration'], r['revision']
        sid, ci = s['sample_id'], CONFIGS.index(cfg)
        expected = old.historical.oracle(s['instruction'],s['instr_new'],cfg)
        actual = {v:(int(trace[v][sid]['observed'],2)>>ci)&1 for v in trace}
        assert r['expected']==expected and r['observed']==actual[rev]
        assert r['native']['attribution_status']==('confirmed' if actual['after']==expected else 'unknown')
        for v in trace:
            t=trace[v][sid]
            assert (int(t['instr'],16),int(t['new']),int(t['txn']),int(t['phase'])) == (s['instruction'],s['instr_new'],s['transaction_id'],s['phase'])
        for a in r['native']['assertions']:
            prop=next(p for p in candidate['assertions'] if p['id']==a['id'])
            name=a['id']+f'_c{ci}'
            trigger=(name,sid-prop['delay']) in marks[rev]['TRIGGER']
            failed=(name,sid) in marks[rev]['ASSERT_FAIL']
            detected=(rev=='before' and actual[rev]!=expected and actual['after']==expected and trigger and failed and (name,sid) not in marks['after']['ASSERT_FAIL'])
            assert (a['trigger'],a['failed'],a['causal_detection']) == (trigger,failed,detected)
    info=old.acceptance.inspect(result['ledger'])
    assert not info['errors'] and len(result['ledger'])==len(rows)*len(CONFIGS)*2
    assert len(result['reference'])==len(rows)*len(CONFIGS)
    lookup={(r['sample']['sample_id'],CONFIGS.index(r['configuration']),r['revision']):r for r in result['ledger']}
    for ref in result['reference']:
        ci=CONFIGS.index(ref['configuration'])
        for rev in ('before','after'):
            entry=lookup[(ref['sample_id'],ci,rev)]
            assert ref['actual'][rev]==entry['observed'] and ref['expected']==entry['expected']
    assert result['counts']=={k:len(info[k]) for k in result['counts']}
    assert result['mapping']==info['mapping']
    assert set(result['required_untriggered'])=={k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']}
    return dict(passed=True, rows_audited=len(result['ledger']), native_revisions=2)


def summarize(result, guard):
    info=old.acceptance.inspect(result['ledger'])
    groups={}
    for cfg in CONFIGS:
        for ob in (*old.OBLIGATIONS, 'encoding_controls'):
            for phase in ('first','held'):
                key=f"E{cfg['RV32E']}M{cfg['RV32M']}/{ob}/{phase}"
                subset=[r for r in result['ledger'] if r['configuration']==cfg and r['obligation']==ob and ('first' if r['sample']['phase']==0 else 'held')==phase]
                ids={r['evidence_id'] for r in subset}
                exposure=[r for r in subset if r['revision']=='before' and r['oracle']['verdict']=='violated' and r['native']['attribution_status']=='confirmed']
                groups[key]=dict(configuration=cfg,obligation=ob,phase=phase,rows=len(subset),
                    actual_target_exposure=len(exposure),detections=len(ids & info['detections']),
                    misses=len(ids & info['misses']),false_positives=len(ids & info['false_positives']),
                    unknown=len(ids & info['unknown']),required_untriggered=len(ids & set(result['required_untriggered'])),
                    triggered_rows=len(ids & info['triggers']),
                    legal_encoding_rows=sum(r['expected']==0 and r['observed']==0 for r in subset))
    exposed=all(g['actual_target_exposure']>0 for g in groups.values() if g['obligation'] in old.OBLIGATIONS)
    controls=all(g['legal_encoding_rows']>0 for g in groups.values() if g['obligation']=='encoding_controls')
    passed=bool(old.admissible(result) and guard['accepted'] and exposed and controls)
    return dict(passed=passed,counts=result['counts'],required_untriggered=len(result['required_untriggered']),
                target_exposure_complete=exposed,legal_control_exposure_complete=controls,groups=groups,
                all_property_guard=guard,scope=result['scope'])


def report(out, summary):
    excluded=read(out/'development_exclusion.json'); seed=read(out/'generation.json')['seed']
    cost=read(out/'cost.json')['total']
    rows=['# research63：冻结后独立验收', '',
          f"结果：**{'通过' if summary['passed'] else '未通过'}**。冻结 research62 接受集合后生成 96 个新指令字，排除清单含 {len(excluded['words'])} 个已用或保守排除的编码，随机种子 `{seed}`。", '',
          '四类各24个指令字；每字2–9个采样，覆盖首周期和保持阶段。四种RV32E/RV32M配置，新增E1/M0。合法BRANCH含12个bit28=1编码，检查类别外误报；OP控制包括受RV32M配置影响的M编码。', '',
          '|配置|义务/控制|阶段|实际违例曝光|检出|漏报|误报|unknown|必检未触发|',
          '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for g in summary['groups'].values():
        c=g['configuration']
        rows.append(f"|E{c['RV32E']}M{c['RV32M']}|{g['obligation']}|{g['phase']}|{g['actual_target_exposure']}|{g['detections']}|{g['misses']}|{g['false_positives']}|{g['unknown']}|{g['required_untriggered']}|")
    rows += ['', f"总体计数：`{json.dumps(summary['counts'])}`。全性质误报检查：{len(summary['all_property_guard']['false_alarms'])}；归因unknown：{len(summary['all_property_guard']['unknown'])}。", '',
        '计数单位是采样×配置×版本的证据点；不是独立Bug数。控制组实际违例曝光为0不代表目标义务缺少曝光。', '',
        f"实际成本：模型调用{cost['model_calls']}、tokens 0；原生编译{cost['native_compile_calls']}次，执行{cost['native_execute_calls']}次；编译耗时合计{cost['native_compile_wall_seconds']:.3f}秒，执行{cost['native_execute_wall_seconds']:.3f}秒，形式化调用0。", '',
        '断言、RTL、开发排除清单和规则先写入freeze.json，随后生成种子及新测试；原生日志、测试平台、波形位于independent/before和after。原断言及历史结果未修改。若未来利用本批结果细化，整批转为开发数据，另建独立测试。', '',
        '仅支持原始decoder模块有限样本下的两项义务结论；不证明整核、FIFO、所有编码或形式化正确性，也不度量机制额外收益。新词与记录的项目数据不重叠，不等于模型预训练未见。', '',
        '复核命令：', '```powershell',
        f'wsl -- python3 scripts/research63_independent.py audit --out {out.relative_to(ROOT).as_posix()}',
        '```', '', '新运行（必须使用新目录，冻结后重新生成种子）：', '```powershell',
        'wsl -- python3 scripts/research63_independent.py run --out deliverables/research63_independent_NEW', '```']
    (out/'SUMMARY.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


def audit(out):
    frozen=verify_freeze(out)
    generation=read(out/'generation.json')
    assert generation['freeze_sha256']==sha(out/'freeze.json') and generation['generated_at']>frozen['frozen_at']
    txns=read(out/'independent_cases.json'); excluded=set(read(out/'development_exclusion.json')['words'])
    assert txns==generate(generation['seed'],excluded)
    assert len(txns)==len({t['instruction'] for t in txns})==96
    assert not excluded & {t['instruction'] for t in txns}
    assert collections.Counter(t['family'] for t in txns)==dict.fromkeys(FAMILIES,24)
    result=read(out/'independent/result.json')
    verified=native_audit(out,result)
    with patch.object(old,'CONFIGS',CONFIGS):
        guard=guards.all_property_guard(result,{rev:read(out/'independent'/rev/'result.json') for rev in ('before','after')},read(out/'candidate.json'))
    summary=summarize(result,guard)
    if (out/'summary.json').exists():
        assert read(out/'summary.json')==summary
    dump(out/'summary.json',summary)
    dump(out/'audit.json',dict(**verified,freeze_unchanged=True,words_disjoint=True,independent_passed=summary['passed']))
    report(out,summary)
    print('INDEPENDENT',json.dumps(dict(passed=summary['passed'],counts=summary['counts'],audit=verified)),flush=True)


def run(out):
    freeze(out)
    seed=secrets.randbits(63)
    dump(out/'generation.json',dict(seed=seed,generated_at=now(),freeze_sha256=sha(out/'freeze.json')))
    excluded=read(out/'development_exclusion.json')['words']
    txns=generate(seed,excluded)
    dump(out/'independent_cases.json',txns)
    print('FROZEN_THEN_GENERATED',len(txns),'excluded',len(excluded),flush=True)
    result=old.replay(read(out/'candidate.json'),txns,'independent',out/'independent',out,configs=CONFIGS)
    verify_freeze(out)
    dump(out/'cost.json',old.cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    if not result['healthy']:
        dump(out/'blocked.json',dict(status='native_execution_incomplete',native_status=result['native_status'],frozen_unchanged=True))
        print('NATIVE_INCOMPLETE',flush=True)
        return
    audit(out)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['run','audit'])
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    (run if args.action=='run' else audit)(args.out.resolve())
