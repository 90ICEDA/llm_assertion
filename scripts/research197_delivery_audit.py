"""Close postprocessing with file/link receipts; never runs models or RTL."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
from research194_refinement_runner import ROOT,read,dump,file_hash


def run():
    d=ROOT/'deliverables';out=d/'reguard_mechanisms_20261104_r07'
    main=read(out/'final_audit.json');combined=read(out/'combined_audit.json');review=read(out/'remaining_work_review.json')
    if main['status']!='passed' or combined['status']!='passed':raise ValueError('prior_audit_failed')
    if review['model_calls']!=combined['original_calls']+combined['additional_calls'] or review['known_tokens']!=combined['total_known_tokens']:raise ValueError('review_cost_mismatch')
    finish=d/'research197_combined_finish_20261104_r01'
    protocol=read(finish/'protocol.json')
    for path,h in protocol['source_bindings'].items():
        if file_hash(path)!=h:raise ValueError('postprocessing_source_changed:'+path)
    links=[];failures=[]
    class Parser(HTMLParser):
        def __init__(self,path):super().__init__();self.path=path
        def handle_starttag(self,tag,attrs):
            attr=dict(attrs);value=attr.get('href') if tag=='a' else attr.get('src') if tag=='img' else None
            if not value:return
            uri=urlsplit(value)
            if uri.scheme or uri.netloc or not uri.path:return
            target=(self.path.parent/unquote(uri.path)).resolve();ok=target.is_file()
            row=dict(source=str(self.path.relative_to(ROOT)),link=value,exists=ok);links.append(row)
            if not ok:failures.append(row)
    pages=list(out.glob('*.html'))+[d/name/'cards.html' for name in (
        'research197_case_cards_20261104_r01','research197_typed_cards_20261104_r01','research197_corrected_cards_20261104_r01')]
    for path in pages:Parser(path).feed(path.read_text(encoding='utf-8'))
    assets=pages+[out/'search_cost_curves.png',out/'search_cost_curves.pdf',out/'remaining_work_review.json',out/'final_audit.json',out/'combined_audit.json']
    if any(not path.is_file() for path in assets):raise ValueError('missing_delivery_asset')
    receipt=dict(status='failed' if failures else 'registered_experiments_and_delivery_complete',model_calls_during_delivery=0,
        original_calls=combined['original_calls'],additional_calls=combined['additional_calls'],known_tokens=combined['total_known_tokens'],
        main_audit_checks=main['checks'],combined_audit_checks=combined['checks'],local_links_checked=len(links),failures=failures,
        frozen_model_versions=72,independent_records=review['independent_records'],
        full_scope_pass_records=review['independent_full_scope_pass_records'],
        real_model_full_three_stage_native_paths=review['complete_three_stage_native_paths'],
        limitation='Registered experiments are closed. Real-model traversal of all three fallback stages remains uncovered; qualification probes are separate. No overall superiority or universal coverage is claimed.',
        assets={str(path.relative_to(ROOT)):file_hash(path) for path in assets},
        postprocessing_protocol_sha256=file_hash(finish/'protocol.json'),audit_source_sha256=file_hash(__file__))
    dump(out/'delivery_audit.json',dict(**receipt,links=links));dump(finish/'delivery_receipt.json',receipt)
    print({k:v for k,v in receipt.items() if k not in ('assets','limitation')},flush=True)
    if failures:raise SystemExit(1)


if __name__=='__main__':run()
