"""Three-sample post-freeze explanatory replay; no model feedback or tuning."""
import obligation_continuation_experiment as exp
from obligation_continuation import x, iso, NAME


def main():
    x.OUT=x.ROOT/'deliverables'/NAME;exp.setup();block=x.OUT/'formal'
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'final_freeze.json').items())
    out=x.OUT/'final_examples';out.mkdir(exist_ok=False)
    d=x.read(x.OUT/'frozen/fifo/definition.json')
    original=x.read(block/'quarantine/fifo/inputs.json')[0]
    rows=original[:3]
    assert not x.check_inputs(d,rows)
    x.engine.sources=lambda d:(block/'quarantine/fifo/control.v',block/'quarantine/fifo/sibling.v')
    results=[]
    for arm in ('B','D'):
        cs=x.read(block/'development/fifo'/arm/'final.json')['candidates']
        q=iso.evaluate(d,rows,cs,'final_examples/fifo_'+arm)
        x.append(out/'queries.jsonl',dict(case='fifo',arm=arm,**q))
        result=dict(arm=arm,candidates=cs,input=rows,metrics=exp.paired_metrics(d,q,cs),runs=q['runs'])
        results.append(result)
    assert not results[0]['metrics']['fp'] and len(results[0]['metrics']['causal_detections'])==1
    assert results[1]['metrics']['fp']==[2]
    x.dump(out/'fifo_B_D.json',dict(results=results,standard='minimum three samples with two mandatory reset samples; no input-value minimization',
        origin='prefix of already-consumed holdout, explanatory replay only, not a new independent holdout',
        model_feedback=False,frozen_candidates_unchanged=True))
    print('FIFO B/D minimal contrast: two reset samples plus one stalled presentation; B accepts control and detects mutant, D rejects control',flush=True)


if __name__=='__main__':main()
