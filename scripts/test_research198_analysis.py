import copy
import unittest
from research198_paths import chains,structural_chains
from research198_cost_sections import runtime

class AnalysisChecks(unittest.TestCase):
    def path(self):
        result=[]
        for index,stage in enumerate(('local','compose','regenerate'),1):
            row=dict(event='native_measured',stage=stage,round=index,before_sha256='active',
                decision=dict(critical_unknown=[],accepted=False,semantic_failure=True,complete=False))
            if stage!='regenerate':row['fallback_receipt']=dict(stage=stage,active_sha256='active',native_bindings={'fixture':'hash'})
            result.append(row)
        return result
    def test_rejected_regeneration_still_counts_as_executed_chain(self):
        self.assertEqual(len(chains(self.path())),1)
        self.assertFalse(chains(self.path())[0]['regeneration_accepted'])
    def test_unordered_or_disconnected_stages_are_not_full_path(self):
        data=self.path()
        self.assertEqual(chains(data[1:]+data[:1]),[])
        data[1]['before_sha256']='different'
        self.assertEqual(chains(data),[])
    def test_unknown_or_accepted_prior_stage_cannot_enable_chain(self):
        for index in range(3):
            data=self.path();data[index]['decision']['critical_unknown']=['unknown']
            self.assertEqual(chains(data),[])
        data=self.path();data[0]['decision']['accepted']=True
        self.assertEqual(chains(data),[])
    def test_common_round_and_cost_axes_are_installed(self):
        constants=repr(runtime().register.__code__.co_consts)
        self.assertIn("('round', (0, 3, 5))",constants)
        self.assertIn('wall_seconds',constants)
        self.assertNotIn('r196_total_seconds',constants)
    def test_partial_improvement_requires_certificate_and_separate_label(self):
        data=self.path();data[0]['decision']['accepted']=True;data[0]['retained_sha256']='improved'
        for r in data[1:]:
            r['before_sha256']='improved'
            if 'fallback_receipt' in r:r['fallback_receipt']['active_sha256']='improved'
        self.assertEqual(structural_chains(data),[])
        data.insert(1,dict(event='structural_local_domain_empty',certificate=dict(active_sha256='improved',missing_obligations=['uncovered'],confirmed_target_ids=['t'],native_bindings={'fixture':'h'})))
        self.assertEqual(len(structural_chains(data)),1)
        self.assertEqual(chains(data),[])
        data[-1]['decision']['critical_unknown']=['compile_failure']
        self.assertEqual(structural_chains(data),[])

if __name__=='__main__':unittest.main()
