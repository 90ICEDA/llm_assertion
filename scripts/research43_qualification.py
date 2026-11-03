"""Local negative controls for paired-trial attribution; zero model/native calls."""
import argparse
import copy
from pathlib import Path
import research43_paired_ablation as c
from research43_report import protection_losses
import research15_acceptance as strict


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    initial=c.read(c.INITIAL)
    keep=dict(operation='keep',assertion_id='',assertions=[],reason='Local parser fixture, never a model response.')
    check('keep_exact_hash',c.loop.sha(c.assemble(keep,initial))==c.loop.sha(initial))
    for name,change in (('keep_slot',dict(assertion_id='a2')),('keep_body',dict(assertions=[{}])),('unknown_op',dict(operation='other'))):
        try:c.assemble({**keep,**change},initial)
        except (AssertionError,ValueError,KeyError):check('reject_'+name,True)
        else:check('reject_'+name,False)
    source=c.HISTORY/'core/history/case_0/ledger.json'
    info=c.loop.inspect(c.read(source)['ledger'])
    key=sorted(info['detections'])[0];row=info['rows'][key]
    missed=copy.deepcopy(row)
    for assertion in missed['native']['assertions']:
        assertion['failed']=False;assertion['causal_detection']=False
    verdict=strict.decide([row],[missed]);loss=protection_losses([row],[missed],verdict)
    check('known_miss_is_confirmed_loss',key in loss['confirmed']['lost_target_detection'])
    unknown=copy.deepcopy(missed);unknown['native']['execution']='unknown'
    loss=protection_losses([row],[unknown],strict.decide([row],[unknown]))
    check('unknown_not_claimed_as_gain',not any(loss['confirmed'].values()))
    check('unknown_loss_retained',key in loss['unconfirmed']['lost_target_detection'])
    changed=copy.deepcopy(missed);changed['stimulus_sha256']='explicit_identity_mutation_fixture'
    loss=protection_losses([row],[changed],strict.decide([row],[changed]))
    check('changed_identity_not_claimed_as_gain',not any(loss['confirmed'].values()))
    loss=protection_losses([row],[],strict.decide([row],[]))
    check('missing_row_not_claimed_as_gain',not any(loss['confirmed'].values()))
    c.dump(out/'verification.json',dict(passed=True,checks=checks,model_calls=0,native_calls=0,
        source=dict(path=str(source),sha256=c.digest(source),evidence_id=key),
        scope='Explicit ledger mutations test reporting classification only; not new RTL faults, model proposals or mechanism benefit.'))
    c.dump(out/'source_hashes.json',{p.name:c.digest(p) for p in (Path(__file__),Path(c.__file__),c.ROOT/'scripts/research43_report.py')})
    print('PAIRED_QUALIFICATION',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
