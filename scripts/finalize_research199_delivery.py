from pathlib import Path
import json
from research194_refinement_runner import read,dump,file_hash
from research199_prepare import verify
from research199_refinement import ARMS
import research199_linkage as linkage
import research199_results as results
from audit_research199_delivery import dependencies,run as audit
from cards_research199_delivery import attach
from report_research199_delivery import run as report
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote

def run():
    base=Path('deliverables')
    prepared=base/'research199_refinement_prepare_20261104_r01'
    execution=base/'research199_refinement_execute_20261104_r01'
    original=base/'research199_finish_20261104_r02'
    out=base/'research199_finish_20261104_r03'
    cards=base/'research199_case_cards_20261104_r01'
    delivery=base/'reguard_mechanisms_20261104_r11'
    recovery=read(out/'recovery.json');snapshot=recovery['original_artifact_hashes'];ledger_hash=recovery['model_ledger_sha256'];done=read(out/'progress.json')
    bad=execution/'historical_stream_delay/19711/A3/refinement/acquisitions.json'
    sources=sorted((bad.parent.parent/'acquisition').glob('query*/acquisition.json'))
    restored=[read(p) for p in sources]
    rounds=read(bad.parent/'rounds.json')
    assert len(restored)==len(rounds)==3
    for r,a in zip(rounds,restored):
        current=read(bad.parent/f"round{r['round']:02}"/'current_measurement.json')
        assert a['candidate_sha256']==current['candidate_sha256']==a['selection']['candidate_sha256']
        assert a['heldout_access'] is False
    dump(out/'restored_acquisitions.json',restored)
    dump(out/'acquisition_recovery.json',dict(original=str(bad),original_sha256=file_hash(bad),sources={str(p):file_hash(p) for p in sources},reason='Malformed aggregate JSON; reconstruct only from complete original per-query records, validated against per-round current candidate; original unchanged.',model_calls=0,native_calls=0))
    normal_read=linkage.read
    def restored_read(path):
        return restored if Path(path).resolve()==bad.resolve() else normal_read(path)
    linkage.read=restored_read
    linkage.run(prepared,execution,out/'cost',out/'linkage.json')
    results.run(prepared,execution,out/'acceptance/native',out/'cost',out/'linkage.json',out/'report')
    verify(prepared);dependencies(prepared)
    if file_hash(execution/'ledger.json')!=ledger_hash:raise ValueError('model_ledger_changed_during_native_recovery')
    dump(out/'outcome.json',dict(status='execution_and_analysis_complete_after_explicit_native_recovery',model_calls=0,phases=done,recovery_record='recovery.json'))
    attach(cards,out/'acceptance/native');audit(prepared,execution,out);report(prepared,execution,out,cards,delivery)
    errors=[];checks=0
    def check(ok,label):
        nonlocal checks
        checks+=1
        if not ok:errors.append(label)
    for path,h in snapshot.items():check(file_hash(path)==h,'interrupted_artifact_changed:'+path)
    for path,h in read(delivery/'manifest.json')['source_bindings'].items():check(file_hash(path)==h,'delivery_binding:'+path)
    check((cards/'selection.json').stat().st_mtime_ns<(original/'acceptance/native/plan.json').stat().st_mtime_ns,'case_selection_not_before_original_acceptance')
    check(file_hash(original/'cost/registration.json')==file_hash(out/'cost/registration.json'),'preregistered_cost_changed')
    class Links(HTMLParser):
        def __init__(self,path):super().__init__();self.path=path
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs);url=attrs.get('href') if tag=='a' else attrs.get('src') if tag=='img' else None
            if not url:return
            uri=urlsplit(url)
            if not uri.scheme and not uri.netloc and uri.path:check((self.path.parent/unquote(uri.path)).resolve().is_file(),'broken_link:'+url)
    for path in (delivery/'report.html',cards/'cards.html',out/'report/report.html'):Links(path).feed(path.read_text(encoding='utf-8'))
    result=dict(status='failed' if errors else 'passed',checks=checks,failures=errors,model_calls=0,
        source_bindings={str(Path(__file__).resolve()):file_hash(__file__)},recovery=str((out/'recovery.json').resolve()),
        note='The ENOSPC attempt remains an infrastructure interruption. Recovered scores use the full unchanged registered population; incomplete first-attempt cost is not zero.')
    dump(delivery/'delivery_audit.json',result);print(result,flush=True)
    if errors:raise SystemExit(1)


if __name__=='__main__':run()
