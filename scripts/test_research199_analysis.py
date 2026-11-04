"""Guard cohort identity and cost accounting before expensive dispatch."""
import tempfile
import unittest
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump
from research194_refinement import digest
from research199_refinement import ARMS
import research199_cost as cost
import research199_independent as independent
import research197_cases as cases

class Analysis(unittest.TestCase):
    def test_registered_freeze_identity_without_constructing_inputs(self):
        with tempfile.TemporaryDirectory(prefix='r199_freeze_test_',dir=ROOT/'deliverables') as td:
            root=Path(td);cid=cases.IDS[0]
            e=dict(id=cid+'/19711/A3',case_id=cid,seed=19711,search='S3',strategy='R3',arm='A3',cohort='online')
            independent.register(root,dict(entries=[e],source_bindings={}))
            registry=read(root/'acceptance_registration.json')['entries'][0]
            folder=root/'execution';candidate=cases.get_case(cid)['initial']
            dump(folder/'frozen.json',candidate)
            dump(folder/'outcome.json',dict(**registry,status='frozen',provenance='real_remote_model',frozen_sha256=digest(candidate),fixture='identity test only; not a model experiment'))
            mod=independent.runtime(root/'acceptance_registration.json')
            mod.freeze([dict(**registry,folder=str(folder.relative_to(ROOT)))],1,root/'freeze.json')
            self.assertTrue(read(root/'freeze.json')['all_trajectories_closed'])
            self.assertFalse((root/'native').exists())

    def test_fixed_vs_online_service_cost_and_round_checkpoints(self):
        with tempfile.TemporaryDirectory(prefix='r199_cost_test_',dir=ROOT/'deliverables') as td:
            root=Path(td);prep=root/'prep';execution=root/'execution';cid=cases.IDS[0];initial=cases.get_case(cid)['initial'];entries=[]
            for seed in (19711,19723):
                for arm,spec in ARMS.items():
                    identity=f'{cid}/{seed}/{arm}';state=prep/identity/'state.json';folder=execution/identity/'refinement'
                    dump(state,dict(initial=initial));entries.append(dict(id=identity,case_id=cid,seed=seed,arm=arm,search=spec['search'],strategy=spec['strategy'],mode='ready',state=str(state)))
                    dump(folder/'outcome.json',dict(status='frozen'));dump(folder/'frozen.json',initial)
                    dump(folder/'rounds.json',[dict(round=1,status='no_change',model=dict(model_calls=1))])
                    dump(folder/'round01/model_call/result.json',dict(prompt_tokens=7,completion_tokens=2,wall_seconds=3))
                    acquisition=dict(wall_seconds=0) if arm.startswith('B') else dict(r196_total_seconds=5,wall_seconds=0)
                    dump(folder/'cost_components.json',[dict(purpose='acquisition',round=1,**acquisition),dict(purpose='proposal_history',round=1,wall_seconds=2)])
            dump(prep/'protocol.json',dict(entries=entries,case_ids=[cid],seeds=[19711,19723]));dump(execution/'outcome.json',dict(status='completed_all_versions_frozen'))
            cost.register(prep,execution,root/'cost');r=read(root/'cost/registration.json')
            for run in r['runs']:
                self.assertEqual(run['final_tokens'],9)
                self.assertEqual(run['final_service_seconds'],5 if run['id'].split('/')[-1].startswith('B') else 10)
            self.assertTrue(any(s['axis']=='round' and s['budget_label']=='2' for s in r['sections']))
            self.assertEqual(r['primary_cost_axis']['budget_label'],'131072')

if __name__=='__main__':unittest.main()
