import json
import unittest
import research192_ablation as x


class AblationTests(unittest.TestCase):
    def test_initial_history_not_ready_leak(self):
        initial,_,_,evidence=x.refine.archived_baseline()
        history=[e for e in evidence if e.get('policy')=='stalled_first']
        base=x.s.read(x.refine.SOURCE/'request.preview.json')
        for strategy in ('R1','R3'):
            request,_=x.refine.build_request(base,strategy,history,19207,initial)
            body=json.loads(request['messages'][1]['content'])
            self.assertNotIn('public_development',body)
            self.assertTrue(all(e['policy']=='stalled_first' for e in body['development_observations']))

    def test_factorial_mapping_and_equal_query_cost(self):
        self.assertEqual(set(x.ARMS.values()),{(s,r) for s in ('ordinary','active') for r in ('R1','R3')})
        self.assertEqual({q['estimated_cost'] for q in x.options()},{2})
        self.assertEqual(len({q['id'] for q in x.options()}),4)
        for q in x.options():
            d=q['descriptor']
            self.assertEqual(x.p.semantic_key(x.p.scene(d),d['depth']),tuple(d['semantic_key']))

    def test_unknown_does_not_close_coverage_gap(self):
        c=x.active.ActiveSelector([dict(antecedent='first_present',consequent='input_complete')],['o'])
        q=[dict(id='q',dimensions=['trigger'],obligations=['o'],estimated_cost=2)]
        before=c.select(q)['chosen']['components']['obligation_deficit']
        c.observe('q','unknown',['o'],[],2,protected_obligations=['o'])
        self.assertEqual(before,c.select(q)['chosen']['components']['obligation_deficit'])


if __name__=='__main__':unittest.main()
