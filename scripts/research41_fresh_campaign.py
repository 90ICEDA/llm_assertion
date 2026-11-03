"""Fixed new-interface fresh generation, then three seed replications.

Maximum eight newly authorized real calls: pilot <=2; three seeds <=2 each.
No archived proposal injection. research40 holdout stays excluded, not training.
After pilot success, all replication versions freeze before a common fresh test.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil

import research17_loop as loop
import research17_model_schema as grammar
import research38_history_feedback as runner
import research39_ast_refinement as legacy
import research40_interface_continuation as interface
import research32_runtime as extension
from research34_campaign import snapshot,digest
from research35_campaign import holdout
from research17_report import artifacts,cost_audit

read,dump=loop.read,loop.dump
PILOT=4103
REPLICATIONS=(4111,4127,4133)
FORMAT='recursive_ast_reset_variadic_v1'
PROTECTED=loop.ROOT/'deliverables/research40_interface_continuation_20261022_r01'


def schema(current):
    value=legacy.schema(current)
    branches=value['$defs']['expression']['anyOf']
    branches[0]['properties']['signal']['enum'].append('rst')
    # Explicitly distinguish variadic logical ops from all binary arithmetic /
    # comparisons. The model still chooses every predicate and sample relation.
    binary=branches.pop()
    binary['properties']['op']['enum']=[op for op in grammar.BINARY if op not in ('&&','||')]
    logical=copy.deepcopy(binary)
    logical['properties']['op']['enum']=['&&','||']
    logical['properties']['args']['minItems']=2
    logical['properties']['args']['maxItems']=8
    branches.extend([binary,logical])
    return value


def assemble(value,current):
    # Top-level constraints match the advertised schema; renderer is the exact
    # interface already exercised in research40, without predicate correction.
    assert type(value) is dict and set(value)=={'operation','assertion_id','assertions','reason'},'edit_fields'
    assert value['operation']=='replace_one','replacement_required'
    assert value['assertion_id'] in schema(current)['properties']['assertion_id']['enum'],'target_slot'
    assert type(value['reason']) is str and len(value['reason'])<=128,'reason_length'
    assert type(value['assertions']) is list and len(value['assertions'])==1,'one_assertion'
    return interface.assemble(value,current)


def render_edit(value,current):
    assemble(value,current)
    rendered=copy.deepcopy(value)
    for side in ('antecedent','consequent'):
        rendered['assertions'][0][side]=interface.expression(value['assertions'][0][side])
    return rendered


def payload(current,diagnostic,plan,settings):
    result=legacy.payload(current,diagnostic,plan,settings)
    body=json.loads(result['messages'][1]['content'])
    body['output_schema']=schema(current)
    common=body['rtl_and_common_contract']
    common['allowed_property_signals']=list(grammar.SIGNALS)+['rst']
    common['signals']['rst']='Active-high reset sampled in expressions; disable iff(rst) remains supplied by the native wrapper.'
    common['syntax']='Use the supplied Boolean AST schema. Explicit rst operands are allowed; clk stays wrapper-only. &&/|| take 2..8 operands, other binary operators exactly 2. Temporal implication is selected only through timing.'
    body['expression_interface'].update(kind=FORMAT,allowed_signals=list(grammar.SIGNALS)+['rst'],
        reset='rst is allowed as an explicit Boolean operand. The harness still supplies posedge clk and disable iff(rst); no operand is removed.',
        instructions='Choose every AST leaf, operator and timing. && and || allow 2..8 args; other binary operators require exactly 2; unary operators require exactly 1. Native rendering preserves all supplied operands in order. No raw strings, no SVA arrows inside operands.')
    body['validation']+=' This interface and all native/history gates are fixed before the first call and will not change during the campaign.'
    result['messages'][1]['content']=json.dumps(body)
    return result


feedback=legacy.feedback


class Model(runner.Model):
    def __init__(self,out,settings,plan):
        super().__init__(out,settings,plan)
        self.assemble=assemble
        dump(self.out/'model_schema.json',schema(read(runner.PREP/'shared_initial.json')))

    def _payload(self,current,target,diagnostic,phase):
        return payload(current,diagnostic,self.plan,self.config)

    def save_decoded_output(self,folder,value,current,secret):
        dump(folder/'rendered_edit.json',render_edit(value,current))
        return super().save_decoded_output(folder,value,current,secret)


def split_hashes(split):
    return {loop.sha(c['rows']) for c in split['boundary_cases']+split['drain_cases']}


def protected_manifest():
    return {p.relative_to(PROTECTED).as_posix():digest(p) for p in (
        PROTECTED/'core/frozen_candidate.json',PROTECTED/'core/freeze.json',
        PROTECTED/'independent/split.json',PROTECTED/'independent/summary.json')}


def prepare(out):
    loop.prepare(out);snapshot(out)
    # Use only research36-era development input, NOT the successful research40
    # AST/SVA, test samples, results, or any newly created test outcome.
    for seed in (PILOT,*REPLICATIONS):
        child=out/f's{seed}'
        runner.prepare(child)
        config=read(child/'model_config.json')
        config.update(expression_format=FORMAT,direct_property=False)
        config['options'].update(seed=seed,temperature=0.2)
        initial=read(child/'shared_initial.json')
        diagnostic=runner.complete_feedback(
            read(runner.OLD/'core/v1/target_native/result.json'),
            read(runner.OLD/'core/v1/decision.json'),read(runner.OLD/'core/v1/model_call/result.json'))
        # Do not send obsolete unknown:rst errors from the previous interface.
        dump(child/'development_diagnostics.json',diagnostic)
        dump(child/'model_config.json',config)
        dump(child/'model_schema.json',schema(initial))
        dump(child/'request.preview.json',payload(initial,diagnostic,read(child/'verified_plan.json'),config))
        protocol=read(child/'protocol.json')
        protocol.update(expression_format=FORMAT,feedback_version=4,
            seed=seed,temperature=0.2,evaluate_retained_versions=seed!=PILOT,
            full_history_feedback=True,
            budget='Two fresh calls maximum, authorized through parent campaign; no retries, stop on acceptance.',
            generation='Every candidate comes from this child run real response. No archived candidate injection or run-time interface adjustment.',
            independent='Pilot fresh batch excludes research40; replication batch generated only after all three freeze, shared for all retained/accepted versions. No test feedback.',
            limits='Requested provider seeds and temperature recorded; provider seed reproducibility not guaranteed. Three replications do not establish general stability.')
        dump(child/'protocol.json',protocol)
        dump(child/'prepared_hashes.json',{p.relative_to(child).as_posix():digest(p)
            for p in child.glob('*.json') if p.name!='prepared_hashes.json'})
    previews=[read(out/f's{s}/request.preview.json') for s in (PILOT,*REPLICATIONS)]
    assert all(r['messages']==previews[0]['messages'] for r in previews)
    initial_hashes={loop.sha(read(out/f's{s}/shared_initial.json')) for s in (PILOT,*REPLICATIONS)}
    assert len(initial_hashes)==1
    dump(out/'protocol.json',dict(maximum_calls=8,maximum_per_seed=2,pilot=PILOT,replications=list(REPLICATIONS),
        endpoint=config['remote_url'],model=config['remote_model'],
        order='Pilot must accept and pass its fresh five-obligation test; otherwise halt. Then three replications without adaptation, freeze all, common fresh test including rejected retained candidates.',
        requested_temperature=0.2,transport_retries=0,initial_hash=next(iter(initial_hashes)),
        research40='Frozen candidate and independent results preserved; used only for input-overlap exclusion and integrity checks, never sent in prompts.',
        stage2_denominator=3,pilot_not_in_stability_denominator=True))
    dump(out/'protected_research40.json',protected_manifest())
    dump(out/'qualification_reuse.json',dict(source=str(PROTECTED/'interface_qualification/result.json'),
        sha256=digest(PROTECTED/'interface_qualification/result.json'),new_native_calls=0,
        scope='Reuse actual research40 rst/variadic native qualification; not fresh model generation or new end-to-end success.'))
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():digest(p) for p in out.glob('*.json') if p.name!='prepared_hashes.json'})
    print('PREPARED fresh pilot plus three seeds; real model calls=0',flush=True)


def run(prep,out,auth_path):
    auth=read(auth_path);protocol=read(prep/'protocol.json')
    assert auth['authorized_calls']==8 and auth['run_output']==out.relative_to(loop.ROOT).as_posix()
    assert auth['endpoint']==protocol['endpoint'] and auth['model']==protocol['model']
    for name,h in read(prep/'prepared_hashes.json').items(): assert digest(prep/name)==h,name
    for name,h in read(prep/'source_snapshot/hashes.json').items(): assert digest(loop.ROOT/'scripts'/name)==h,name
    assert protected_manifest()==read(prep/'protected_research40.json')
    loop.prepare(out);snapshot(out)
    shutil.copy2(auth_path,out/'authorization.json')
    dump(out/'prepared_source.json',dict(path=str(prep)))
    dump(out/'protocol.json',protocol)
    excluded=split_hashes(read(PROTECTED/'independent/split.json'))
    stage='pilot_not_started'
    try:
        for seed in (PILOT,*REPLICATIONS):
            child=out/f's{seed}';child_prep=prep/f's{seed}'
            delegated=dict(authorized_calls=2,endpoint=auth['endpoint'],model=auth['model'],
                run_output=child.relative_to(loop.ROOT).as_posix(),parent_authorization=str(out/'authorization.json'),
                parent_maximum_calls=8,seed=seed,transport_retries=0)
            authorization=out/'allocations'/f's{seed}.json';dump(authorization,delegated)
            def independent_policy(folder,candidate,development):
                if seed!=PILOT: return False
                holdout(folder,candidate,development,extra_exposed_hashes=excluded)
                return True
            runner.run(child_prep,child,authorization,Model,feedback,
                       holdout_fn=independent_policy,history_feedback=True)
            outcome=read(child/'outcome.json')
            if seed==PILOT:
                if not outcome['accepted']:
                    stage='pilot_refinement_rejected';return
                if not read(child/'independent/summary.json')['all_five_pass_on_first_attributed_evidence']:
                    stage='pilot_independent_failed_no_adaptation';return
                excluded.update(split_hashes(read(child/'independent/split.json')))
                stage='pilot_complete_replications_running'
        stage='all_replication_versions_frozen'
        dump(out/'replication_freezes.json',{str(s):read(out/f's{s}/core/freeze.json') for s in REPLICATIONS})
        common=None
        with extension.installed():
            for seed in REPLICATIONS:
                child=out/f's{seed}'
                holdout(child,read(child/'core/frozen_candidate.json'),read(prep/f's{seed}/full_cases.json'),
                        extra_exposed_hashes=excluded,fixed_split=common)
                if common is None:
                    common=read(child/'independent/split.json')
                    dump(out/'common_independent_split.json',common)
                outcome=read(child/'outcome.json')
                outcome['status']='accepted_and_independent_completed' if outcome['accepted'] else 'retained_rejected_version_independent_completed'
                dump(child/'outcome.json',outcome)
                dump(child/'cost.json',cost_audit(child,artifacts(child)))
        stage='pilot_and_three_seed_replications_completed'
    except BaseException:
        stage='campaign_execution_exception'
        raise
    finally:
        assert protected_manifest()==read(prep/'protected_research40.json'),'research40_changed'
        outcomes={str(s):read(out/f's{s}/outcome.json') for s in (PILOT,*REPLICATIONS) if (out/f's{s}/outcome.json').exists()}
        actual=sum(c['calls'] for c in outcomes.values())
        assert actual<=8
        dump(out/'outcome.json',dict(status=stage,seed_outcomes=outcomes,calls=actual,maximum_calls=8,
             research40_preserved=True,replication_denominator=3))
        dump(out/'cost.json',cost_audit(out,artifacts(out)))
        print('CAMPAIGN',stage,'calls',actual,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    if a.action=='prepare':prepare(out)
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
