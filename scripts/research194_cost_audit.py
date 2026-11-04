"""Count physical commands once, including qualification and aborted batches."""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def run(out):
    roots=sorted((ROOT/'deliverables').glob('research194_*'))
    commands=[];bindings={};model_ledgers=[];model_results=[];seen_model_folders=set()
    for folder in roots:
        for name,kind in (('compile.json','native_compile'),('execute.json','native_execute')):
            for path in sorted(folder.rglob(name)):
                if not (path.parent/'tb.sv').exists():continue
                row=json.loads(path.read_text())
                commands.append(dict(path=str(path.relative_to(ROOT)),campaign=folder.name,kind=kind,
                    wall_seconds=row.get('wall_seconds'),exit_code=row.get('exit_code'),status=row.get('status'),timed_out=row.get('status')=='timeout'))
                bindings[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
        for path in folder.rglob('global_model_ledger.json'):
            data=json.loads(path.read_text());model_ledgers.append(dict(path=str(path.relative_to(ROOT)),reserved_slots=len(data),records=data))
            bindings[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
            for entry in data:
                model_folder=Path(entry['folder'])
                if model_folder in seen_model_folders:raise ValueError('duplicate_paid_model_folder')
                seen_model_folders.add(model_folder)
                result_path=model_folder/'result.json'
                if not result_path.exists():
                    model_results.append(dict(folder=str(model_folder),status='pending_result',tokens_known=False));continue
                record=json.loads(result_path.read_text())
                known=record.get('prompt_tokens') is not None and record.get('completion_tokens') is not None
                model_results.append(dict(folder=str(model_folder.relative_to(ROOT)),status=record.get('status'),
                    model_calls=record.get('model_calls',0),retries=record.get('retries'),
                    prompt_tokens=record.get('prompt_tokens'),completion_tokens=record.get('completion_tokens'),
                    tokens_known=known,wall_seconds=record.get('wall_seconds'),response_id=record.get('response_id')))
                bindings[str(result_path.relative_to(ROOT))]=hashlib.sha256(result_path.read_bytes()).hexdigest()
    summary=[]
    for campaign in sorted({x['campaign'] for x in commands}):
        rows=[r for r in commands if r['campaign']==campaign]
        summary.append(dict(campaign=campaign,compile_attempts=sum(r['kind']=='native_compile' for r in rows),
            execution_attempts=sum(r['kind']=='native_execute' for r in rows),
            known_native_seconds=sum(r['wall_seconds'] or 0 for r in rows),
            command_duration_unknown=sum(r['wall_seconds'] is None for r in rows)))
    result=dict(snapshot_utc=datetime.now(timezone.utc).isoformat(),summary=summary,commands=commands,model_ledgers=model_ledgers,model_results=model_results,
        total_compile_attempts=sum(x['compile_attempts'] for x in summary),
        total_execution_attempts=sum(x['execution_attempts'] for x in summary),
        known_native_seconds=sum(x['known_native_seconds'] for x in summary),
        reserved_model_slots=sum(x['reserved_slots'] for x in model_ledgers),
        model_calls_with_final_record=sum(x.get('model_calls',0) for x in model_results),
        model_result_status_counts=dict(Counter(x['status'] for x in model_results)),
        known_prompt_tokens=sum(x.get('prompt_tokens') or 0 for x in model_results),
        known_completion_tokens=sum(x.get('completion_tokens') or 0 for x in model_results),
        known_total_tokens=sum((x.get('prompt_tokens') or 0)+(x.get('completion_tokens') or 0) for x in model_results),
        token_unknown_model_results=sum(not x['tokens_known'] for x in model_results),
        actual_retries=sum(x.get('retries') or 0 for x in model_results),
        known_model_wall_seconds=sum(x.get('wall_seconds') or 0 for x in model_results),
        monetary_cost=None,
        limits=['Snapshots include completed command records only; a currently running command has no final duration yet.',
            'Source regrading and label projections are read-only analysis, not additional native executions.',
            'Qualification, aborted batches and duplicate paid inputs remain in physical totals; comparison tables separate them.',
            'A reserved model slot is not necessarily a successful response; individual ledgers preserve status.'])
    out.mkdir(parents=True,exist_ok=True)
    for name,data in (('actual_costs.json',result),('cost_source_bindings.json',bindings)):
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('total_compile_attempts','total_execution_attempts','known_native_seconds','reserved_model_slots')}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'deliverables/reguard_mechanisms_20261103_r02');run(p.parse_args().out)
