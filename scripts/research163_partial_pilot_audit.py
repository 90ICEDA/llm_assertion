"""Audit sealed local qualification and future branching, no simulator/model calls."""
import argparse
import ast
import json
from pathlib import Path
import re
import research162_partial_candidate as q


def run(prep, native, report, out):
    q.verify(prep)
    out.mkdir(parents=True, exist_ok=False)
    checks=[]
    def check(name, value):
        checks.append(dict(check=name, passed=bool(value)))
        assert value, name
    for n,h in q.read(report/'report_seal.json').items():
        check('report seal '+n, q.sha(report/n)==h)
    for rev in ('before','after'):
        for p in (prep/'rtl'/rev).iterdir():
            check('original source '+rev+'/'+p.name, p.read_bytes()==(q.PRIOR/'ibex54'/rev/p.name).read_bytes())
    rows=q.read(prep/'vectors.json')
    by=q.read(report/'acceptance_matrix.json')
    matrix={r['control']:r for r in by}
    mappings=[]
    for control in q.controls():
        a=q.read(prep/'local_controls'/f'{control}.json')['assertions']
        for rev in ('before','after'):
            path=native/control/rev
            result=q.read(path/'result.json')
            log=(path/'execute.log').read_text()
            for key,marker in [('failures','ASSERT_FAIL'),('triggers','TRIGGER')]:
                parsed=[dict(id=i,detail=d.strip()) for i,d in re.findall(r'^'+marker+r'\s+(\S+)(.*)$',log,re.M)]
                check('raw native '+control+'/'+rev+'/'+key, parsed==result[key])
            for assertion in a:
                label=assertion['label']
                triggers=q.positions([r for r in result['triggers'] if r['id']==label])
                failures=q.positions([r for r in result['failures'] if r['id']==label])
                mappings.append(dict(control=control, revision=rev, label=label,
                    declared_obligations=assertion['obligations'],
                    actual_trigger_samples=sorted(triggers),actual_failure_samples=sorted(failures),
                    trigger_targets=sorted({rows[i]['target'] for i in triggers if rows[i]['target']}),
                    violated_target_samples=sorted(i for i in failures if rows[i]['target'] and rev=='before'),
                    note='Mapping is empirical per original RTL sample; declared label alone is not evidence.'))
    request=q.read(report/'pilot/request.preview.json')
    body=json.loads(request['messages'][1]['content'])
    baseline=q.read(prep/'local_controls/baseline.json')['assertions']
    check('exact handwritten baseline in request', body['current_assertions']==baseline)
    check('history target samples absent from first request', all(e['scope']=='public' and e['target']!='shift_hint_legal' for e in body['public_development_evidence']))
    check('no local solution predicate in request', q.IMMEDIATE not in request['messages'][1]['content'])
    check('no evidence of independent evaluation', not any('independent' in k for k in body))
    check('baseline has history protection and current misses', matrix['baseline']['history_detected']==27 and matrix['baseline']['public_detected']==0)
    check('ordinary accepts class replacement', matrix['replacement']['ordinary_accept'])
    check('history alone additionally rejects class replacement', not matrix['replacement']['historical_accept'] and len(matrix['replacement']['lost_baseline_detections'])==27)
    check('complementary set jointly satisfies checks', matrix['complementary']['historical_accept'])
    check('reserved-code false positives rejected', not matrix['overbroad']['ordinary_accept'] and matrix['overbroad']['false_positive_samples']>0)
    # Reuse the existing pure branch function without importing any remote runtime.
    branch_file=q.ROOT/'scripts/research136_prospective_history.py'
    tree=ast.parse(branch_file.read_text())
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='branch')
    module=ast.Module(body=[fn],type_ignores=[]);ast.fix_missing_locations(module)
    ns={};exec(compile(module,str(branch_file),'exec'),ns)
    branch=ns['branch'];branch_checks=[]
    for transport in ('response_received','timeout','http_error'):
        for measured in (False,True):
            for ordinary in (False,True):
                for history in (False,True):
                    for lost,fp in ((0,0),(1,0),(0,1)):
                        for unknown in (0,1):
                            got=branch(transport,measured,ordinary,history,lost,fp,unknown)
                            eligible=transport=='response_received' and measured and ordinary and not history and bool(lost or fp) and not unknown
                            check('branch '+str((transport,measured,ordinary,history,lost,fp,unknown)), (got=='history_once')==eligible)
                            branch_checks.append(dict(transport=transport,measured=measured,ordinary=ordinary,history=history,lost=lost,new_false_positive=fp,unknown=unknown,decision=got))
    check('fixture counts do not increment real recovery',q.read(report/'decision.json')['conditional_recovery']=='0/0 not estimable')
    retention=q.read(report/'retained_version.json')
    check('rejected version does not replace baseline',q.sha(q.ROOT/retention['path'])==retention['sha256'])
    # Full words/sample indices are not used by any hand fixture predicate.
    for name,assertions in q.controls().items():
        for a in assertions:
            check('semantic fields not word whitelist '+name+'/'+a['label'],
                not re.search(r"32'[hbd]|\bsample\b|\bexpected\b", a['antecedent']+' '+a['consequent']))
    q.dump(out/'obligation_assertion_evidence_map.json',mappings)
    q.dump(out/'branch_checks.json',branch_checks)
    q.dump(out/'checks.json',checks)
    q.dump(out/'bindings.json',dict(qualification_seal=q.sha(report/'report_seal.json'),
        prior_branch_source=q.sha(branch_file),audit_source=q.sha(Path(__file__))))
    q.dump(out/'result.json',dict(passed=len(checks),model_calls=0,native_compiles=0,native_executions=0,
        qualification='local handcrafted semantic distinction',real_model_incremental_value='not_yet_executed',
        future_holdout_caveat='Independent generation must exclude the union of current and all archived development low16 words; if requested exposure is infeasible, stop without relaxing uniqueness or using results to tune rules. No holdout generated by this audit.'))
    q.dump(out/'seal.json',{p.name:q.sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(passed=len(checks),model_calls=0),indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for n in ('prepared','native','report','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.native.resolve(),a.report.resolve(),a.out.resolve())
