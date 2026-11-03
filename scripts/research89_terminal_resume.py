"""Resume only the interrupted frozen test audit; no model calls or new tests."""
import argparse
import shutil
from pathlib import Path
from unittest.mock import patch
import research87_cross_parent_recovery as x


def run(prep, trial):
    x.verify(prep)
    assert not (trial/'resume.json').exists(), 'already resumed'
    preserved = {n:x.sha(trial/n) for n in ('freeze.json','generation.json',
        'independent_cases.json','exception.json','outcome.json','cost.json')}
    freeze=x.read(trial/'freeze.json'); generation=x.read(trial/'generation.json')
    txns=x.read(trial/'independent_cases.json')
    assert generation['at'] > freeze['time']
    assert generation['freeze_sha256']==preserved['freeze.json']
    excluded=x.read(prep/'excluded_words.json')
    assert txns==x.holdout.base.generate(generation['seed'],excluded)
    assert len({t['instruction'] for t in txns})==96
    assert not set(excluded)&{t['instruction'] for t in txns}
    expected=dict(A=x.read(prep/'proposal.json'),B=x.read(trial/'B/v1/transition/active.json'))
    results={}; reused={}
    for arm in ('A','B'):
        folder=trial/'frozen'/arm; candidate=x.read(folder/'candidate.json')
        assert candidate==expected[arm]
        assert x.old.acceptance.sha(candidate)==freeze['versions'][arm]
        casepath=folder/'independent_cases.json'
        if casepath.exists():assert x.read(casepath)==txns
        else:shutil.copy2(trial/'independent_cases.json',casepath)
        for rev in ('before','after'):
            if not (folder/rev).exists():shutil.copytree(prep/rev,folder/rev)
            for source in (prep/rev).glob('*.sv'):
                assert x.sha(source)==x.sha(folder/rev/source.name)
        resultpath=folder/'independent/result.json'
        reused[arm]=resultpath.exists()
        if reused[arm]:result=x.read(resultpath)
        else:result=x.old.replay(candidate,txns,'independent',folder/'independent',folder,configs=x.holdout.base.CONFIGS)
        version=x.read(folder/'independent/before/result.json')['tool_version']
        toolpath=folder/'tool_config.json'
        if toolpath.exists():assert x.read(toolpath)['version']==version
        else:x.dump(toolpath,dict(version=version))
        assert result['healthy'], 'native execution failed; no retry'
        audit=x.holdout.base.native_audit(folder,result)
        with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):
            guard=x.all_guard(folder/'independent',result,candidate)
        summary=x.holdout.summarize(result,guard)
        x.dump(folder/'audit.json',audit);x.dump(folder/'summary.json',summary)
        results[arm]=summary
        print('RESUME89',arm,summary['passed'],summary['counts'],flush=True)
    for n,h in preserved.items():assert x.sha(trial/n)==h,n
    x.verify(prep)
    x.dump(trial/'independent_summary.json',results)
    x.dump(trial/'resumed_cost.json',x.costs.native_cost(trial))
    x.dump(trial/'resume.json',dict(preserved=preserved,reused_native=reused,
        new_model_calls=0,new_test_generation=False,new_native_revisions=2*sum(not v for v in reused.values()),
        reason='Bind the already frozen shared test list at each native auditor input path; reuse completed A replay.',
        script_sha256=x.sha(Path(__file__))))
    original=x.read(trial/'outcome.json')
    x.dump(trial/'terminal_outcome.json',dict(original_outcome_sha256=preserved['outcome.json'],
        new_calls=original['new_calls'],accepted_B=original['accepted_B'],independent_executed=True,
        independent_passed={a:s['passed'] for a,s in results.items()},
        same_budget_recovery_success=bool(original['accepted_B'] and results['B']['passed'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve())
