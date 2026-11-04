"""Compare parsers on actual archived composition responses; no model/native calls."""
import argparse
import copy
import json
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research198_refinement import runtime as old_runtime
from research198_active_obligation_fix import runtime as fixed_runtime
import research197_cases as cases

def controller(factory,policy,context,cid):
    core,_=factory(policy);cfg=cases.get_case(cid)
    c=core.Controller(cfg['initial'],'R3',cfg['obligations'],max_rounds=5)
    c.active=copy.deepcopy(context['current_assertions']);c.history=copy.deepcopy(context['earlier_rounds'])
    c.rounds=context['round'];c.stage='compose';receipt=copy.deepcopy(context['fallback_receipt'])
    if receipt.get('kind')=='local_domain_empty':
        for k in ('editable_fields','immutable_fields'):receipt[k]=tuple(receipt[k])
        c.receipt=core.LocalDomainEmptyReceipt(**receipt)
    else:c.receipt=core.FailureReceipt(**receipt)
    return core,c

def run(execution,out):
    execution=Path(execution);out=Path(out)
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('freeze_before_complete_replay')
    rows=[]
    for path in sorted(execution.glob('*/*/*/refinement/round*/model_edit.json')):
        request=read(path.parent/'request.preview.json');context=json.loads(request['messages'][-1]['content'])
        schema=context['output_contract']['schema']
        if not isinstance(schema.get('edits'),list) or schema['edits'][0].get('op')!='add_assertion':continue
        parts=path.relative_to(execution).parts;cid=parts[0];policy='local_first' if parts[2].endswith('local_first') else 'legacy'
        response=read(path);outcomes={}
        for name,factory in (('original',old_runtime),('retained_candidate_fix',fixed_runtime)):
            core,c=controller(factory,policy,context,cid)
            try:
                proposal,_=c.parse(response,context['development_observations'],lambda v:cases.validate(cid,v))
                outcomes[name]=dict(status='parsed',candidate_sha256=core.digest(proposal))
            except (ValueError,TypeError,KeyError) as exc:
                outcomes[name]=dict(status='rejected',error=str(exc))
        rows.append(dict(id='/'.join(parts[:3]),round=parts[4],request_sha256=file_hash(path.parent/'request.preview.json'),
            response_sha256=file_hash(path),outcomes=outcomes,behavior_changed=outcomes['original']!=outcomes['retained_candidate_fix']))
    result=dict(scope='Archived parser replay only; no fresh model results, no native candidate acceptance and no independent grades.',
        model_calls=0,native_jobs=0,composition_responses=len(rows),changed_responses=sum(r['behavior_changed'] for r in rows),rows=rows,
        source_bindings={str(Path(p).resolve()):file_hash(p) for p in (__file__,Path(__file__).with_name('research198_active_obligation_fix.py'))},
        interpretation='The synthetic regression proves a rejected proposal cannot erase the retained candidate gap. Actual response behavior is audited separately; other invalid additions remain rejected.')
    dump(out,result);print({k:v for k,v in result.items() if k not in ('rows','source_bindings')},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.execution,a.out)
