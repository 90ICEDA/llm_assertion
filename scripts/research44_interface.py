"""Prospective metadata-tolerant AST interface and unchanged-response replay.

No remote calls. Research43 results remain immutable. Reason is saved verbatim;
only executable structure, signal, arity, slot and obligation rules gate parsing.
"""
import argparse
import copy
import json
from pathlib import Path
import research17_loop as loop
import research17_model as base
import research40_interface_continuation as ast_interface
import research43_paired_ablation as old
import research32_runtime as extension
from research35_campaign import join_results
from research17_report import cost_audit
from research28_report import raw_response

read, dump = loop.read, loop.dump
ROOT = loop.ROOT
SOURCE = ROOT/'deliverables/research43_real_20261022_r01'
PREP = ROOT/'deliverables/research43_prepare_20261022_r02'


def schema(current):
    value = old.schema(current)
    value['properties']['reason'].pop('maxLength', None)
    value['properties']['reason']['description'] = 'Explanation metadata saved verbatim, never interpreted as an executable predicate. Keep concise to leave output budget for the AST.'
    return value


def assemble(value, current):
    assert type(value) is dict and set(value) == {'operation','assertion_id','assertions','reason'}, 'edit_fields'
    assert type(value['reason']) is str, 'reason_must_be_string'
    assert value['operation'] in ('keep','replace_one'), 'operation'
    if value['operation'] == 'keep':
        assert value['assertion_id'] == '' and value['assertions'] == [], 'keep_must_be_empty'
        return copy.deepcopy(current)
    assert value['assertion_id'] in schema(current)['properties']['assertion_id']['enum'][1:], 'target_slot'
    assert type(value['assertions']) is list and len(value['assertions']) == 1, 'one_assertion'
    return ast_interface.assemble(value, current)


def rendered(value):
    result = copy.deepcopy(value)
    if value['operation'] == 'replace_one':
        for side in ('antecedent','consequent'):
            result['assertions'][0][side] = ast_interface.expression(value['assertions'][0][side])
    return result


def executable_hash(candidate):
    # Exact rendered property strings, independent of explanatory metadata.
    return loop.sha([dict(id=a['id'], property=a['property'], obligations=a['obligations']) for a in candidate['assertions']])


def qualify(out):
    loop.prepare(out)
    initial = read(PREP/'shared_initial.json')
    old_files = [p for p in old.files(SOURCE) if p.suffix == '.json' and
                 (p.name in ('outcome.json','pair_result.json','model_edit.json','result.json','freeze.json','summary.json'))]
    protected = {str(p):old.digest(p) for p in old_files}
    checks = []
    def check(name, passed):
        checks.append(dict(name=name, passed=bool(passed)))
        assert passed, name
    check('schema_reason_unbounded_metadata', 'maxLength' not in schema(initial)['properties']['reason'])
    keep = dict(operation='keep', assertion_id='', assertions=[], reason='x'*4096)
    check('long_metadata_preserved_keep', assemble(keep,initial) == initial)
    for name, value in (
        ('nonstring_reason', {**keep,'reason':[]}),
        ('bad_keep_slot', {**keep,'assertion_id':'a4'}),
        ('bad_keep_assertions', {**keep,'assertions':[{}]}),
        ('unknown_operation', {**keep,'operation':'magic'})):
        try: assemble(value,initial)
        except (AssertionError,ValueError,TypeError): check(name,True)
        else: check(name,False)
    example = read(SOURCE/'s4211/search/model_call/model_edit.json')
    for name, modify in (
        ('unknown_signal', lambda v: v['assertions'][0].update(antecedent={'signal':'not_a_port'})),
        ('bad_arity', lambda v: v['assertions'][0].update(antecedent={'op':'!','args':[]})),
        ('wrong_obligation', lambda v: v['assertions'][0].update(obligation=['order_payload']))):
        value = copy.deepcopy(example); modify(value)
        try: assemble(value,initial)
        except (AssertionError,ValueError,TypeError): check(name,True)
        else: check(name,False)
    records = []
    with extension.installed():
        for seed in (4201,4211,4217):
            for stream in ('ordinary','search'):
                source = SOURCE/f's{seed}'/stream/'model_call'
                dest = out/'core'/f's{seed}'/stream
                if not (source/'model_edit.json').exists():
                    records.append(dict(seed=seed,stream=stream,status='truncated_no_candidate',native_replay=False))
                    continue
                value = read(source/'model_edit.json')
                check(f'{seed}/{stream}:raw_response',raw_response(source,value))
                candidate = assemble(value,initial)
                dump(dest/'original_model_edit.json',value)
                dump(dest/'rendered_edit.json',rendered(value))
                dump(dest/'candidate.json',candidate)
                (dest/'candidate.sva').write_text(base.native.candidate_sva(candidate),encoding='utf-8')
                history = read(PREP/'history_cases.json')
                cases = [history[0]]
                before = read(PREP/'core/qualification/common/result.json')
                if stream == 'search':
                    cases += read(PREP/f's{seed}/acquired_cases.json')
                    before = join_results([before,read(PREP/f's{seed}/core/qualification/acquired/result.json')])
                after = loop.replay(candidate,dest/'native',cases)
                verdict = old.current_decision(before,after,value)
                dump(dest/'decision.json',verdict)
                check(f'{seed}/{stream}:native_healthy',after['healthy'])
                check(f'{seed}/{stream}:unchanged_original_ast',read(source/'model_edit.json') == read(dest/'original_model_edit.json'))
                check(f'{seed}/{stream}:native_expected_outcome', verdict['accepted'] == (stream=='ordinary'))
                records.append(dict(seed=seed,stream=stream,status='new_interface_native_replayed',
                    native_replay=True,source=str(source),source_sha256=old.digest(source/'model_edit.json'),
                    raw_reason_length=len(value['reason']),reason_saved_verbatim=True,
                    current_decision=verdict,counts=after['counts'],executable_hash=executable_hash(candidate),
                    replay=str(dest/'native/result.json'),edit=str(dest/'original_model_edit.json')))
                print('UNCHANGED_RESPONSE',seed,stream,'current_pass',verdict['accepted'],'misses',after['counts']['misses'],flush=True)
    check('prior_trial_unchanged',all(old.digest(Path(p))==h for p,h in protected.items()))
    dump(out/'qualification.json',dict(passed=all(c['passed'] for c in checks),checks=checks,
        records=records,model_calls=0,protected_source_hashes=protected,
        scope='New interface replay of exact historical real responses. No new generation, no changed research43 acceptance, no new independent test, ordinary current-pass is not a full-history acceptance.'))
    dump(out/'cost.json',cost_audit(out,old.files(out)))
    print('INTERFACE_QUALIFIED',len(checks),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert ROOT in a.out.resolve().parents
    qualify(a.out.resolve())
