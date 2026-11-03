"""Pilot entry with interruption-safe final milestone accounting.

Preserves the sealed runner and its raw results. Reservations are not completion.
"""
import argparse
from pathlib import Path
import research80_presentation_pilot as pilot


def finalize(prep,out):
    path=out/'outcome.json'
    if not path.exists():return
    outcome=pilot.read(path)
    pilot.dump(out/'runner_outcome.json',outcome)
    state=pilot.read(out/'budget.json');initial=pilot.read(prep/'initial.json')
    # Freeze remaining baselines after a global exception; never resume calls.
    for arm in pilot.ARMS:
        folder=out/'arms'/arm
        if not (folder/'core/frozen_candidate.json').exists():
            pilot.b.loop.freeze(folder/'core',initial,'not_run_after_global_exception')
        if not (folder/'outcome.json').exists():
            pilot.dump(folder/'outcome.json',dict(status='not_run_global_exception',accepted=False,
                plan_passed=False,frozen_hash=pilot.b.loop.sha(initial),independent_performed=False))
    phases=[]
    for arm in pilot.ARMS:
        result=out/'arms'/arm/'core/v0/history/result.json'
        if result.exists():phases.append(dict(arm=arm,path=result.relative_to(out).as_posix(),sha256=pilot.b.search.digest(result)))
    outcome['history_replay_reservations']=sum('history' in s['phases'] for s in state['arms'].values())
    outcome['full_history_replays']=len(phases)
    outcome['completed_history_results']=phases
    outcome['distinct_new_accepted_hashes']=len({pilot.read(out/'arms'/a/'outcome.json')['frozen_hash']
        for a in pilot.ARMS if pilot.read(out/'arms'/a/'outcome.json')['accepted']})
    outcome['distinct_independent_pass_hashes']=len({v['candidate_hash'] for v in outcome['independent'].values() if v['qualified']})
    outcome['accounting']='Finished result artifacts, not budget reservations. Arm counts and distinct candidate hashes both retained.'
    pilot.dump(path,outcome)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','run']);p.add_argument('--prepared',type=Path)
    p.add_argument('--authorization',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.action=='prepare':pilot.prepare(a.out.resolve())
    else:
        prep,out=a.prepared.resolve(),a.out.resolve()
        # Do not finalize an existing run on a failed accidental re-invocation.
        if out.exists():raise FileExistsError(out)
        try:pilot.run(prep,out,a.authorization.resolve())
        finally:finalize(prep,out)
