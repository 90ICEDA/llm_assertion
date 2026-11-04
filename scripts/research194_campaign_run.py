"""Run sealed packages only after new explicit authorization; then freeze/test.

The two authorization files must refer to the actual new user approval. Merely
running this entry point never grants permission or expands a previous budget.
"""
import argparse
from pathlib import Path
import research194_refinement_prepare as main
import research194_refinement_runner as runner
import research194_augmentation as augmentation
import research194_independent as acceptance
import research194_report as report
import research194_cost_audit as audit
import research194_case_cards as cards


def run(args):
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    ma,ms=runner.verify_package(args.main_prepared)
    au,asu=runner.verify_package(args.augmentation_prepared)
    approved=[]
    for path,protocol,seal in ((args.main_authorization,ma,ms),(args.augmentation_authorization,au,asu)):
        auth=runner.read(path)
        if auth.get('approved') is not True or auth.get('version')!='research194' or auth.get('protocol_sha256')!=seal or auth.get('endpoint')!=runner.ENDPOINT or not auth.get('user_message_reference'):
            raise ValueError('new_actual_user_approval_required')
        approved.append(min(auth['maximum_model_calls'],protocol['maximum_model_calls']))
    if sum(approved)>219:raise ValueError('campaign_call_ceiling')
    registered=runner.read(acceptance.REGISTRATION)
    for path,sha in registered['source_bindings'].items():
        if runner.file_hash(path)!=sha:raise ValueError('registered_acceptance_source_changed')
    runner.dump(out/'protocol.json',dict(main_seal=ms,augmentation_seal=asu,maximum_model_calls=sum(approved),
        workers=2,no_retries=True,no_independent_access_before_all_80_frozen=True,
        authorization_files=[str(args.main_authorization),str(args.augmentation_authorization)]))
    main_out=out/'base';aug_out=out/'augmentation';independent_out=out/'independent'
    try:
        main.execute(args.main_prepared,main_out,args.main_authorization,workers=2)
        augmentation.execute(args.augmentation_prepared,aug_out,args.augmentation_authorization,workers=2)
        acceptance.collect(main_out,aug_out,out/'entries.json')
        acceptance.freeze(runner.read(out/'entries.json'),80,out/'frozen_versions.json')
        acceptance.execute(out/'frozen_versions.json',independent_out)
        status='completed'
    except Exception as exc:
        runner.dump(out/'interruption.json',dict(error_type=type(exc).__name__,error=str(exc),
            automatic_retry=False,instruction='Preserve paid attempts. Missing or unknown trajectories are not replaced by successful new ones.'))
        status='incomplete_exception'
        raise
    finally:
        cards.build(main_out,independent_out,args.report/'case_cards')
        report.build(args.report,args.search,main_out,aug_out,args.fault,independent_out)
        audit.run(args.report)
        runner.dump(out/'outcome.json',dict(status=locals().get('status','incomplete'),
            independent_completed=runner.read(independent_out/'outcome.json').get('status')=='completed' if (independent_out/'outcome.json').exists() else False))


if __name__=='__main__':
    p=argparse.ArgumentParser();d=runner.ROOT/'deliverables'
    p.add_argument('--main-prepared',type=Path,default=d/'research194_refinement_prepare_20261103_r01')
    p.add_argument('--augmentation-prepared',type=Path,default=d/'research194_augmentation_prepare_20261103_r01')
    p.add_argument('--main-authorization',type=Path,required=True);p.add_argument('--augmentation-authorization',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--report',type=Path,default=d/'reguard_mechanisms_20261103_r02')
    p.add_argument('--search',type=Path,default=d/'research194_active_native_20261103_r02')
    p.add_argument('--fault',type=Path,default=d/'research194_fault_regrade_20261103_r01')
    run(p.parse_args())
