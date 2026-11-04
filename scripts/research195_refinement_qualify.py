"""Native, handwritten typed-operation qualification. Zero model calls."""
import argparse
import copy
from pathlib import Path
from research195_refinement_adapter import runtime
from research195_refinement_fixtures import fixtures,FixtureAdapter
from research194_refinement_safe_localization import safe_localize


def run(out,names):
    core,runner=runtime('L');out=Path(out);out.mkdir(parents=True,exist_ok=False)
    registry=fixtures();runner.dump(out/'preregistration.json',dict(fixtures={k:registry[k] for k in names},
        provenance='handwritten controls only; zero model calls; fixed before native outcomes'))
    results=[]
    for name in names:
        adapter=FixtureAdapter(name);fixture=registry[name];folder=out/name
        before=adapter.evaluate(fixture['initial'],folder/'before',fixture['queries'])
        evidence=runner.model_evidence(before);audit=safe_localize(fixture['initial'],evidence)
        controller=runner.controller_from(adapter,'R3',before,max_rounds=1)
        response=dict(edits=[fixture['edit']],reason='Preregistered handwritten typed-operation qualification, not model output.')
        runner.dump(folder/'safe_localization.json',audit);runner.dump(folder/'handwritten_response.json',response)
        runner.dump(folder/'request.preview.json',core.build_request(adapter.case,controller,evidence,19507,0))
        row=dict(fixture=name,model_calls=0,operator=fixture['edit']['op'],interpretation=fixture['interpretation'],
            before=dict(targets=len(before['targets']),detected=len(before['transaction_detected_ids']),fp=len(before['false_positives']),unknown=len(before['critical_unknown'])))
        try:
            candidate,edits=controller.parse(response,evidence,adapter.validate)
            runner.dump(folder/'proposal.json',candidate);runner.dump(folder/'edits.json',edits)
            after=adapter.evaluate(candidate,folder/'after',fixture['queries'])
            entry=controller.observe(candidate,after,current_targets=before['targets'],edit_record=edits,baseline=before)
            row.update(status='native_measured',decision=entry['decision'],after=dict(targets=len(after['targets']),
                detected=len(after['transaction_detected_ids']),fp=len(after['false_positives']),unknown=len(after['critical_unknown'])))
        except (ValueError,TypeError,KeyError) as exc:
            row.update(status='qualification_failed',error_type=type(exc).__name__,error=str(exc))
        runner.dump(folder/'frozen.json',controller.active);runner.dump(folder/'result.json',row)
        results.append(row);runner.dump(out/'results.json',results)
        print(dict(fixture=name,status=row['status'],accepted=row.get('decision',{}).get('accepted'),before=row['before'],after=row.get('after')),flush=True)
    runner.dump(out/'outcome.json',dict(status='completed',model_calls=0,fixtures=len(results)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--fixtures',nargs='+',default=['delay','window','single_inflight_match','exception'])
    args=p.parse_args();run(args.out,args.fixtures)
