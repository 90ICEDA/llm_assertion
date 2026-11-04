"""Rejudge archived handwritten native controls; no new native/model requests.

Every current generated bench, DUT source and independent reference result must
equal its archived execution. This never attributes new source to an old run.
"""
import argparse
import copy
from pathlib import Path
import research194_cases as cases
import research194_refinement as r
import research194_refinement_runner as run

def regrade(source,out):
    source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    keys=('baseline','failed_local','successful_composition','failed_composition','successful_regeneration','structured_operations')
    checked=[];measurements={};candidates={}
    for key in keys:
        original=source/key;protocol=run.read(original/'protocol.json');candidate=protocol['candidate'];candidates[key]=candidate
        m=run.read(original/'measurement.json');valid=True
        for j in m['executions']:
            folder=Path(j['folder']);q=next(q for q in protocol['queries'] if q['id']==j['query_id'])
            expected=cases._bench('counter',candidate,q['rows'],j['variant'])
            bench=expected==(folder/'tb.sv').read_text()
            monitor=cases.reference('counter',j['trace'])==j['reference']
            generated=cases._sources('counter',out/'source_verification'/key/j['variant'],j['variant'])
            rtl=all(p.read_bytes()==(folder.parent/(j['variant']+'_rtl')/p.name).read_bytes() for p in generated)
            healthy=j['result']['compile_status']=='passed' and j['result']['execution_status']=='completed'
            checked.append(dict(control=key,variant=j['variant'],bench_equal=bench,independent_reference_equal=monitor,rtl_equal=rtl,native_healthy=healthy))
            valid=valid and bench and monitor and rtl and healthy
        if not valid:
            run.dump(out/'checks.json',checked)
            run.dump(out/'outcome.json',dict(status='not_qualified',reason='archived_native_not_equivalent:'+key,new_native_jobs=0,new_model_calls=0))
            raise AssertionError('archived_native_not_equivalent:'+key)
        revised=0
        for ev in m['evidence']:
            if ev['label']=='legal' and ev['variant']!='correct':
                revised+=ev['status']=='confirmed';ev['status']='unknown'
        m['false_positives']=[e for e in m['false_positives'] if e['variant']=='correct']
        notices=[u for u in m['critical_unknown'] if u.get('reason')==['source_changed_during_execution']]
        m['critical_unknown']=[u for u in m['critical_unknown'] if u not in notices]
        m['reference_complete']=not m['critical_unknown'];m['native_complete']=True
        m['regrade']=dict(original_measurement=str(original/'measurement.json'),original_sha256=run.file_hash(original/'measurement.json'),
            current_case_source_sha256=run.file_hash(cases.__file__),bench_reference_dut_equal=True,legal_mutant_samples_to_unknown=revised,
            original_source_change_notices=notices,new_native_jobs=0,new_model_calls=0,
            claim='Reclassification of original native execution; not execution under a new source version.')
        measurements[key]=run.bind_measurement(m,candidate);run.dump(out/key/'measurement.json',measurements[key])
    initial=candidates['baseline'];baseline=measurements['baseline'];evidence=run.model_evidence(baseline)
    fixtures=run.read(source/'fixture_inputs.json');obligations=cases.get_case('counter')['obligations']
    outcomes={}
    for name,second,third in [('two_round','successful_composition',None),('three_round','failed_composition','successful_regeneration')]:
        c=r.Controller(initial,'R3',obligations,protected=set(baseline['detected_ids']))
        p,edit=c.parse(fixtures['local'],evidence,lambda x:cases.validate('counter',x))
        if p!=candidates['failed_local']:raise AssertionError('local_bytes_changed')
        c.observe(p,measurements['failed_local'],baseline=baseline,edit_record=edit)
        if c.stage!='compose':raise AssertionError('local_failure_not_confirmed')
        response=fixtures['compose'] if second=='successful_composition' else fixtures['failed_compose']
        p,edit=c.parse(response,evidence,lambda x:cases.validate('counter',x))
        if p!=candidates[second]:raise AssertionError('composition_bytes_changed')
        c.observe(p,measurements[second],baseline=baseline,edit_record=edit)
        if third:
            if c.stage!='regenerate':raise AssertionError('composition_failure_not_confirmed')
            p,edit=c.parse(fixtures['regenerate'],evidence,lambda x:cases.validate('counter',x))
            if p!=candidates[third]:raise AssertionError('regeneration_bytes_changed')
            c.observe(p,measurements[third],baseline=baseline,edit_record=edit)
        if not c.history[-1]['decision']['accepted']:raise AssertionError('final_handwritten_control_rejected')
        outcomes[name]=c.history
    result=dict(provenance='Handwritten controls and read-only reclassification; not LLM results',new_model_calls=0,new_native_jobs=0,
        original_native_compile_attempts=sum(m['cost']['native_compile_attempts'] for m in measurements.values()),
        checked_native_jobs=len(checked),all_bench_reference_dut_equal=True,
        branch_scope='Explicit measured-local-failure state-machine paths; automatic structural-empty-domain choice is separately unit-tested.',
        outcomes=outcomes,structured_operations_false_positives=len(measurements['structured_operations']['false_positives']),
        current_sources={str(Path(m.__file__).resolve()):run.file_hash(m.__file__) for m in (r,run,cases)})
    run.dump(out/'checks.json',checked);run.dump(out/'qualification.json',result)
    print('RECLASSIFIED '+str(len(checked))+' original native jobs; new_native_jobs=0 model_calls=0',flush=True)
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();regrade(a.source.resolve(),a.out.resolve())
