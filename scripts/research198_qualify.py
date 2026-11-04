"""Native regression qualification, explicitly not a real-model experiment."""
import argparse
from pathlib import Path
from research195_refinement_adapter import clone
from research194_refinement_runner import ROOT, read, dump
from research198_refinement import runtime
import research197_cases as cases


def run(out):
    module=clone('research197_local_qualification')
    module.runtime=lambda arm=None: runtime('local_first')
    module.run(ROOT/'deliverables/research197_qualification_20261104_r02',out)
    rows=[]
    p=read(ROOT/'deliverables/research197_refinement_prepare_20261104_r01/protocol.json')
    for e in p['entries']:
        if e['arm'] is not None or e['strategy']!='R3':continue
        s=read(e['state']);a=cases.CaseAdapter(e['case_id']);stages={};findings=[]
        for policy in ('legacy','local_first'):
            core,runner=runtime(policy);c=runner.controller_from(a,'R3',s['baseline'],5)
            c.consider_empty_domain(s['first_measurement']);stages[policy]=c.stage
            findings=core.localize(c.active,s['first_measurement']['evidence'])
        rows.append(dict(id=e['id'],stages=stages,localized_fields=sorted({(f['assertion'],f['field']) for f in findings}),
            cause='Legacy skips all existing local fields if any necessary obligation lacks a declared component. New routing distinguishes partial local repair from adding missing components.'))
    dump(Path(out)/'routing_diagnosis.json',dict(rows=rows,model_calls=0,
        scope='Archived native initial evidence; routing replay only. Native qualification uses handwritten proposals and is never counted as model success.'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
