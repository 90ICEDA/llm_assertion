import unittest
from pathlib import Path
from research194_refinement_runner import ROOT,read
import research197_cases as cases
from research197_refinement import runtime

class TemporalRegression(unittest.TestCase):
    def test_reference_against_native_correct_and_faulty_traces(self):
        root=ROOT/'deliverables/research197_qualification_20261104_r01'
        for cid in cases.IDS:
            jobs=read(root/cid/'native/executions.json')
            for job in jobs:
                ref=cases.reference(cid,job['trace'])
                self.assertFalse(ref['unknown'])
                if job['variant']=='correct':self.assertTrue(all(c['passed'] for c in ref['checks']),(cid,job['query_id']))
                else:self.assertTrue(any(not c['passed'] for c in ref['checks']),cid)
    def test_typed_bounds_and_no_unrestricted_field_edit(self):
        core,_=runtime('T')
        with self.assertRaises(ValueError):core.render_operation(dict(op='replace_field',assertion='x',field='consequent',value='1'))
        with self.assertRaises(ValueError):core.render_operation(dict(op='set_response_window',assertion='x',field='consequent',response='out_valid',min_cycles=18,max_cycles=22,anchor_cycles=21))
        field,expr=core.render_operation(dict(op='set_response_window',assertion='x',field='consequent',response='out_valid',min_cycles=18,max_cycles=21,anchor_cycles=21))
        self.assertEqual(field,'consequent');self.assertIn('$past',expr)
    def test_no_shared_source_module_patching(self):
        import research194_refinement as old
        render=old.render_operation
        runtime('T');self.assertIs(old.render_operation,render)

if __name__=='__main__':unittest.main()
