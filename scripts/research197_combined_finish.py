"""Local post-model pipeline after both authorized cohorts freeze; no transport."""
import argparse
from pathlib import Path
import time
from research194_refinement_runner import ROOT,read,dump,file_hash
import research197_cost_sections as cost
import research197_cards as cards
import research197_results as results
import research197_diagnostics as diagnostics
import research197_typed_analysis as typed
import research197_combined_acceptance as independent
import research197_final_audit as final_audit


def run(out):
    d=ROOT/'deliverables';prepared=d/'research197_refinement_prepare_20261104_r01';execution=d/'research197_refinement_execute_20261104_r01'
    corrected=d/'research197_typed_contract_fix_20261104_r01';corrected_execution=d/'research197_typed_execute_20261104_r01'
    registration=d/'research197_combined_registration_20261104_r01';combined=d/'research197_combined_independent_20261104_r01'
    original=d/'research197_independent_20261104_r01';costout=d/'research197_cost_sections_20261104_r01'
    cardout=d/'research197_case_cards_20261104_r01';diagout=d/'research197_typed_cards_20261104_r01'
    typedout=d/'research197_typed_analysis_20261104_r01';fixedcards=d/'research197_corrected_cards_20261104_r01'
    report=d/'reguard_mechanisms_20261104_r07';out=Path(out)
    for folder in (execution,corrected_execution):
        if read(folder/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('both_cohorts_must_finish')
    out.mkdir(parents=True,exist_ok=False)
    phases=[('register_main_cost',lambda:cost.register(prepared,execution,costout)),
        ('select_main_cards',lambda:cards.runtime().select(prepared,execution,cardout)),
        ('select_all_original_typed_trials',lambda:diagnostics.select(prepared,execution,diagout)),
        ('register_corrected_cost_and_cards',lambda:typed.register(prepared,corrected,execution,corrected_execution,registration,typedout,fixedcards)),
        ('combined_independent_acceptance',lambda:independent.run(registration,combined)),
        ('original_membership_view',lambda:independent.original_view(combined,prepared,original)),
        ('evaluate_main_cost',lambda:cost.runtime().evaluate(costout,original/'native')),
        ('analyze_main_cost',lambda:cost.runtime().analyze(costout)),
        ('attach_main_cards',lambda:cards.runtime().attach(cardout,original/'native')),
        ('main_report',lambda:results.build(prepared,execution,original/'native',costout,report)),
        ('attach_original_typed_trials',lambda:diagnostics.attach(diagout,original/'native',report)),
        ('corrected_analysis_and_cards',lambda:typed.finish(typedout,combined/'native',report)),
        ('main_final_audit',lambda:final_audit.audit(prepared,execution,original/'native',costout,cardout,report,prepared/'authorization.json'))]
    modules=[Path(m.__file__).resolve() for m in (cost,cards,results,diagnostics,typed,independent,final_audit)]
    modules+=[Path(__file__).resolve(),ROOT/'scripts/research196_results.py',ROOT/'scripts/research196_cards.py',ROOT/'scripts/research196_cost_sections.py']
    dump(out/'protocol.json',dict(model_calls=0,phase_order=[name for name,_ in phases],source_bindings={str(path):file_hash(path) for path in modules},
        model_cohorts=72,independent_scope='Original registered fault definitions and input seeds; shared physical execution, separate cohort membership.'))
    completed=[]
    for name,action in phases:
        dump(out/'status.json',dict(status='running',phase=name,completed=completed,model_calls=0));print('PHASE',name,flush=True);start=time.monotonic()
        try:action()
        except BaseException as exc:
            dump(out/'status.json',dict(status='failed',phase=name,error_type=type(exc).__name__,error=str(exc),completed=completed,model_calls=0,retried=False));raise
        completed.append(dict(phase=name,wall_seconds=time.monotonic()-start))
    dump(out/'status.json',dict(status='local_phases_completed',completed=completed,model_calls=0,plot_and_combined_authorization_audit_pending=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);run(p.parse_args().out)
