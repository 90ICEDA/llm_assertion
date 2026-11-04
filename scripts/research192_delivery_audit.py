"""Check the published campaign tables, links and bound report sources."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/reguard_mechanisms_20261103_r01'


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.paths=[]

    def handle_starttag(self,tag,attrs):
        for key,value in attrs:
            if key in ('href','src') and value:
                self.paths.append(value)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
    tables=read(OUT/'tables.json')
    for section in ('search_diagnostic','search_native','refinement','ablation'):
        check(section+'_four_arms',len(tables[section])==4)
    check('sixteen_independent_versions',len(tables['new_independent'])==16)
    check('one_new_independent_parent',len({r['parent_bug'] for r in tables['new_independent']})==1)
    check('no_exposure_not_full_pass',all(not r['whole_scope_pass'] for r in tables['new_independent'] if r['missing_exposure']))
    cost=read(OUT/'actual_costs.json')
    check('sixteen_actual_model_calls',cost['total_model_calls']==16)
    tokens=sum(r['prompt_tokens']+r['completion_tokens'] for r in cost['rows'] if r['model_calls'])
    check('tokens_match_call_audit',tokens==220028)
    check('request_audit_passed',read(OUT/'model_call_audit.json')['audit_status']=='passed')
    for name,digest in read(OUT/'source_bindings.json').items():
        check('report_source:'+name,hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest)
    parser=Links(); parser.feed((OUT/'report.html').read_text(encoding='utf-8'))
    for path in parser.paths:
        if '://' not in path and not path.startswith('#'):
            check('local_link:'+path,(OUT/path.split('#')[0]).exists())
    independent=ROOT/'deliverables/research192_independent_20261103_r01'
    native_cost=read(independent/'cost.json')
    check('native_validation_32_pairs_of_revision_jobs',native_cost['physical_compiles']==32 and native_cost['physical_executions']==32)
    check('independent_no_model_calls',native_cost['model_calls']==0)
    result=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',checks=checks,
                total_tokens=tokens,scope='Delivery consistency only; native semantic audit is separate.')
    (OUT/'delivery_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(result['status'],len(checks),'checks')
    if result['status']!='passed':raise SystemExit(1)


if __name__=='__main__':main()
