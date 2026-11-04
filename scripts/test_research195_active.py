import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research195_active_queries as queries
import research195_active_search as active
from research195_active_analysis import state_at_cut


class ScheduleTests(unittest.TestCase):
    def test_seeded_lengths_signal_widths_and_split_separation(self):
        for case in queries.CASES:
            pool=queries.query_pool(case,19507)
            self.assertEqual(pool,queries.query_pool(case,19507));self.assertEqual(len(pool),18)
            self.assertEqual(len({q['id'] for q in pool}),18)
            widths=queries.get_case(case)['input_signals']
            for q in pool:
                self.assertEqual(len(q['rows']),q['generator_parameters']['length']);self.assertEqual(q['estimated_cost'],2*len(q['rows']))
                for row in q['rows']:
                    self.assertEqual(set(row),set(widths));self.assertTrue(all(0<=row[k]<2**widths[k] for k in row))
            reserved=queries.query_pool(case,19507,'independent')
            self.assertFalse({q['semantic_key'] for q in pool}&{q['semantic_key'] for q in reserved})
            self.assertNotEqual(pool,queries.query_pool(case,19519))

    def test_temporal_stress_is_explicit_in_inputs(self):
        pool={q['family']:q for q in queries.query_pool('arbiter',19507) if len(q['rows'])==72}
        self.assertGreater(queries.coverage(pool['held_grant'])['request_with_no_ack'],10)
        self.assertGreater(queries.coverage(pool['reset_inflight'])['resets'],3)
        counter={q['family']:q for q in queries.query_pool('counter',19507) if len(q['rows'])==72}
        self.assertGreater(queries.coverage(counter['clear_arbitration'])['clear_load_overlap'],0)
        self.assertGreater(queries.coverage(counter['enable_pause'])['disabled_samples'],3)


class CostPolicyTests(unittest.TestCase):
    def baseline(self):return dict(query=dict(id='public',family='public',obligations=[]),measurement=dict(evidence=[]),gap_contexts={})

    def test_cost_divisor_changes_choice_with_identical_benefit_model(self):
        pool=[queries.generate_query('counter','up_boundary',n,19507) for n in (24,216)]
        def goal(q,*args,**kwargs):return dict(semantic_discrimination=.5 if len(q['rows'])==24 else 1)
        with tempfile.TemporaryDirectory(dir=active.ROOT/'deliverables') as tmp,patch.object(active.semantics,'plan_goal',side_effect=goal):
            picks={}
            for strategy in ('active_cost','active_no_cost'):
                s=active.Session('counter',strategy,19507,pool,self.baseline(),dict(native_seconds_intercept=1,native_seconds_per_sample=.01),Path(tmp)/strategy)
                picks[strategy]=s.rank()['selected_query_id']
            self.assertEqual(picks['active_cost'],pool[0]['id']);self.assertEqual(picks['active_no_cost'],pool[1]['id'])

    def test_over_budget_query_is_never_submitted_and_heldout_pool_is_rejected(self):
        pool=[queries.generate_query('counter','up_boundary',72,19507)]
        with tempfile.TemporaryDirectory(dir=active.ROOT/'deliverables') as tmp:
            s=active.Session('counter','active_cost',19507,pool,self.baseline(),dict(native_seconds_intercept=1,native_seconds_per_sample=.01),Path(tmp)/'session',cycle_budget=48)
            self.assertIsNone(s.rank()['selected_query_id'])
            with self.assertRaisesRegex(ValueError,'heldout_pool'):
                active.Session('counter','S2',19507,[dict(pool[0],split='independent')],self.baseline(),{},Path(tmp)/'forbidden')

    def test_cut_does_not_credit_a_query_that_crosses_budget(self):
        points=[dict(cycles=0,gaps=0),dict(cycles=48,gaps=2),dict(cycles=192,gaps=7)]
        self.assertEqual(state_at_cut(points,'cycles',191)['gaps'],2)
        self.assertEqual(state_at_cut(points,'cycles',192)['gaps'],7)

    def test_wall_prediction_is_fitted_only_from_supplied_pilot(self):
        rows=[dict(cost=dict(observed_sampled_cycles=x,native_seconds=10+.01*x)) for x in (48,144,432)]
        fit=active.fit_cost_calibration(rows)
        self.assertAlmostEqual(fit['native_seconds_intercept'],10);self.assertAlmostEqual(fit['native_seconds_per_sample'],.01)
        reversed_cost=copy.deepcopy(rows)
        for r in reversed_cost:r['cost']['native_seconds']=20-.01*r['cost']['observed_sampled_cycles']
        self.assertEqual(active.fit_cost_calibration(reversed_cost)['native_seconds_per_sample'],0)


if __name__=='__main__':unittest.main()
