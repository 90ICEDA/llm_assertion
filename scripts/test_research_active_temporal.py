"""Acquisition integrity tests: no oracle lookahead, unknown credit or fake costs."""
import unittest
from research_active_temporal import ActiveSelector, analyze_candidates, rank_queries


class ActiveAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.candidates = [dict(antecedent='req', consequent='ack', delay=1),
                           dict(antecedent='req && ready', consequent='ack', delay=2)]
        self.queries = [dict(id='a', dimensions=['window'], obligations=['latency'], estimated_cost=1),
                        dict(id='b', dimensions=['response'], obligations=['payload'], estimated_cost=1)]

    def test_candidate_dimensions_and_identical_pool(self):
        result = analyze_candidates(self.candidates)
        self.assertIn('window', result['pairs'][0]['dimensions'])
        self.assertIn('trigger', result['pairs'][0]['dimensions'])
        timing = analyze_candidates([dict(self.candidates[0],timing='same_sample'),dict(self.candidates[0],timing='next_sample')])
        self.assertIn('window', timing['pairs'][0]['dimensions'])
        identical = rank_queries(self.queries, [self.candidates[0]] * 2, [], [])
        self.assertTrue(all(q['components']['candidate_discrimination'] == 0 for q in identical))

    def test_unknown_consumes_attempt_but_no_evidence_credit(self):
        selector = ActiveSelector(self.candidates, ['latency', 'payload'])
        selector.observe('a', 'unknown', ['latency'], ['fake'], 1)
        ranking = selector.select(self.queries)['ranking']
        target = next(q for q in ranking if q['id'] == 'a')
        self.assertEqual(target['components']['obligation_deficit'], 1)
        self.assertEqual(target['components']['evidence_novelty'], .5)

    def test_confirmed_novelty_and_obligation_coverage_changes_selection(self):
        queries = [dict(q, dimensions=['window']) for q in self.queries]
        p = ActiveSelector(self.candidates, [])
        self.assertEqual(p.select(queries)['chosen']['id'], 'a')
        p.observe('a', 'confirmed', ['latency'], ['gap'], 1)
        self.assertEqual(p.select(queries)['chosen']['id'], 'b')
        ranked = p.select(queries)['ranking']
        self.assertTrue(all(q['components']['obligation_deficit']==1 for q in ranked))
        p.observe('b', 'confirmed', ['payload'], [], 1, protected_obligations=['payload'])
        self.assertEqual(next(q for q in p.select(queries)['ranking'] if q['id']=='b')['components']['obligation_deficit'], .5)

    def test_cost_and_unknown_structure(self):
        queries = [dict(q, dimensions=['window']) for q in self.queries]
        queries[0]['estimated_cost'] = 100
        self.assertEqual(rank_queries(queries, self.candidates, [], [])[0]['id'], 'b')
        uncertain = rank_queries(self.queries, ['unsupported opaque expression', self.candidates[0]], [], [])
        self.assertTrue(all(q['components']['candidate_discrimination'] == 0 for q in uncertain))
        with self.assertRaises(ValueError):
            rank_queries([dict(queries[0], estimated_cost=0)], self.candidates, [], [])

    def test_future_outcome_fields_not_consumed(self):
        ranked = rank_queries(self.queries, self.candidates, [], [])
        tainted = [dict(q, oracle_verdict='violation', future_gap_count=999) for q in self.queries]
        reranked = rank_queries(tainted, self.candidates, [], [])
        self.assertEqual([(r['id'],r['score']) for r in ranked], [(r['id'],r['score']) for r in reranked])


if __name__ == '__main__':
    unittest.main()
