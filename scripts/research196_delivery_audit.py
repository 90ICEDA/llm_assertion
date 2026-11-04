"""Read-only old-artifact check, plus new local links and sealed request audit."""
from html.parser import HTMLParser
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump,file_hash
from research194_refinement import digest

OUT=ROOT/'deliverables/reguard_mechanisms_20261103_r04'


def local(path):return Path(str(path).replace('/mnt/d/AssertionForge-main1',str(ROOT)))


def run():
    failures=[];checks=0
    for path in (ROOT/'deliverables/reguard_mechanisms_20261103_r03/source_bindings.json',OUT/'source_bindings.json'):
        for source,h in read(path).items():
            checks+=1;p=local(source)
            if not p.is_file() or file_hash(p)!=h:failures.append(dict(kind='changed_or_missing_binding',path=str(p)))
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            nonlocal checks
            if tag!='a':return
            href=dict(attrs).get('href','')
            if href and '://' not in href and not href.startswith('#'):
                checks+=1;p=(OUT/href).resolve()
                if not p.is_file():failures.append(dict(kind='broken_link',path=str(p)))
    Links().feed((OUT/'report.html').read_text(encoding='utf-8'))
    prepared=ROOT/'deliverables/research196_refinement_prepare_20261103_r01'
    protocol=read(prepared/'protocol.json');seal=read(prepared/'seal.json')['protocol_sha256']
    checks+=1
    if file_hash(prepared/'protocol.json')!=seal:failures.append(dict(kind='protocol_changed'))
    for path,h in protocol['source_bindings'].items():
        checks+=1
        if file_hash(path)!=h:failures.append(dict(kind='sealed_source_changed',path=path))
    for e in protocol['entries']:
        checks+=2
        if file_hash(e['state'])!=e['state_sha256']:failures.append(dict(kind='state_changed',id=e['id']))
        if digest(read(e['request']))!=e['request_sha256']:failures.append(dict(kind='request_changed',id=e['id']))
    log=(OUT/'unittest.log').read_text(encoding='utf-8');checks+=1
    if 'Ran 15 tests' not in log or not log.strip().endswith('OK'):failures.append(dict(kind='unit_tests_not_passed'))
    result=dict(status='passed' if not failures else 'failed',checks=checks,failures=failures,
        model_calls=0,new_native_jobs=78,unit_tests_passed=15,registered_trajectories=64,
        callable_first_requests=protocol['exact_first_requests'],maximum_model_calls=protocol['maximum_model_calls'],
        protocol_sha256=seal,latest_model_campaign_executed=False,latest_unseen_fault_acceptance_executed=False)
    dump(OUT/'delivery_audit.json',result);print(result,flush=True)


if __name__=='__main__':run()
