"""Explicit local-only recovery of an ENOSPC-interrupted acceptance attempt.

Preserve the failed attempt, reuse byte-identical preregistered checkpoints and
frozen candidates, and rerun the entire identical native acceptance population.
No model transport is instantiated; no failed mutant or input is substituted.
"""
import argparse
import json
from pathlib import Path
import shutil
import time
from html.parser import HTMLParser
from urllib.parse import urlsplit,unquote
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest
from research199_prepare import verify
import research199_independent as independent
import research199_cost as cost
import research199_linkage as linkage
import research199_results as results
from audit_research199_delivery import dependencies,run as audit
from cards_research199_delivery import attach
from report_research199_delivery import run as report


def run(prepared,execution,original,out,cards,delivery):
    verify(prepared);dependencies(prepared)
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('not_frozen')
    if (original/'outcome.json').exists():raise ValueError('original_attempt_not_interrupted')
    if set(p.name for p in (original/'cost').iterdir())!={'registration.json','seal.json'}:raise ValueError('unexpected_cost_state')
    if read(cards/'selection.json')['selection_reads_independent_results']:raise ValueError('invalid_example_selection')
    out.mkdir(parents=True,exist_ok=True)
    if any(out.iterdir()):raise ValueError('recovery_output_not_empty')
    snapshot={str(p.resolve()):file_hash(p) for p in original.rglob('*') if p.is_file()}
    known=0;records=0
    for p in (original/'acceptance/native').rglob('*.json'):
        if p.name not in ('compile.json','execute.json'):continue
        try:r=read(p)
        except (ValueError,OSError):continue
        if isinstance(r.get('wall_seconds'),(int,float)):known+=r['wall_seconds'];records+=1
    ledger_hash=file_hash(execution/'ledger.json')
    recovery=dict(reason='Prior local acceptance process ended during conversation interruption; no running process remained',
        original_attempt=str(original.resolve()),original_artifact_hashes=snapshot,model_calls=0,model_retry=False,
        model_ledger_sha256=ledger_hash,remediation='Preserve prior attempts; validate and reuse complete fault measurements; execute only missing complete measurements.',
        native_recovery='Same frozen acceptance population graded in a new directory; complete native measurements reused, missing measurements executed; all prior files preserved.',
        cost_registration_recomputed=False,known_interrupted_native_seconds=known,known_interrupted_command_records=records,
        interrupted_native_cost_complete=False,unknown_interrupted_cost='The final failed compile could not write its timing/result record; never count this missing cost as zero.',
        source_sha256=file_hash(__file__))
    dump(out/'recovery.json',recovery)
    protocol=read(original/'protocol.json');protocol['recovery']=str((out/'recovery.json').resolve());dump(out/'protocol.json',protocol)
    (out/'cost').mkdir();(out/'acceptance').mkdir()
    for name in ('registration.json','seal.json'):
        shutil.copy2(original/'cost'/name,out/'cost'/name)
        if file_hash(original/'cost'/name)!=file_hash(out/'cost'/name):raise ValueError('cost_copy_changed')
    shutil.copy2(original/'acceptance/freeze.json',out/'acceptance/freeze.json')
    if file_hash(original/'acceptance/freeze.json')!=file_hash(out/'acceptance/freeze.json'):raise ValueError('freeze_copy_changed')
    module=independent.runtime(prepared/'acceptance_registration.json')
    original_evaluate=module.cases.evaluate
    reused=[]
    def evaluate(cid,candidate,folder,**kwargs):
        prior=original/'acceptance/native'/cid/kwargs['fault']
        measurement=prior/'measurement.json'
        if not measurement.exists():return original_evaluate(cid,candidate,folder,**kwargs)
        m=read(measurement); config=read(prior/'protocol.json')
        if m['candidate_sha256']!=digest(candidate) or config['queries']!=kwargs['queries'] or config['fault']!=kwargs['fault']:raise ValueError('reused_measurement_identity')
        for path,h in m['source_bindings'].items():
            if file_hash(path)!=h:raise ValueError('reused_source_changed')
        for job in m['executions']:
            f=Path(job['folder'])
            if read(f/'result.json')!=job['result'] or read(f/'reference.json')!=job['reference']:raise ValueError('reused_job_mismatch')
            if job['result'].get('source_sha256')!=file_hash(f/'tb.sv'):raise ValueError('reused_native_source_mismatch')
        reused.append(dict(case_id=cid,fault=kwargs['fault'],source=str(measurement),sha256=file_hash(measurement),original_physical_cost=m['cost']))
        m['cost']=dict(m['cost'],native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0,physical_reuse=True)
        dump(Path(folder)/'measurement.json',m);dump(out/'reused_measurements.json',reused)
        print('REUSE_COMPLETE',cid,kwargs['fault'],flush=True)
        return m
    module.cases.evaluate=evaluate
    def validate_plan():
        if digest(read(original/'acceptance/native/plan.json'))!=digest(read(out/'acceptance/native/plan.json')):raise ValueError('recovery_changed_registered_inputs_or_faults')
    steps=[('independent_recovery',lambda:module.execute(out/'acceptance/freeze.json',out/'acceptance/native')),
        ('same_input_plan_check',validate_plan),
        ('cost_evaluation',lambda:cost.runtime().evaluate(out/'cost',out/'acceptance/native')),
        ('cost_analysis',lambda:cost.analyze(out/'cost')),
        ('linkage',lambda:linkage.run(prepared,execution,out/'cost',out/'linkage.json')),
        ('report',lambda:results.run(prepared,execution,out/'acceptance/native',out/'cost',out/'linkage.json',out/'report'))]
    done=[]
    for name,fn in steps:
        start=time.monotonic();fn();done.append(dict(phase=name,seconds=time.monotonic()-start));dump(out/'progress.json',done);print('DONE',name,flush=True)
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


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('prepared','execution','original','out','cards','delivery'):parser.add_argument('--'+key,type=Path,required=True)
    a=parser.parse_args();run(a.prepared,a.execution,a.original,a.out,a.cards,a.delivery)
