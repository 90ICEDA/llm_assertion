"""Check the delivered R195 artifacts without invoking models or native jobs."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'deliverables'
OUT = D / 'reguard_mechanisms_20261103_r03'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def local(path):
    return Path(str(path).replace('/mnt/d/AssertionForge-main1', str(ROOT)))


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []
    def handle_starttag(self, tag, attrs):
        self.links += [v for k, v in attrs if k in ('href', 'src') and v]


def run():
    failures=[]; checks=0
    def check(ok, message):
        nonlocal checks
        checks += 1
        if not ok: failures.append(message)
    for name in ('source_bindings.json','cost_source_bindings.json'):
        for p,h in read(D/'reguard_mechanisms_20261103_r02'/name).items():
            q=ROOT/p
            check(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest()==h,'old_binding:'+p)
    for p,h in read(OUT/'source_bindings.json').items():
        q=ROOT/p
        check(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest()==h,'new_binding:'+p)
    execution=D/'research195_refinement_execute_20261103_r01'
    ledger=read(execution/'ledger.json'); auth=read(OUT/'authorization.json')
    prepared=read(D/'research195_refinement_prepare_20261103_r01/protocol.json')
    allowed={e['request_sha256'] for e in prepared['entries'] if e['mode']=='ready'}
    check(len(ledger)==18 and len(ledger)<=auth['maximum_model_calls'],'authorized_call_count')
    check(len({r['request_sha256'] for r in ledger})==len(ledger),'duplicate_model_request')
    check(all(r['request_sha256'] in allowed for r in ledger),'request_outside_sealed_population')
    check(all(r.get('model_calls')==1 for r in ledger),'unexpected_per_request_call_count')
    check(read(execution/'outcome.json')['population']==24,'frozen_population')
    frozen=list(execution.glob('*/*/*/refinement/frozen.json'))
    check(len(frozen)==24,'frozen_file_count')
    ind=D/'research195_refinement_independent_20261103_r02'
    check(read(ind/'outcome.json')['status']=='completed','independent_completion')
    for p,h in read(ind/'plan.json')['frozen_bindings'].items():
        q=local(p)
        check(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest()==h,'frozen_candidate_changed:'+str(p))
    active=read(D/'research195_active_native_20261103_r01/audit.json')
    check(active['status']=='passed' and active['native_jobs_replayed']==112,'native_active_audit')
    reports=[OUT/'report.html',D/'research195_cost_sections_20261103_r01/curves.html',D/'research195_active_native_20261103_r01/report.html',D/'research195_refinement_report_20261103_r01/report.html']
    for p in reports:
        parser=Links();parser.feed(p.read_text(encoding='utf-8'))
        for value in parser.links:
            parsed=urlsplit(value)
            if parsed.scheme and parsed.scheme not in ('file',):continue
            if not parsed.path:continue
            target=local(unquote(parsed.path))
            if not target.is_absolute():target=p.parent/target
            check(target.exists(),'missing_link:'+str(p)+':'+value)
    result=dict(status='passed' if not failures else 'failed',checks=checks,failures=failures,
                actual_model_requests=len(ledger),frozen_files=len(frozen),new_model_calls=0,new_native_jobs=0,
                audit_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'delivery_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if failures:raise SystemExit(1)


if __name__=='__main__':
    run()
