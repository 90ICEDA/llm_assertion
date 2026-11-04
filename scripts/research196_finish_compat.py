"""Resume local postprocessing after recorded pre-input adapter failure."""
import argparse
from pathlib import Path
import time
from research194_refinement_runner import ROOT, read, dump, file_hash
from research196_acceptance_compat import install, check


def run(prepared, execution, out):
    prepared, execution, out = map(Path, (prepared, execution, out))
    previous = ROOT/'deliverables/research196_finish_20261104_r01'
    if read(previous/'status.json')['phase'] != 'independent_acceptance':
        raise ValueError('unexpected_previous_failure_phase')
    base = ROOT/'deliverables'
    ind = base/'research196_independent_20261104_r01'
    if ind.exists():
        raise ValueError('acceptance_already_started')
    out.mkdir(parents=True, exist_ok=False)
    proof = check(prepared/'acceptance_registration.json')
    scripts = ['research196_acceptance_compat.py', 'research196_finish_compat.py',
               'research196_cost_sections.py', 'research196_cards.py', 'research196_results.py']
    dump(out/'protocol.json', dict(model_calls=0, previous_failure=str(previous),
         repair='Copy missing registered Ibex metadata into private case clone; no query/fault/candidate changes.',
         qualification=proof, source_bindings={str(ROOT/'scripts'/s):file_hash(ROOT/'scripts'/s) for s in scripts}))
    install()
    import research196_independent as independent
    import research196_cost_sections as cost
    import research196_cards as cards
    import research196_results as results
    costout = base/'research196_cost_sections_20261104_r01'
    cardout = base/'research196_case_cards_20261104_r01'
    report = base/'reguard_mechanisms_20261104_r05'
    phases = [('independent_acceptance', lambda: independent.run(prepared, execution, ind)),
              ('evaluate_cost_checkpoints', lambda: cost.evaluate(costout, ind/'native')),
              ('analyze_cost', lambda: cost.analyze(costout)),
              ('attach_cards', lambda: cards.attach(cardout, ind/'native')),
              ('report', lambda: results.build(prepared, execution, ind/'native', costout, report))]
    completed = []
    for name, action in phases:
        dump(out/'status.json', dict(status='running', phase=name, completed=completed, model_calls=0))
        print('PHASE', name, flush=True)
        start = time.monotonic()
        try:
            action()
        except Exception as exc:
            dump(out/'status.json', dict(status='failed', phase=name, error=repr(exc), completed=completed, model_calls=0))
            raise
        completed.append(dict(phase=name, wall_seconds=time.monotonic()-start))
    dump(out/'status.json', dict(status='local_phases_completed', completed=completed, model_calls=0,
                                windows_plot_render_pending=True, final_audit_pending=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for key in ('prepared', 'execution', 'out'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    run(args.prepared, args.execution, args.out)
