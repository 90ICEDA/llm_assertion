"""Check delivered references and final source bindings without rerunning experiments."""
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import research194_case_atlas as atlas

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'
OUT=D/'reguard_mechanisms_20261103_r02'

class Links(HTMLParser):
    def __init__(self):super().__init__();self.references=[]
    def handle_starttag(self,tag,attrs):
        self.references.extend(v for k,v in attrs if k in ('href','src') and v)

def check():
    failures=[];binding_checks=0;link_checks=0
    files=[(OUT/'completion.json',['source_bindings','analysis_source_bindings']),
           (OUT/'case_cards/itt_status.json',['source_sha256']),
           (D/'research194_active_outcomes_20261103_r01/analysis.json',['source_bindings']),
           (D/'research194_ablation_interactions_20261103_r01/analysis.json',['source_sha256'])]
    for file,keys in files:
        data=json.loads(file.read_text(encoding='utf-8'))
        for key in keys:
            for path,expected in data[key].items():
                p=atlas.repository_path(path);binding_checks+=1
                if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected:
                    failures.append(dict(type='binding',artifact=str(file.relative_to(ROOT)),path=path))
    pages=[OUT/'report.html',OUT/'case_atlas.html',OUT/'case_cards/case_cards.html',OUT/'case_cards/itt_case_cards.html',
           D/'research194_fault_augmentation_audit_20261103_r01/report.html']
    for page in pages:
        parser=Links();parser.feed(page.read_text(encoding='utf-8'))
        for href in parser.references:
            url=urlsplit(href)
            if url.scheme or url.netloc or not url.path:continue
            target=(page.parent/unquote(url.path)).resolve();link_checks+=1
            if not target.exists():failures.append(dict(type='missing_link',page=str(page.relative_to(ROOT)),target=href))
    result=dict(status='passed' if not failures else 'failed',binding_checks=binding_checks,local_link_checks=link_checks,
        failures=failures,model_calls=0,native_executions=0,
        rendered_artifact_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in pages})
    (OUT/'delivery_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    if failures:raise SystemExit(1)

if __name__=='__main__':check()
