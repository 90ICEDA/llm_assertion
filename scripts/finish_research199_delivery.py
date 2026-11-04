"""Run the unchanged sealed finish pipeline, then additive delivery checks."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
from research194_refinement_runner import read,dump,file_hash
from audit_research199_delivery import dependencies,run as audit
from cards_research199_delivery import select,attach
from report_research199_delivery import run as report
from research199_finish import run as finish


def run(prepared,execution,finished,cards,delivery):
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':
        raise ValueError('all_versions_must_freeze')
    print('DYNAMIC_DEPENDENCIES_BEFORE',dependencies(prepared),flush=True)
    select(prepared,execution,cards)
    finish(prepared,execution,finished)
    print('DYNAMIC_DEPENDENCIES_AFTER',dependencies(prepared),flush=True)
    attach(cards,finished/'acceptance/native')
    audit(prepared,execution,finished)
    report(prepared,execution,finished,cards,delivery)
    failures=[];checks=0
    def check(ok,label):
        nonlocal checks
        checks+=1
        if not ok:failures.append(label)
    class Links(HTMLParser):
        def __init__(self,path):super().__init__();self.path=path
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs);href=attrs.get('href') if tag=='a' else attrs.get('src') if tag=='img' else None
            if not href:return
            uri=urlsplit(href)
            if not uri.scheme and not uri.netloc and uri.path:
                check((self.path.parent/unquote(uri.path)).resolve().is_file(),str(self.path)+': '+href)
    for path in (delivery/'report.html',cards/'cards.html',finished/'report/report.html'):
        Links(path).feed(path.read_text(encoding='utf-8'))
    for path,h in read(delivery/'manifest.json')['source_bindings'].items():
        check(file_hash(path)==h,path)
    check((cards/'selection.json').stat().st_mtime_ns<(finished/'acceptance/native/plan.json').stat().st_mtime_ns,'example selection after independent inputs')
    snapshot={str(p.resolve()):file_hash(p) for p in [Path(__file__),Path(__file__).with_name('audit_research199_delivery.py'),Path(__file__).with_name('cards_research199_delivery.py'),Path(__file__).with_name('report_research199_delivery.py')]}
    result=dict(status='passed' if not failures else 'failed',checks=checks,failures=failures,model_calls=0,source_bindings=snapshot,
        main_audit=str((finished/'report/final_audit.json').resolve()),independent_results_do_not_enter_model_requests=True)
    dump(delivery/'delivery_audit.json',result);print(result,flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('prepared','execution','finished','cards','delivery'):parser.add_argument('--'+key,type=Path,required=True)
    a=parser.parse_args();run(a.prepared,a.execution,a.finished,a.cards,a.delivery)
