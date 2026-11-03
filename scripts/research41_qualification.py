"""New schema/renderer/feedback qualification; no synthetic model successes."""
import argparse
import copy
import json
from pathlib import Path

import research17_loop as loop
import research41_fresh_campaign as campaign
import research39_ast_refinement as old
from research34_campaign import snapshot,digest


def run(out):
    loop.prepare(out);snapshot(out)
    initial=loop.read(campaign.runner.PREP/'shared_initial.json')
    plan=loop.read(campaign.runner.OLD/'plan/v1/model_call/applicability_plan.json')
    checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    # Archived output is only a parser qualification control. It must never
    # become a fresh model result or be included in this campaign's requests.
    archived=loop.read(campaign.interface.SOURCE/'model_edit.json')
    candidate=campaign.assemble(archived,initial)
    check('exact_existing_native_qualified_candidate',candidate==loop.read(campaign.PROTECTED/'candidate.json'))
    import jsonschema
    jsonschema.Draft202012Validator.check_schema(campaign.schema(initial))
    jsonschema.validate(archived,campaign.schema(initial))
    check('expanded_schema_matches_actual_renderer',True)
    try: old.assemble(archived,initial)
    except Exception: check('old_rejection_unchanged',True)
    else: raise AssertionError('old interface unexpectedly accepts')
    def invalid(name,change):
        value=copy.deepcopy(archived);change(value)
        try: campaign.assemble(value,initial)
        except Exception: check(name,True)
        else: raise AssertionError('invalid edit accepted:'+name)
    invalid('keep_rejected',lambda v:v.update(operation='keep'))
    invalid('wrong_slot_rejected',lambda v:v.update(assertion_id='a0'))
    invalid('changed_obligation_rejected',lambda v:v['assertions'][0].update(obligation=['order_payload']))
    invalid('clock_not_property_signal',lambda v:v['assertions'][0].update(antecedent={'signal':'clk'}))
    invalid('nonlogical_variadic_rejected',lambda v:v['assertions'][0].update(antecedent={'op':'==','args':[{'int':1}]*3}))
    invalid('embedded_temporal_arrow_rejected',lambda v:v['assertions'][0].update(antecedent={'op':'|=>','args':[{'signal':'mvalid'}]*2}))
    diagnostic=campaign.runner.complete_feedback(
        loop.read(campaign.runner.OLD/'core/v1/target_native/result.json'),
        loop.read(campaign.runner.OLD/'core/v1/decision.json'),loop.read(campaign.runner.OLD/'core/v1/model_call/result.json'))
    config=loop.read(campaign.runner.PREP/'model_config.json')
    request=campaign.payload(initial,diagnostic,plan,config)
    body=json.loads(request['messages'][1]['content'])
    check('declared_rst_consistent','rst' in body['rtl_and_common_contract']['allowed_property_signals'] and
          'rst' in body['expression_interface']['allowed_signals'])
    check('shared_rtl_retained',body['rtl_and_common_contract']['rtl_shared']==json.loads(old.payload(initial,diagnostic,plan,config)['messages'][1]['content'])['rtl_and_common_contract']['rtl_shared'])
    check('same_verified_plan',body['actual_verified_plan']==plan)
    check('eight_actual_gap_cards_retained',len(body['obligation']['contrasts'])==8)
    check('no_successful_ast_in_prompt',json.dumps(archived) not in json.dumps(request))
    check('no_research40_artifact_reference_in_prompt','research40' not in json.dumps(request))
    check('no_independent_rows_field','boundary_cases' not in json.dumps(request) and 'drain_cases' not in json.dumps(request))
    previous_call=loop.read(campaign.interface.SOURCE/'result.json')
    feedback=campaign.feedback(None,dict(accepted=False,reasons=[dict(kind='model_output_unusable')]),previous_call,diagnostic)
    check('interface_error_kept',feedback['interface_diagnostic']['candidate_error']==previous_call['candidate_error'])
    check('history_preserved_if_interface_fails',feedback['prior_native_development_diagnostics']==diagnostic)
    # The holdout extension must remain the same function as the experiment
    # uses; no materialization of new independent input during qualification.
    check('protected_freeze_present',(campaign.PROTECTED/'core/freeze.json').is_file())
    loop.dump(out/'verification.json',dict(passed=True,checks=checks,count=len(checks),model_calls=0,
        new_native_calls=0,reused_native_qualification=str(campaign.PROTECTED/'interface_qualification/result.json'),
        reused_native_hash=digest(campaign.PROTECTED/'interface_qualification/result.json'),
        scope='Real archived AST parser qualification and development request isolation only. Not fresh generation, not a new successful repair.'))
    print('FRESH_INTERFACE_QUALIFICATION',len(checks),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert loop.ROOT in a.out.resolve().parents;run(a.out.resolve())
