import copy
import unittest
import research192_independent as x


class IndependentTests(unittest.TestCase):
    def test_population_unique_and_outside_old_pool(self):
        descriptors=x.test_population()
        self.assertEqual(len(descriptors),16)
        self.assertEqual(len({tuple(d['semantic_key']) for d in descriptors}),16)
        old=x.ROOT/'deliverables/research188_drop_binding_prepare_20261102_r01'
        blocked={tuple(d['semantic_key']) for name in ('reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json') for d in x.read(old/name)}
        self.assertFalse(blocked & {tuple(d['semantic_key']) for d in descriptors})
        for d in descriptors:
            self.assertEqual(x.p.semantic_key(x.p.scene(d),d['depth']),tuple(d['semantic_key']))

    def test_combined_preserves_expressions(self):
        a=x.p.controls()['partial_stalled']
        b=copy.deepcopy(x.p.controls()['replacement_ready'])
        b[0]['label']='v1_a0'
        rows=x.p.q.rows(16,'ready_first')
        text=x.combined_bench({'a':a,'b':b},16,'ready_first',rows)
        self.assertEqual(text.count(': assert property'),2)
        self.assertEqual(text.count('initial begin $dumpfile'),1)
        for c in (a,b):
            for prop in c:
                self.assertIn(f"({prop['antecedent']}) |-> ({prop['consequent']})",text)

    def test_no_exposure_is_not_pass(self):
        m=dict(public_targets=[],historical_targets=[],detected_ids=[],triggered_ids=[],false_positives=[],critical_unknown=[])
        jobs=[dict(scene_id='x',revision=rev,result=dict(compile_status='passed',execution_status='completed')) for rev in ('before','after')]
        grade=x.scope_grade(m,{'x/frame2'},jobs,4,True)
        self.assertFalse(grade['passed'])
        self.assertEqual(grade['false_negative_ids'],[])
        self.assertEqual(grade['missing_exposure_ids'],['x/frame2'])


if __name__=='__main__':unittest.main()
