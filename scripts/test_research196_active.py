import unittest
from research196_active_search import fit_wall_cost,predict,control_contexts


class WallCostTests(unittest.TestCase):
    def records(self):
        return [dict(query=dict(split='development',rows=[dict(en=1)]*n),heldout_access=False,
            cost=dict(observed_sampled_cycles=2*n,acquisition_wall_seconds=20+.02*n+11,lock_wait_seconds=11)) for n in (24,72,216)]
    def test_fixed_cost_is_preserved_and_lock_wait_removed(self):
        m=fit_wall_cost(self.records());self.assertAlmostEqual(m['fixed_seconds'],20)
        self.assertAlmostEqual(predict(m,dict(rows=[{}]*72)),21.44)
        self.assertLess(predict(m,dict(rows=[{}]*216))/predict(m,dict(rows=[{}]*24)),1.3)
    def test_heldout_results_are_rejected(self):
        r=self.records();r[0]['query']['split']='independent'
        with self.assertRaises(ValueError):fit_wall_cost(r)
    def test_payload_and_long_prefixes_do_not_inflate_novelty(self):
        a=dict(rows=[dict(en=1,d=i,q=i) for i in range(50)])
        b=dict(rows=[dict(en=1,d=0,q=100) for i in range(500)])
        self.assertEqual(control_contexts(a,('q',)),control_contexts(b,('q',)))


if __name__=='__main__':unittest.main()
