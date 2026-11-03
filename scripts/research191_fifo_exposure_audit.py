"""Read-only causal audit of research190 exposure, using archived native VCDs.

No new stimulus, simulator, model, candidate, or acceptance-rule changes.
VCD pre-edge samples must match the original TRACE logs before internal state
is used. Post-edge registers are checked separately, never used as SVA samples.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'deliverables/research190_fifo_independent_20261103_r01'
RTL = ROOT / 'deliverables/research183_history_prepare_20261101_r01/frame_fifo_drop'
PORTS = dict(cycle='cycle', rst='rst', sv='s_axis_tvalid', sr='s_axis_tready',
    sd='s_axis_tdata', sl='s_axis_tlast', sid='s_axis_tid', dest='s_axis_tdest',
    mv='m_axis_tvalid', mr='m_axis_tready', md='m_axis_tdata', ml='m_axis_tlast',
    mid='m_axis_tid', ov='status_overflow', good='status_good_frame',
    first='first_present', cnt='input_count', done='input_complete')
INTERNAL = ('wr_ptr_reg', 'wr_ptr_next', 'wr_ptr_cur_reg', 'wr_ptr_cur_next',
    'rd_ptr_reg', 'rd_ptr_next', 'full', 'full_cur', 'full_wr', 'empty',
    'drop_frame_reg', 'drop_frame_next', 'write', 'read', 'store_output',
    'overflow_next', 'good_frame_next', 'mem_read_data_valid_reg',
    'mem_read_data_valid_next', 'm_axis_tvalid_next')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def verify_manifest(path):
    entries = read(path)
    assert all(sha(ROOT / k) == v for k, v in entries.items()), str(path)
    return len(entries)


def native_traces(path):
    return [dict((k, int(v)) for k, v in re.findall(r'(\w+)=(-?\d+)', line))
            for line in path.read_text().splitlines() if line.startswith('TRACE ')]


def decode(value):
    if any(x in value.lower() for x in 'xz'):
        return None
    return int(value, 2)


def vcd_edges(path):
    """Sample settled values BEFORE a rising edge, plus post-NBA dump values."""
    scope, names, values, samples = [], {}, {}, []
    with path.open() as f:
        for line in f:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == '$scope':
                scope.append(parts[2])
            elif parts[0] == '$upscope':
                scope.pop()
            elif parts[0] == '$var':
                names['.'.join(scope + [parts[4]])] = parts[3]
            elif parts[0] == '$enddefinitions':
                break
        mapping = {key: names['TOP.tb.' + signal] for key, signal in PORTS.items()}
        mapping.update({key: names['TOP.tb.dut.' + key] for key in INTERNAL})
        clk = names['TOP.tb.clk']
        wanted = set(mapping.values()) | {clk}
        timestamp, before = None, {}

        def finish():
            if timestamp is not None and before.get(clk) == 0 and values.get(clk) == 1:
                pre = {key: before.get(code) for key, code in mapping.items()}
                post = {key: values.get(code) for key, code in mapping.items()}
                if pre['cycle'] is not None and pre['cycle'] < 2**31:
                    samples.append(dict(time_ps=timestamp, pre=pre, post=post))

        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith('#'):
                finish()
                timestamp = int(line[1:])
                before = values.copy()
            elif line[0] in 'bB':
                bits, code = line[1:].split()
                if code in wanted:
                    values[code] = decode(bits)
            elif line[0] in '01xXzZ':
                code = line[1:]
                if code in wanted:
                    values[code] = decode(line[0])
        finish()
    return samples


def check_cycle(sample, trace, depth, revision):
    """Original RTL transition audit; not a new functional correctness oracle."""
    a, z = sample['pre'], sample['post']
    assert all(a[k] is not None for k in a), 'unknown internal/port sample'
    assert {k: a[k] for k in PORTS} == trace, 'pre-edge TRACE alignment'
    mask = 2 * depth - 1
    wp, cur, rp = (a[k] for k in ('wr_ptr_reg', 'wr_ptr_cur_reg', 'rd_ptr_reg'))
    occupied = (cur - rp) & mask
    committed = (wp - rp) & mask
    partial = (cur - wp) & mask
    assert 0 <= committed <= occupied <= depth, 'pointer occupancy'
    assert a['full'] == int(committed == depth)
    assert a['full_cur'] == int(occupied == depth)
    assert a['full_wr'] == int(partial == depth)
    assert a['empty'] == int(wp == rp)
    assert a['sr'] == 1, 'DROP_WHEN_FULL means valid requests are accepted'
    accept = bool(a['sv'] and a['sr'])
    dropping = bool(a['full_cur'] or a['full_wr'] or a['drop_frame_reg'])
    expected_drop = 0 if revision == 'before' else a['drop_frame_reg']
    expected_wp, expected_cur, write, overflow, good = wp, cur, 0, 0, 0
    if accept:
        if dropping:
            expected_drop = 1
            if a['sl']:
                expected_cur, expected_drop, overflow = wp, 0, 1
        else:
            write = 1
            expected_cur = (cur + 1) & mask
            if a['sl']:
                expected_wp, good = expected_cur, 1
    expected = dict(write=write, drop_frame_next=expected_drop,
        wr_ptr_next=expected_wp, wr_ptr_cur_next=expected_cur,
        overflow_next=overflow, good_frame_next=good)
    for key, val in expected.items():
        assert a[key] == val, f'combinational {key}'
    store = int(a['mr'] or not a['mv'])
    take = int((store or not a['mem_read_data_valid_reg']) and not a['empty'])
    assert a['store_output'] == store and a['read'] == take
    assert a['rd_ptr_next'] == ((rp + take) & mask)
    for reg, nxt in [('wr_ptr_reg', 'wr_ptr_next'), ('wr_ptr_cur_reg', 'wr_ptr_cur_next'),
                     ('rd_ptr_reg', 'rd_ptr_next'), ('drop_frame_reg', 'drop_frame_next'),
                     ('ov', 'overflow_next'), ('good', 'good_frame_next'),
                     ('mv', 'm_axis_tvalid_next'), ('mem_read_data_valid_reg', 'mem_read_data_valid_next')]:
        assert z[reg] == (0 if a['rst'] else a[nxt]), f'post-edge register {reg}'
    return dict(memory_occupied=occupied, committed_memory=committed,
        tentative_frame_words=partial,
        output_pipeline_words=a['mem_read_data_valid_reg'] + a['mv'],
        accepted=bool(not a['rst'] and accept),
        output_handshake=bool(not a['rst'] and a['mv'] and a['mr']))


def summarize_job(samples, depth):
    rows = [s['pre'] for s in samples]
    target = [s for s in samples if s['pre']['sid'] == 2 and s['derived']['accepted']]
    assert target and target[-1]['pre']['sl'] == 1
    assert all(not s['pre']['sl'] for s in target[:-1])
    breaks = [i for i in range(1, len(target)) if target[i]['pre']['cycle'] > target[i-1]['pre']['cycle'] + 1]
    assert len(breaks) == 1
    split = breaks[0]
    gap = [s for s in samples if target[split-1]['pre']['cycle'] < s['pre']['cycle'] < target[split]['pre']['cycle']]
    assert gap and all(not s['derived']['accepted'] and not s['pre']['rst'] for s in gap)
    reset_cancel = [r['cycle'] for r in rows if target[0]['pre']['cycle'] <= r['cycle'] <= target[-1]['pre']['cycle'] and r['rst']]
    presented = [s for s in samples if not s['pre']['rst'] and s['pre']['mv'] and s['pre']['mid'] == 2]
    transfers = [s for s in presented if s['derived']['output_handshake']]
    legal = {}
    for fid in (1, 3):
        inp = [r for r in rows if not r['rst'] and r['sv'] and r['sr'] and r['sid'] == fid]
        out = [r for r in rows if not r['rst'] and r['mv'] and r['mr'] and r['mid'] == fid]
        assert [(r['sd'], r['sl']) for r in inp] == [(r['md'], r['ml']) for r in out], 'legal frame order/data'
        legal[str(fid)] = dict(accepted_cycles=[r['cycle'] for r in inp], output_cycles=[r['cycle'] for r in out])
    drops = [s for s in target if not s['pre']['write']]
    writes = [s for s in target if s['pre']['write']]
    if transfers:
        assert [(s['pre']['sd'], s['pre']['sl']) for s in writes] == [(s['pre']['md'], s['pre']['ml']) for s in transfers], 'leaked stored beats'
    resume = target[split]
    tail = target[-1]
    clears = [s for s in gap if s['pre']['drop_frame_reg'] and not s['post']['drop_frame_reg']]
    second_drop = [s for s in target[split:] if not s['pre']['write']]
    final = samples[-1]
    drained = all(final['pre'][k] == 0 for k in ('mv', 'mem_read_data_valid_reg')) and final['derived']['memory_occupied'] == 0
    assert drained and not reset_cancel, 'no truncation/reset explanation'
    return dict(accepted_beats=len(target), accepted_cycles=[s['pre']['cycle'] for s in target],
        accepted_values=[s['pre']['sd'] for s in target], initial_drop_cycle=drops[0]['pre']['cycle'] if drops else None,
        gap_cycles=[s['pre']['cycle'] for s in gap], gap_start=gap[0]['pre']['cycle'],
        gap_drop_clear_cycles=[s['pre']['cycle'] for s in clears],
        written_before_gap=sum(s['pre']['write'] for s in target[:split]),
        resume_cycle=resume['pre']['cycle'], resume_drop=resume['pre']['drop_frame_reg'],
        resume_memory_occupied=resume['derived']['memory_occupied'], resume_tentative_words=resume['derived']['tentative_frame_words'],
        resume_committed_memory=resume['derived']['committed_memory'],
        resume_output_pipeline_words=resume['derived']['output_pipeline_words'],
        remaining_accepted_beats=len(target)-split,
        hypothetical_words_if_remaining_written=resume['derived']['tentative_frame_words']+len(target)-split,
        next_full_drop_cycle=second_drop[0]['pre']['cycle'] if second_drop else None,
        next_full_drop_flags={k:second_drop[0]['pre'][k] for k in ('full_cur','full_wr','drop_frame_reg')} if second_drop else None,
        tail_cycle=tail['pre']['cycle'], tail_write=tail['pre']['write'],
        tail_drop_before=tail['pre']['drop_frame_reg'], tail_overflow_next=tail['pre']['overflow_next'],
        tail_good_next=tail['pre']['good_frame_next'],
        tail_cur_before=tail['pre']['wr_ptr_cur_reg'], tail_cur_after=tail['post']['wr_ptr_cur_reg'],
        tail_committed_before=tail['pre']['wr_ptr_reg'], tail_committed_after=tail['post']['wr_ptr_reg'],
        output_present_cycles=[s['pre']['cycle'] for s in presented],
        output_handshake_cycles=[s['pre']['cycle'] for s in transfers],
        output_beats=len(transfers), legal_frames=legal, reset_cancel_cycles=reset_cancel,
        final_cycle=final['pre']['cycle'], final_drained=drained)


def execute(out):
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    checks = []
    def ck(name, value):
        checks.append(dict(name=name, passed=bool(value)))
        dump(out/'checks.json', checks)
        assert value, name
    # Audit-only sandbox: no network, subprocesses, or writes to earlier runs.
    def guard(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
            raise RuntimeError('audit_only_no_network_or_execution')
        if event == 'open' and isinstance(args[0], (str, bytes)):
            path = Path(args[0]).resolve()
            if isinstance(args[1], str) and any(c in args[1] for c in 'wax+') and not path.is_relative_to(out):
                raise RuntimeError('write_outside_new_audit')
    sys.addaudithook(guard)
    old_count = verify_manifest(RUN/'result_seal.json')
    ck('research190 original seal valid', old_count > 0)
    verify_manifest(RUN/'selection/seal.json')
    bindings = {rel(Path(__file__)): sha(Path(__file__)), rel(RUN/'result_seal.json'):sha(RUN/'result_seal.json')}
    for rev in ('before', 'after'):
        file = RTL/rev/'axis_fifo.v'
        bindings[rel(file)] = sha(file)
    before_rtl = (RTL/'before/axis_fifo.v').read_text()
    after_rtl = (RTL/'after/axis_fifo.v').read_text()
    ck('original fix is drop-state default persistence', before_rtl.replace("    drop_frame_next = 1'b0;", '    drop_frame_next = drop_frame_reg;', 1) == after_rtl)
    old_results = read(RUN/'scene_results.json')
    specs = read(RUN/'selection/scenes.json')
    ck('fixed population all32 not just failures', len(specs)==len(old_results)==32)
    dump(out/'audit_protocol.json', dict(kind='retrospective_local_trace_diagnosis',
        inputs='All64 archived native VCD/log pairs and exact original source; no new stimuli or oracle acceptance changes.',
        sample_rule='Pre-rising-edge VCD must match every original TRACE field; post-NBA values used only for state transitions.',
        controls='All20 already exposed scenes included; no counterfactual generated scenes.',
        limits='Selected batch, single root fix, exact parameters and schedules only; no global non-exposure proof.',
        isolation='Original independent records unchanged. No generator/candidate/rule tuning in this audit. Using these derived conditions for later tuning requires promoting the entire research190 batch to development.',
        model_calls=0, new_native_calls=0))
    scene_summaries, jobs, total_samples = [], [], 0
    for spec, old in zip(specs, old_results):
        sid, depth = spec['scene_id'], spec['descriptor']['depth']
        ck(sid+' scene identity', sid == old['scene_id'])
        pair = {}
        for revision in ('before', 'after'):
            folder = RUN/'native'/sid/revision
            wave, log = folder/'wave.vcd', folder/'execute.log'
            for file in (wave, log, folder/'tb.sv', folder/'result.json'):
                bindings[rel(file)] = sha(file)
            traces = native_traces(log)
            samples = vcd_edges(wave)
            ck(sid+'/'+revision+' sample count and completion', len(samples)==len(traces)>0 and 'NATIVE_RUN_COMPLETE' in log.read_text())
            for sample, trace in zip(samples, traces):
                sample['derived'] = check_cycle(sample, trace, depth, revision)
            total_samples += len(samples)
            ck(sid+'/'+revision+' all port and internal transitions checked', True)
            # Negative control catches accidental post-edge sampling/one-cycle shift.
            changed = next((x for x in samples if any(x['pre'][k] != x['post'][k] for k in PORTS)), None)
            ck(sid+'/'+revision+' pre/post are distinguishable', changed is not None)
            if changed:
                rejected=False
                try:
                    check_cycle(dict(pre=changed['post'], post=changed['post']), {k:changed['pre'][k] for k in PORTS}, depth, revision)
                except AssertionError:
                    rejected=True
                ck(sid+'/'+revision+' wrong post-edge sample rejected', rejected)
            result = summarize_job(samples, depth)
            ck(sid+'/'+revision+' actual length matches descriptor', result['accepted_beats']==depth+spec['descriptor']['excess'])
            if revision=='before':
                clear = next(x for x in samples if x['pre']['cycle'] in result['gap_drop_clear_cycles'])
                rejected=False
                try:
                    check_cycle(clear, {k:clear['pre'][k] for k in PORTS}, depth, 'after')
                except AssertionError:
                    rejected=True
                ck(sid+' wrong RTL revision equation rejected', rejected)
            target_file = out/'cycles'/sid/(revision+'.jsonl')
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with target_file.open('w') as f:
                for sample in samples:
                    f.write(json.dumps(sample, separators=(',', ':'))+'\n')
            pair[revision]=result
            jobs.append(dict(scene_id=sid, revision=revision, samples=len(samples), vcd=rel(wave), log=rel(log), result=result))
        a,z=pair['before'],pair['after']
        ck(sid+' identical accepted transactions', a['accepted_cycles']==z['accepted_cycles'] and a['accepted_values']==z['accepted_values'])
        ck(sid+' fix retains drop across gap', len(a['gap_drop_clear_cycles'])==1 and not z['gap_drop_clear_cycles'] and a['resume_drop']==0 and z['resume_drop']==1)
        ck(sid+' fixed drops at accepted tail', z['tail_overflow_next']==1 and z['tail_good_next']==0 and z['output_beats']==0)
        # The20-cycle drain gap exhausts the15-beat prefix at Depth16, but
        # not the31-beat prefix at Depth32. Keep the latter concurrent reads.
        if depth == 16:
            ck(sid+' depth16 prefix RAM drained at resume', a['resume_committed_memory']==0)
        else:
            ck(sid+' depth32 prefix still draining at resume', a['resume_committed_memory']==9 and a['resume_output_pipeline_words']==2)
        ck(sid+' three tentative target words remain at resume', a['resume_tentative_words']==3)
        exceeds=a['hypothetical_words_if_remaining_written']>depth
        if exceeds:
            classification='drop_state_loss_masked_by_second_capacity_overflow'
            valid=(a['next_full_drop_flags'] is not None and a['next_full_drop_flags']['full_cur']==1 and a['next_full_drop_flags']['full_wr']==1
                and a['next_full_drop_flags']['drop_frame_reg']==0 and a['tail_overflow_next']==1 and a['tail_good_next']==0
                and a['tail_cur_after']==a['tail_committed_before']==a['tail_committed_after']
                and not a['output_present_cycles'] and not a['output_handshake_cycles'])
        else:
            classification='drop_state_loss_followed_by_tail_commit_and_leak'
            valid=(a['next_full_drop_cycle'] is None and a['tail_write']==1 and a['tail_good_next']==1 and a['tail_overflow_next']==0
                and a['output_beats']==a['hypothetical_words_if_remaining_written']>0)
        ck(sid+' causal classification grounded in transitions', valid)
        ck(sid+' original exposure outcome unchanged', bool(a['output_beats'])==bool(old['exposed_targets']) and exceeds==bool(old['missing_exposure_ids']))
        scene_summaries.append(dict(scene_id=sid, descriptor=spec['descriptor'], classification=classification,
            old_passed=old['passed'], old_exposed=old['exposed_targets'], before=a, after=z))
    dump(out/'native_audit.json', jobs)
    dump(out/'scene_causes.json', scene_summaries)
    missing=[x for x in scene_summaries if not x['old_exposed']]
    ck('all12 unexposed explained at depth16', len(missing)==12 and all(x['descriptor']['depth']==16 for x in missing))
    ck('all20 exposed included as observed controls', sum(x['old_exposed'] for x in scene_summaries)==20)
    ck('old results seal unchanged after diagnosis', verify_manifest(RUN/'result_seal.json')==old_count)
    ck('all native/source bindings unchanged', all(sha(ROOT/k)==v for k,v in bindings.items()))
    dump(out/'source_bindings.json', bindings)
    summary=dict(status='local_diagnosis_complete', audited_scenes=32, audited_native_pairs=64,
        audited_rising_edge_samples=total_samples, explained_unexposed=12, observed_exposed_controls=20,
        cause='Buggy drop latch clears in gap in all32. In12 depth16 traces, resumed tentative writes reach depth again before completing TLAST; capacity/within-frame overflow re-enters dropping, rolls back at TLAST, and hides the externally observable leak. Fixed RTL keeps the original drop state throughout.',
        unchanged_old_scope_pass=False, unchanged_old_scene_pass='20/32', unchanged_sva=True,
        new_model_versions=0, new_independent_runs=0, model_calls=0, native_compile_calls=0, native_execution_calls=0,
        conditional_recovery=dict(numerator=0,denominator=0,estimate=None), H_R_equivalent=True,
        mechanism_increment_claim=False, tasks2_3_expanded=False,
        data_use='Read-only retrospective interpretation; not used to change candidates, generators, or acceptance rules. Future tuning from this diagnosis requires promotion of the entire old batch.',
        next_step='If supplementary validation is desired, first promote research190 to development in a new protocol; verify actual exposure conditions on development material, freeze unchanged SVA and sampling rules, then draw new unseen semantic scenarios. Do not replace failed old scenarios or treat this diagnosis as new acceptance.')
    dump(out/'summary.json', summary)
    dump(out/'cost.json', dict(model_calls=0,tokens=0,compile_calls=0,simulation_calls=0,formal_calls=0,
        archived_native_jobs_read=64, vcd_samples_checked=total_samples, local_wall_seconds=time.monotonic()-started))
    lines=['# research191：research190未曝光场景的本地因果审计','',
        '**12个未曝光场景均已用原生波形解释；research190仍为20/32，未修改断言、规则或原结果。**','',
        '旧版并非没有触发内部缺陷：全部32个场景中，输入间隔均使drop_frame_reg从1错误清为0；修复版持续保持1。差异在于间隔之后能否提交帧尾。', '',
        '12个Depth16场景中，恢复输入时已有3拍暂存；余下接受拍数使暂存总量再次超过16。原生波形显示full_cur与full_wr重新置位，旧版再次进入丢帧，TLAST时回滚临时写指针而不提交。旧版和修复版因此均无目标输出。不是复位取消、请求未接受、仿真截断或SVA漏报。', '',
        '其余20个已曝光场景作为同批观察对照：临时累计写入未再次溢出，旧版在TLAST错误提交并泄漏；修复版仍丢弃。Depth32恢复输入时RAM内尚有9个前帧字，两个输出寄存器也有前帧字，继续并行排出；逐周期指针检查包含这些读出，未假设前帧已排空。这里只是该批具体轨迹的因果解释，不证明Depth16永远无法复现。Depth16同批已有4个成功曝光。', '',
        '|未曝光场景|帧长|间隔前已接受拍数|间隔/清除周期|恢复周期|恢复后剩余拍数|再次满而丢弃周期|TLAST回滚周期|目标输出|',
        '|---|---:|---:|---|---:|---:|---:|---:|---:|']
    for x in missing:
        a=x['before'];d=x['descriptor']
        lines.append(f"|{x['scene_id']}|{a['accepted_beats']}|{d['semantic_key'][3]}|{a['gap_start']}/{a['gap_drop_clear_cycles'][0]}|{a['resume_cycle']}|{a['remaining_accepted_beats']}|{a['next_full_drop_cycle']}|{a['tail_cycle']}|{a['output_beats']}|")
    lines += ['', '占用口径：memory_occupied是临时写指针减读指针；committed_memory是已提交写指针减读指针；tentative_frame_words是当前未提交帧占用。另列输出两级寄存器占用，不能用累计输入减输出直接替代RAM占用。', '',
        f'复核64份VCD及64份TRACE日志、{total_samples}个上升沿，所有端口字段逐项匹配前沿采样；另核验原始RTL的指针/丢帧/写入方程与NBA后寄存器。错误后沿采样、错误RTL版本方程的负检查均拒绝。{len(checks)}项审计检查通过。', '',
        '本轮没有生成新刺激、没有模型/仿真调用、没有新增接受或独立通过版本。32个原场景、SVA及原验收结果的封存哈希均未改变。分类是回顾性诊断，不能算机制增量或独立新发现。', '',
        '首个诊断运行r01因“所有深度的前帧均已在间隔中排空”的过强假设停止，失败快照和检查保留。r02修正的是本地诊断假设，未改变原生结果、SVA、参考判定或接受条件。', '',
        '**下一步边界：**若利用本诊断调整场景生成，必须先在新协议中把research190整批转为开发数据；本轮只读解释，尚未调整生成器或申请模型。可在开发材料中核验实际曝光必要条件，再保持SVA不变，封存新语义空间、固定数量/预算和不补抽规则，另做补充独立验收。不能只保留这20个成功场景，更不能追改为32/32。', '',
        '固定三任务：任务1仍缺前瞻性的额外拒绝→恢复→独立通过；条件恢复0/0不可估计，H/R等价。任务2/3本轮不扩展，既有576次查询负结果保持。', '',
        '复核命令（新目录；无模型、无仿真）：','```powershell',
        'wsl -- python3 scripts/research191_fifo_exposure_audit.py --out deliverables/research191_reaudit','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    dump(out/'seal.json', {rel(f):sha(f) for f in out.rglob('*') if f.is_file()})
    print(json.dumps(summary, ensure_ascii=False))
    print('CHECKS', len(checks), 'passed')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args=parser.parse_args()
    execute((ROOT/args.out).resolve())
