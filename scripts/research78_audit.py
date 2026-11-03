"""Read-only preparation/result audit using the unchanged research77 gates."""
import argparse
import json
from pathlib import Path
import research78_counterexample_feedback as c
import research77_result_audit as previous_audit


def prepare(prep,out):
    c.gate.old.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,okay):
        assert okay,name
        checks.append(name)
    rows=c.read(prep/'windows.private.json')
    req=c.read(prep/'plan_request.preview.json');body=json.loads(req['messages'][1]['content'])
    before=c.read(c.P/'plan_request.preview.json');oldbody=json.loads(before['messages'][1]['content'])
    plan=c.read(c.R/'plan/v0/model_call/hold_plan.json');decision=c.gate.validate(plan,rows)
    check('raw archived response matches',c.raw_response(c.R/'plan/v0/model_call',plan))
    check('independent diagnosis recomputed',decision==c.read(c.R/'plan/v0/decision.json'))
    check('exact feedback from failed response',body['actual_failed_plan_feedback']==c.feedback(plan,decision,rows))
    oldbody.pop('previous_actual_rejection');oldbody['actual_failed_plan_feedback']=c.feedback(plan,decision,rows)
    check('exact request body',body==oldbody)
    check('public protocol unchanged',body['response_schema']==c.gate.schema(rows))
    check('no transport or sampling change',
        {k:v for k,v in req.items() if k!='messages'}=={k:v for k,v in before.items() if k!='messages'})
    check('exact system prompt',req['messages'][0]==before['messages'][0])
    for name in ('windows.private.json','windows.public.json','window_cases.json','cases.json','history_cases.json',
                 'initial.json','sva_template.json','excluded_inputs.json','protected.json','model_config.json'):
        check('unchanged '+name,c.read(prep/name)==c.read(c.P/name))
    check('local feedback tests passed',c.read(prep/'feedback_checks.json')['passed'])
    check('full semantic tests passed',c.read(prep/'local_checks.json')['passed'])
    check('unchanged runtime gate',c.gate.run.__module__=='research77_rule_consistency')
    check('research77 failure remains',not c.read(c.R/'outcome.json')['plan_passed'])
    check('no conditional generation already run',not (c.R/'sva_request.preview.json').exists())
    c.dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        code_sha256=c.b.search.digest(Path(__file__)),sealed_sha256=c.b.search.digest(prep/'sealed.json')))
    print('PREFLIGHT',len(checks),'checks',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','result']);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.action=='prepare':prepare(a.prepared.resolve(),a.out.resolve())
    else:
        previous_audit.result(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
        report=a.out/'SUMMARY.md'
        report.write_text(report.read_text(encoding='utf-8').replace('# research77','# research78',1),encoding='utf-8')
