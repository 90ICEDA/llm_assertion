"""Seal postprocessing, then freeze/grade all real model versions. No calls."""
import argparse
from pathlib import Path
import time
from research194_refinement_runner import ROOT,read,dump,file_hash
import research198_cost_sections as cost
import research198_cards as cards
import research198_independent as independent
import research198_results as results
import research198_audit as audit
import research198_paths as paths
import research198_fix_replay as fix_replay
import research198_active_obligation_fix as obligation_fix

def run(out):
    d=ROOT/'deliverables';out=Path(out)
    prepared=d/'research198_refinement_prepare_20261104_r01';execution=d/'research198_refinement_execute_20261104_r01'
    acceptance=d/'research198_independent_20261104_r01';costout=d/'research198_cost_sections_20261104_r01'
    cardout=d/'research198_case_cards_20261104_r01';report=d/'reguard_mechanisms_20261104_r09'
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('models_must_finish')
    out.mkdir(parents=True,exist_ok=False)
    bindings=dict(read(prepared/'protocol.json')['source_bindings'])
    bindings.update({str(Path(m.__file__).resolve()):file_hash(m.__file__) for m in (cost,cards,independent,results,audit,paths,fix_replay,obligation_fix)})
    for name in ('research196_cost_sections.py','research196_results.py','research194_report.py'):
        source=ROOT/'scripts'/name;bindings[str(source.resolve())]=file_hash(source)
    bindings[str(Path(__file__).resolve())]=file_hash(__file__)
    dump(out/'protocol.json',dict(model_calls=0,source_bindings=bindings,
        order=['parser_replay','cost_and_cards_selection','freeze','independent_acceptance','cost_evaluation','report','audit']))
    steps=[('parser_replay',lambda:fix_replay.run(execution,d/'research198_composition_fix_20261104_r01/replay.json')),
        ('cost_registration',lambda:cost.register(prepared,execution,costout)),
        ('card_selection',lambda:cards.select(prepared,execution,cardout)),
        ('independent_acceptance',lambda:independent.run(prepared,execution,acceptance)),
        ('cost_evaluation',lambda:cost.runtime().evaluate(costout,acceptance/'native')),
        ('cost_analysis',lambda:cost.runtime().analyze(costout)),
        ('attach_cards',lambda:cards.attach(cardout,acceptance/'native')),
        ('build_report',lambda:results.build(prepared,execution,acceptance/'native',costout,cardout,report)),
        ('final_audit',lambda:audit.run(prepared,execution,acceptance,costout,cardout,report,out))]
    completed=[]
    for name,fn in steps:
        started=time.monotonic();fn();completed.append(dict(phase=name,seconds=time.monotonic()-started))
        dump(out/'progress.json',completed);print('LOCAL_PHASE_DONE',name,flush=True)
    dump(out/'outcome.json',dict(status='registered_experiment_and_delivery_complete',model_calls=0,phases=completed,
        report=str(report/'report.html'),interpretation='See actual fallback coverage, unknown and negative outcomes; no superiority inferred from completion.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
