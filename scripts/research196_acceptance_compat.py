"""Post-freeze adapter repair; original sealed sources remain byte-identical.

The private research194_cases clone does not inherit Ibex's dynamic registration.
Copy only the missing registered Ibex config/fault registry before the sealed
R196 adapter replaces the independent fault. No query or fault definition edits.
"""
import copy
from pathlib import Path
import research196_independent as sealed


def install():
    if getattr(sealed, '_r196_registration_compat', False):
        return
    original_clone = sealed.clone
    def clone(name):
        module = original_clone(name)
        if name == 'research194_cases':
            registered = sealed.ibex.register()
            for field in ('CONFIG', 'FAULTS'):
                target = getattr(module, field)
                if 'ibex_flush' in target:
                    raise ValueError('unexpected_existing_private_ibex_registration')
                target['ibex_flush'] = copy.deepcopy(getattr(registered, field)['ibex_flush'])
        if name == 'research194_independent':
            module.SOURCE_NAMES = (*module.SOURCE_NAMES, Path(__file__).name)
        return module
    sealed.clone = clone
    sealed._r196_registration_compat = True


def check(registration):
    install()
    registered = sealed.ibex.register()
    before = copy.deepcopy(registered.FAULTS)
    adapter = sealed.runtime(registration).cases
    assert registered.FAULTS == before
    assert adapter.CONFIG['ibex_flush'] == registered.CONFIG['ibex_flush']
    for cid, definition in sealed.NEW_FAULTS.items():
        independent = [f for f in adapter.FAULTS[cid] if f['split'] == 'independent']
        assert independent == [dict(definition, split='independent')]
    return dict(status='passed', definitions_unchanged=True,
                shared_registry_unchanged=True, inputs_constructed=False, native_jobs=0)
