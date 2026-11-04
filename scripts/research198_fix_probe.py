"""Read-only diagnosis of rejected-proposal coverage poisoning composition."""
import argparse
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump
from research194_refinement import digest

def run(execution,out):
    execution=Path(execution);rows=[]
    for path in sorted(execution.glob('*/*/*/refinement/rounds.json')):
        if not path.parent.parent.name.endswith('local_first'):continue
        for r in read(path):
            if r.get('error')!='addition_requires_uncovered_obligation':continue
            rd=path.parent/f"round{r['round']:02}";request=read(rd/'request.preview.json');context=json.loads(request['messages'][-1]['content'])
            current=read(rd/'current_measurement.json');history=context['earlier_rounds'];edit=read(rd/'model_edit.json')
            if not history or 'decision' not in history[-1] or history[-1]['decision']['accepted']:continue
            observed={e['obligation'] for e in context['development_observations'] if e['status']=='confirmed' and e['label']=='violation'}
            wrong=observed-set(history[-1]['decision']['covered_obligations'])
            correct=observed-set(current['covered_obligations'])
            additions={o for e in edit.get('edits',[]) if e.get('op')=='add_assertion' for o in e.get('assertion',{}).get('obligations',[])}
            if not (additions&correct)-wrong:continue
            rows.append(dict(id='/'.join(path.relative_to(execution).parts[:3]),round=r['round'],
                active_sha256=current['candidate_sha256'],rejected_proposal_sha256=history[-1]['proposal_sha256'],
                wrongly_allowed=sorted(wrong),active_uncovered=sorted(correct),proposed_obligations=sorted(additions),
                request_sha256=digest(request),folder=str(rd.resolve()),
                reason='Prior rejected proposal coverage was used in place of retained candidate coverage.'))
            break
    dump(out,dict(model_calls=0,rows=rows,affected_trajectories=len(rows),
        selection_rule='First observed addition rejection per new-policy trajectory whose proposed obligation is uncovered in retained native evidence but counted as covered only by the rejected proposal. No independent results read.'))
    print(dict(affected_trajectories=len(rows),rows=rows),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.execution,a.out)
