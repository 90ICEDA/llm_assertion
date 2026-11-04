"""Prevent isolation arms leaking into main R3 and over-budget proposals."""
import tempfile
from pathlib import Path
import unittest
from research194_refinement_runner import ROOT,dump,read
from research197_cost_sections import runtime


class CostIsolation(unittest.TestCase):
    def test_isolation_arms_and_completed_prefixes(self):
        module=runtime()
        with tempfile.TemporaryDirectory(dir=ROOT/'deliverables',prefix='r197_cost_test_') as directory:
            root=Path(directory).resolve()
            self.assertTrue(root.is_relative_to((ROOT/'deliverables').resolve()))
            prepared=root/'prepared';execution=root/'execution';out=root/'cost';entries=[]
            tags=['S0_R0','S0_R1','S0_R2','S0_R3','S1_R1','S2_R1','S3_R1','S3_R3','F','P','T']
            for seed in (1,2):
                for tag in tags:
                    arm=tag if tag in ('F','P','T') else None
                    search,strategy=('S0','R3') if arm else tag.split('_')
                    identity=f'case/{seed}/{tag}';state=prepared/identity/'state.json';folder=execution/identity/'refinement'
                    initial=[dict(label='initial')];proposal=[dict(label=tag)];tokens={'F':10,'P':20,'T':30}.get(tag,40)
                    dump(state,dict(initial=initial));dump(folder/'outcome.json',dict(status='frozen'))
                    dump(folder/'rounds.json',[dict(round=1,status='accepted')]);dump(folder/'cost_components.json',[])
                    dump(folder/'round01/model_call/result.json',dict(prompt_tokens=tokens,completion_tokens=0,wall_seconds=tokens))
                    dump(folder/'round01/proposal.json',proposal);dump(folder/'frozen.json',proposal)
                    entries.append(dict(id=identity,case_id='case',seed=seed,arm=arm,search=search,strategy=strategy,mode='ready',state=str(state)))
            dump(prepared/'protocol.json',dict(entries=entries,case_ids=['case'],seeds=[1,2]))
            dump(execution/'outcome.json',dict(status='completed_all_versions_frozen'))
            module.register(prepared,execution,out);data=read(out/'registration.json')
            self.assertEqual(22,len(data['runs']))
            section=next(s for s in data['sections'] if s['group']=='T' and s['seed']==1 and s['axis']=='tokens' and s['budget_label']=='minimum_observed_total')
            self.assertEqual(10,section['budget'])
            self.assertEqual({'F':1,'P':0,'T':0},{a:p['round'] for a,p in section['checkpoints'].items()})
            main=next(s for s in data['sections'] if s['group']=='R' and s['seed']==1 and s['axis']=='tokens' and s['budget_label']=='minimum_observed_total')
            self.assertEqual(40,main['budget'])
            self.assertEqual(40,main['checkpoints']['R3']['tokens'])


if __name__=='__main__':unittest.main()
