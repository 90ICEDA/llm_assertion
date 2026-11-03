"""Opt-in artificial stall-data fault on actual axis_fifo, with native audit.

This is deliberate fault-model coverage, not discovery of a historical defect.
Importing this module changes nothing. Use installed() or paired install/uninstall
in a single experiment process. No persisted modification of existing modules.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
from pathlib import Path
import shutil

import research15_search_runtime as runtime
import research17_fifo_feedback as sampled
import research17_loop as loop
from research15_evidence import INPUTS
from research15_search_experiment import stimulus
from research17_model import ROOT, dump, read

MODE='stall_glitch'
FAULT_INDEX=5
_original_template=runtime.testbench_template
_original_modes=runtime.MODES
_active=False


def template(depth=2,pipeline=0):
    """Preserve driver, reset, handshakes, RTL and all previous fault modes."""
    source=_original_template(depth,pipeline)
    anchor='  assign mdata = '
    if source.count(anchor)!=1:
        raise RuntimeError('expected exactly one known output data assignment')
    injected=("  // RESEARCH20 ARTIFICIAL STALL FAULT: no upstream-defect claim.\n"
              "  // Alternate output bit zero only while valid is backpressured.\n"
              "  // Input driver, output valid and actual FIFO RTL stay identical.\n"
              "  assign mdata = (fault_mode==5 && raw_valid && !mready) ?\n"
              "    (raw_data ^ (native_cycle & 1)) : ")
    return source.replace(anchor,injected)


def install():
    global _active
    if _active:
        if runtime.testbench_template is not template or runtime.MODES!=_original_modes+(MODE,):
            raise RuntimeError('installed runtime changed by another owner')
        return False
    if runtime.testbench_template is not _original_template or runtime.MODES!=_original_modes:
        raise RuntimeError('refusing to overwrite another runtime extension')
    if len(_original_modes)!=FAULT_INDEX:
        raise RuntimeError('original fault indices changed')
    runtime.testbench_template=template
    runtime.MODES=_original_modes+(MODE,)
    _active=True
    return True


def uninstall():
    global _active
    if not _active:return False
    if runtime.testbench_template is not template or runtime.MODES!=_original_modes+(MODE,):
        raise RuntimeError('refusing to overwrite runtime modified after installation')
    runtime.testbench_template=_original_template
    runtime.MODES=_original_modes
    _active=False
    return True


@contextmanager
def installed():
    changed=install()
    try:yield
    finally:
        if changed:uninstall()


def extra_cases():
    result=[]
    for depth,pipeline,seed in ((2,0,2026101841),(5,1,2026101941)):
        result.append(dict(id=f'dev20:d{depth}:p{pipeline}:s{seed}:backpressure:{MODE}',
            depth=depth,pipeline=pipeline,mode=MODE,rows=stimulus(seed,'backpressure'),
            seed=seed,family='backpressure',source='prospective_artificial_stall_fault',
            split='development',target_obligation='stall_stability'))
    return result


def build(candidate,folder,depth=2,pipeline=0):
    if not _active:raise RuntimeError('explicit install required')
    return sampled.build(candidate,folder,depth,pipeline)


def execute(compiled,folder,rows,mode):
    if not _active:raise RuntimeError('explicit install required')
    return sampled.execute(compiled,folder,rows,mode)


def _hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(out,candidate_path):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    candidate_path=Path(candidate_path).resolve()
    candidate=read(candidate_path);cases=extra_cases()
    dump(out/'cases.json',cases)
    dump(out/'protocol.json',dict(candidate_source=str(candidate_path),candidate_sha256=_hash(candidate_path),
        source='Existing genuine model initial candidate; not newly generated.',
        artificial_fault=MODE,fault_index=FAULT_INDEX,
        mutation='XOR output data bit zero with sampled cycle parity only while raw_valid and !mready.',
        changed_semantics='Faulty output data stability only; protocol requirement is unchanged.',
        unchanged=['Actual axis_fifo RTL','input driver','valid/ready acceptance','synchronous reset','existing modes 0..4','independent oracle'],
        purpose='Deliberate artificial fault coverage and valid missed-evidence qualification. Not an upstream historical defect discovery.',
        data_split='Development only. No new independent test results are read.'))
    snap=out/'source_snapshot';snap.mkdir()
    for path in (Path(__file__),Path(runtime.__file__),Path(sampled.__file__),Path(loop.__file__),
                 ROOT/'scripts/research15_native_interface.py',ROOT/'scripts/research15_evidence.py',runtime.RTL):
        shutil.copy2(path,snap/path.name)
    dump(snap/'hashes.json',{p.name:_hash(p) for p in snap.iterdir()})
    for case in cases:
        d,p=case['depth'],case['pipeline']
        before=_original_template(d,p);after=template(d,p)
        (out/f'original_d{d}_p{p}.sv').write_text(before)
        (out/f'stall_fault_d{d}_p{p}.sv').write_text(after)
    native_result=None
    try:
        with installed():native_result=loop.replay(candidate,out/'native',cases)
    finally:
        dump(out/'restoration.json',dict(restored=runtime.testbench_template is _original_template and runtime.MODES==_original_modes,
                                        active=_active,modes=runtime.MODES))
    details=[]
    if native_result and native_result.get('group'):
        for index,case in enumerate(cases):
            folder=out/'native'/f'case_{index}'
            fixed=read(folder/'correct/replay.json');buggy=read(folder/MODE/'replay.json')
            group=read(folder/'ledger.json')
            first=[row for row in group['ledger'] if row['oracle']['verdict']=='violated' and row['obligation']=='stall_stability']
            targets=[]
            same_input=([{k:t[k] for k in INPUTS} for t in fixed['trace']]==
                        [{k:t[k] for k in INPUTS} for t in buggy['trace']])
            for row in first:
                cycle=row['cycle']
                # A stalled output is presented but not yet accepted. Associate
                # the oldest already accepted, not reset-cancelled input using
                # the independent correct-transaction history, never intent.
                pending=[t for t in fixed['oracle']['transactions'] if t['accept_cycle']<cycle
                    and (t['response_cycle'] is None or t['response_cycle']>=cycle)
                    and (t['cancel_cycle'] is None or t['cancel_cycle']>cycle)]
                oldest=min(pending,key=lambda t:t['accept_cycle']) if pending else None
                controls=[c for c in fixed['oracle']['checks'] if c['cycle']==cycle and c['obligation']=='stall_stability']
                checks=dict(same_accepted_input_schedule=same_input,
                    legal_input=fixed['oracle']['legality']==buggy['oracle']['legality']=='legal',
                    independent_fixed_pass=bool(controls) and all(c['passed'] for c in controls),
                    independent_buggy_violation=row['oracle']['verdict']=='violated',
                    accepted_transaction_identified=oldest is not None,
                    current_sva_did_not_report=not any(e['cycle']<=cycle for e in buggy['native'].get('failures',[]) if 'cycle' in e),
                    evidence_admission_confirmed=row['native']['attribution_status']=='confirmed',
                    sampling_pass=fixed['sampling_qualification']['status']==buggy['sampling_qualification']['status']=='passed')
                # Failure markers normally carry cycle in detail, not a field.
                from research15_evidence import marker_map
                failure_cycles=set().union(*marker_map(buggy['native'],'failures').values()) if buggy['native']['failures'] else set()
                checks['current_sva_did_not_report']=not any(c<=cycle for c in failure_cycles)
                targets.append(dict(evidence_id=row['evidence_id'],cycle=cycle,checks=checks,valid=all(checks.values()),
                    associated_accepted_transaction=oldest,
                    fixed_samples=[t for t in fixed['reference_trace'] if cycle-1<=t['cycle']<=cycle],
                    buggy_samples=[t for t in buggy['reference_trace'] if cycle-1<=t['cycle']<=cycle],
                    candidate_gap='no_property_mapped' if not row['native']['assertions'] else 'no_effective_trigger' if not any(a['trigger'] for a in row['native']['assertions']) else 'triggered_but_no_detection',
                    oracle_violation=row['oracle_violation']))
            details.append(dict(case=case['id'],targets=targets,
                fixed_legality=fixed['oracle']['legality'],fixed_violations=fixed['oracle']['violations'],
                buggy_violations=buggy['oracle']['violations'],
                native_failures=buggy['native']['failures'],later_attribution_unknown=len(group['exclusions'])))
    commands=[read(p) for p in out.rglob('compile.json')]
    executions=[read(p) for p in out.rglob('execute.json')]
    targets=[t for d in details for t in d['targets']]
    result=dict(passed=bool(native_result and native_result['healthy'] and len(details)==2 and all(d['targets'] for d in details) and all(t['valid'] for t in targets)),
        counts=native_result.get('counts') if native_result else None,cases=details,
        valid_target_count=sum(t['valid'] for t in targets),independent_fault_mechanism_classes=1 if targets else 0,
        cost=dict(native_compiles=len(commands),native_executions=len(executions),
            compile_wall_seconds=sum(c.get('wall_seconds',0) for c in commands),execute_wall_seconds=sum(c.get('wall_seconds',0) for c in executions),model_calls=0,formal_queries=0),
        limitation='Intentional fault-model extension on real RTL. No original historical bug credit, no new model generation/refinement success and no formal proof.',
        template_hashes={p.name:_hash(p) for p in out.glob('*.sv')})
    dump(out/'summary.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,default=ROOT/'deliverables/research19_closed_loop_20261016_r03/shared_initial.json')
    args=parser.parse_args();result=audit(args.out,args.candidate)
    print({k:result[k] for k in ('passed','counts','valid_target_count','cost')},flush=True)
    if not result['passed']:raise SystemExit(1)


if __name__=='__main__':main()
