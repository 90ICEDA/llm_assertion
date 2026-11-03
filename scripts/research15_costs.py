"""Inventory physical calls from actual command/model records, not estimations."""
import collections
import os
from pathlib import Path
from research15_pipeline import ROOT,OUT,read,dump


def run():
    commands=[];models=[]
    for owner in ('native','search','history','regression'):
        base=ROOT/f'deliverables/research15_{owner}_20261015_r01'
        if not base.exists():continue
        for directory,dirs,files in os.walk(base):
            dirs[:]=[d for d in dirs if d not in ('obj_dir','tools','source_snapshot','execution_source_snapshot','__pycache__')]
            folder=Path(directory)
            for name in ('compile.json','execute.json','simulate.json'):
                if name not in files:continue
                record=read(folder/name)
                commands.append(dict(owner=owner,kind='compile' if name=='compile.json' else 'simulation',
                    record=str((folder/name).relative_to(ROOT)),exit_code=record.get('exit_code'),
                    wall_seconds=record.get('wall_seconds',record.get('elapsed_seconds')),
                    argv=record.get('argv',record.get('command')),status=record.get('status')))
            if 'request.json' in files and 'attempt.json' in files:
                response=read(folder/'result.json') if 'result.json' in files else {}
                request=read(folder/'request.json')
                models.append(dict(owner=owner,directory=str(folder.relative_to(ROOT)),
                    model=request.get('model'),options=request.get('options',{}),
                    status=response.get('status','no_final_result'),
                    prompt_tokens=response.get('prompt_tokens'),completion_tokens=response.get('completion_tokens'),
                    wall_seconds=response.get('wall_seconds'),retries=response.get('retries'),digest=response.get('digest')))
    summaries={}
    for owner in ('native','search','history','regression'):
        records=[r for r in commands if r['owner']==owner]
        summaries[owner]={kind:dict(attempts=sum(r['kind']==kind for r in records),
            nonzero_or_unknown_exit=sum(r['kind']==kind and r['exit_code']!=0 for r in records),
            known_wall_seconds=sum(r['wall_seconds'] or 0 for r in records if r['kind']==kind),
            unavailable_wall_records=sum(r['wall_seconds'] is None for r in records if r['kind']==kind))
            for kind in ('compile','simulation')}
    result=dict(physical_command_records=commands,physical_model_attempts=models,per_owner=summaries,
        model_totals=dict(attempts=len(models),completed=sum(m['status']=='response_received' for m in models),
            known_prompt_tokens=sum(m['prompt_tokens'] or 0 for m in models),
            known_completion_tokens=sum(m['completion_tokens'] or 0 for m in models),
            token_unavailable_attempts=sum(m['prompt_tokens'] is None or m['completion_tokens'] is None for m in models),
            known_wall_seconds=sum(m['wall_seconds'] or 0 for m in models)),
        formal_calls=0,formal_wall_seconds=0,monetary_cost=None,cpu_energy_cost=None,
        accounting='Each actual compile/execute command record counted once. Includes engineering/tool qualification and default smoke simulation during compilation. Main experiment query budgets and cached/shared treatment costs are reported separately. Local model money/energy cost unavailable, not assumed free.')
    dump(OUT/'physical_cost_ledger.json',result)
    print(__import__('json').dumps(dict(commands=len(commands),model_attempts=len(models))))
    return result


if __name__=='__main__':run()
