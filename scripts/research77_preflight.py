"""Verify sealed requests, sample binding and generation interlock locally."""
import argparse
import copy
import json
from pathlib import Path
import research77_rule_consistency as c


def run(prep,out):
    c.old.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,okay):
        assert okay,name
        checks.append(name)
    rows=c.read(prep/'windows.private.json')
    req=c.read(prep/'plan_request.preview.json');body=json.loads(req['messages'][1]['content'])
    previous=c.read(c.P/'plan_request.preview.json');oldbody=json.loads(previous['messages'][1]['content'])
    check('scalar rule schema',body['response_schema']==c.schema(rows))
    check('public samples only',body['windows']==[w['public'] for w in rows])
    check('no private sample fields',all(set(w)=={'id','anchor_sample','check_sample'} for w in body['windows']))
    changed={'task','instruction','response_schema','previous_actual_rejection'}
    check('only intended request fields changed',
        {k:v for k,v in body.items() if k not in changed}=={k:v for k,v in oldbody.items() if k not in changed})
    check('no hidden extra request fields',set(body)==set(oldbody)|{'previous_actual_rejection'})
    check('transport and sampling unchanged',
        {k:v for k,v in req.items() if k!='messages'}=={k:v for k,v in previous.items() if k!='messages'})
    check('system message unchanged',req['messages'][0]==previous['messages'][0])
    for name in ('initial.json','cases.json','history_cases.json','window_cases.json','windows.public.json',
                 'windows.private.json','sva_template.json','excluded_inputs.json','protected.json','model_config.json'):
        check('unchanged '+name,c.read(prep/name)==c.read(c.P/name))
    check('local tests passed',c.read(prep/'local_checks.json')['passed'])
    check('native controls re-audited',c.read(prep/'native_reaudit.json')['passed'] and c.read(prep/'native_reaudit.json')['raw_records']==30)
    good=dict(**c.fixture_rules(),windows=[r['expected'] for r in rows])
    verdict=c.validate(good,rows)
    unlocked=c.unlock(c.read(prep/'sva_template.json'),good,verdict,rows)
    content=json.loads(unlocked['messages'][1]['content'])
    check('passing fixture preserved exactly, local only',content['verified_model_hold_plan']==good)
    altered=copy.deepcopy(verdict);altered['windows']=0
    try:c.unlock(c.read(prep/'sva_template.json'),good,altered,rows)
    except ValueError:rejected=True
    else:rejected=False
    check('forged acceptance certificate rejected',rejected)
    check('no fixture embedded in real request','verified_model_hold_plan' not in body)
    p=c.read(prep/'protocol.json')
    check('one judgment then conditional one SVA',p['maximum_calls']==2 and p['plan_maximum']==1 and p['sva_maximum']==1 and p['retries']==0)
    check('research76 unchanged failed outcome',not c.read(c.R/'outcome.json')['accepted'] and c.read(c.R/'outcome.json')['model_calls']==1)
    c.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        sealed_sha256=c.b.search.digest(prep/'sealed.json'),code_sha256=c.b.search.digest(Path(__file__))))
    print('PREFLIGHT',len(checks),'checks',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.out.resolve())
