"""Frontend correction: admit the declared scalar reset in expressions.

The old interface excluded reset even though the executor exposes it and disables
checks while reset is low. Replay the last ACTUAL model proposal verbatim in a
separate diagnostic block. Do not reconstruct or replace the four-arm trajectory.
"""
import argparse
import copy
import json
import re
from pathlib import Path
import obligation_isolated_search as iso
from obligation_isolated_search import x

BASE_NORMALIZE=x.checker.normalize


def normalize(c,d,depth=0,param=None):
    # Scalar reset is public. Invented historical reset registers are not.
    for key in ('antecedent','consequent'):
        assert not re.search(r'\bp[123]_'+re.escape(d['rst'])+r'\b',c[key]),'unsupported:reset_history'
    metadata=copy.deepcopy(d)
    metadata['observation_base']=list(dict.fromkeys([*d['observation_base'],d['rst']]))
    metadata['inputs']={**d['inputs'],d['rst']:1}
    return BASE_NORMALIZE(c,metadata,depth,param)


def main(run):
    x.OUT=x.ROOT/'deliverables'/run;out=x.OUT/'reset_identifier_diagnostic';out.mkdir(exist_ok=False)
    block=x.OUT/'refinement_r04';assert (block/'final_freeze.json').exists()
    files=list(block.glob('models/*/*/1/response.raw.json'))
    x.dump(out/'freeze.json',{x.rel(p):x.sha(p) for p in [Path(__file__),*files]})
    x.dump(out/'protocol.json',dict(scope='post-freeze frontend diagnosis only; not a new or rerun model repair comparison',
        change='admit declared scalar reset, keep forbidden identifiers/history/operator restrictions; implicit reset still disables checks',
        candidates='last actual response per case/arm, no textual edits; initial/final main experiment records untouched',
        evaluations='two already-public common development schedules per available proposal; no new hidden inputs',model_calls=0))
    x.checker.normalize=normalize;iso.configure()
    results=[]
    for k in ('filter','fifo','stat'):
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        # The implementation-level permission check is independent of any model.
        normalize(dict(antecedent=d['rst'],consequent='1',delay=0),d)
        for arm in ('A','B','C','D'):
            folder=block/'models'/k/arm/'1';old=x.read(folder/'result.json')
            result=dict(case=k,arm=arm,original_status=old['status'],original_error=old.get('error'),queries=[])
            try:
                parsed=json.loads(x.read(folder/'response.raw.json')['message']['content'])['assertions']
                assert 1<=len(parsed)<=4
                cs=[]
                for j,c in enumerate(parsed):
                    normalize(c,d,3)
                    cs.append(dict(antecedent=c['antecedent'],consequent=c['consequent'],delay=c['delay'],
                        id=f'raw_{k}_{arm}_{j}',provenance='verbatim_actual_model_proposal_frontend_diagnostic',authorized_history_depth=3))
                result['unaltered_ast_sha256']=x.digest([{n:c[n] for n in ('antecedent','consequent','delay')} for c in cs])
                result['raw_model_response']=x.rel(folder/'response.raw.json')
                for i,rows in enumerate(x.read(block/'common'/f'{k}.json')):
                    q=iso.evaluate(d,rows,cs,f'reset_identifier_diagnostic/{k}/{arm}/{i}')
                    x.append(out/'queries.jsonl',dict(case=k,arm=arm,scenario=i,**q))
                    result['queries'].append(dict(status=q['status'],runs=q['runs'],evidence=q['evidence']))
                result['status']='executable' if all(q['status']=='ok' for q in result['queries']) else 'execution_unknown'
            except (AssertionError,KeyError,ValueError,FileNotFoundError) as exc:
                result.update(status='still_unsupported',error=repr(exc))
            results.append(result)
    x.dump(out/'results.json',results)
    x.dump(out/'summary.json',dict(proposals=len(results),originally_parsed=sum(r['original_status']=='parsed' for r in results),
        now_executable=sum(r['status']=='executable' for r in results),
        instruction='Do not attribute these frontend-recovered proposals to the old main trajectory; a future full four-arm block would be needed to compare repaired feedback loops.',
        outcome='Even executable proposals need independent semantic acceptance; no parent pass implied.'))
    print(json.dumps(x.read(out/'summary.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
