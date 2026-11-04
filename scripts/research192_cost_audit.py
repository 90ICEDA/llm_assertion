"""Recount actual commands and model submissions, including interrupted work.

Reads command/result files, not budget caps. Shared work is counted once per
physical directory. Runtime/referee time nested in commands is not added twice.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DEFAULTS=[
    ('legacy_search_main','research192_active_20261103_r03'),
    ('legacy_search_superseded','research192_active_20261103_r02'),
    ('native_search','research193_active_native_20261103_r01'),
    ('ablation_acquisition','research192_ablation_prepare_20261103_r01'),
    ('refinement','research192_refinement_20261103_r01'),
    ('ablation','research192_ablation_20261103_r01'),
    ('local_edit_qualification','research192_local_qualification_20261103_r01'),
    ('independent_renderer_qualification','research192_independent_qualification_20261103_r01'),
    ('fault_family_qualification','research192_fault_family_pilot_20261103_r01'),
    ('independent','research192_independent_20261103_r01')]


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def safe_read(path):
    try:return read(path)
    except (OSError,ValueError):return None


def collect(folder):
    for base,dirs,names in os.walk(folder):
        dirs[:]=[d for d in dirs if d not in ('obj_dir','__pycache__','source_snapshot','frozen','run_sources')]
        for name in names:
            if name in ('compile.json','execute.json','simulate.json','cost.json','attempt.json','result.json'):
                yield Path(base)/name


def audit(out):
    rows=[];bindings={}
    for role,name in DEFAULTS:
        folder=ROOT/'deliverables'/name
        if not folder.exists():
            rows.append(dict(role=role,status='not_run',model_calls=0));continue
        files=list(collect(folder))
        commands=[f for f in files if f.name in ('compile.json','execute.json','simulate.json')]
        # Icarus uses each per-variant cost.json; native uses command JSON.
        attempts=[f for f in files if f.name=='attempt.json' and f.parent.name=='model_call']
        calls=[f.parent/'result.json' for f in attempts]
        usage=[safe_read(f) or {} for f in calls]
        command_records=[safe_read(f) for f in commands]
        row=dict(role=role,status='recorded',directory=name,model_calls=len(attempts),
            unknown_usage_calls=sum(v.get('prompt_tokens') is None or v.get('completion_tokens') is None for v in usage),
            prompt_tokens=sum(v['prompt_tokens'] for v in usage) if all(v.get('prompt_tokens') is not None for v in usage) else None,
            completion_tokens=sum(v['completion_tokens'] for v in usage) if all(v.get('completion_tokens') is not None for v in usage) else None,
            native_compile_commands=sum(f.name=='compile.json' for f in commands),
            native_execution_commands=sum(f.name in ('execute.json','simulate.json') for f in commands),
            command_seconds=sum(v.get('wall_seconds',0) for v in command_records) if all(v is not None for v in command_records) else None,
            missing_or_truncated_command_records=sum(v is None for v in command_records),
            monetary_cost=None,formal_calls=0)
        # A disk failure can erase whole command files, not only truncate them.
        # Preserve the saved-command count as a lower bound instead of treating
        # readable surviving records as a complete timing ledger.
        summaries=safe_read(folder/'results.json') or []
        if isinstance(summaries,list) and summaries and isinstance(summaries[0],dict):
            interrupted=sum(bool(r.get('infrastructure_failure')) or 'infrastructure' in r.get('status','') for r in summaries)
            declared=sum(r.get('physical_native_compiles',0) for r in summaries)
            row['infrastructure_interrupted_arms']=interrupted
            row['recorded_arm_compile_attempt_counter']=declared
            row['unrecorded_compile_attempts_min']=max(0,declared-row['native_compile_commands'])
            if interrupted or row['unrecorded_compile_attempts_min']:
                row['command_seconds_lower_bound']=sum(v.get('wall_seconds',0) for v in command_records if v is not None)
                row['command_seconds']=None
                row['command_ledger_complete']=False
        # Legacy runner has separate stdout/stderr logs and counters in query records.
        query_file=folder/'queries.json'
        if not query_file.exists():
            query_files=list(folder.glob('search/*/queries.jsonl'))
            queries=[];partial_records=0
            for path in query_files:
                for line in path.read_text().splitlines():
                    if not line.strip():continue
                    try:queries.append(json.loads(line))
                    except ValueError:partial_records+=1
            row['truncated_query_records']=partial_records
        else:
            value=read(query_file);queries=value if isinstance(value,list) else []
        row['recorded_queries']=len(queries)
        row['diagnostic_query_compiles']=sum(q.get('compile_attempts',0) for q in queries)
        row['diagnostic_query_simulations']=sum(q.get('simulation_attempts',0) for q in queries)
        outcome=folder/'outcome.json'
        if outcome.exists():row['terminal_status']=read(outcome).get('status')
        rows.append(row)
        for path in [*commands,*attempts,*(f for f in calls if f.exists())]:
            bindings[path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    actual_model_calls=sum(r['model_calls'] for r in rows)
    if actual_model_calls>16:raise ValueError('explicit_call_authorization_exceeded')
    out.mkdir(parents=True,exist_ok=True)
    (out/'actual_costs.json').write_text(json.dumps(dict(rows=rows,total_model_calls=actual_model_calls,
        actual_model_call_cap=16,monetary_cost=None,
        timing='Command durations sum concurrent worker effort, not campaign elapsed time; no nested timing added.',
        caveat='Diagnostic counts are from saved completed-query records. Interrupted submissions/partially issued commands are separately retained in superseded-run audit.'),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'cost_source_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf-8')
    print('ACTUAL MODEL SUBMISSIONS',actual_model_calls,'/16',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=ROOT/'deliverables/reguard_mechanisms_20261103_r01')
    audit(parser.parse_args().out.resolve())
