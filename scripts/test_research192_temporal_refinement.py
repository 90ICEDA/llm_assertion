"""Safety and causal-boundary checks for temporal localized modification."""
import copy
import json
import unittest
import research192_temporal_refinement as r


class TemporalRefinementTests(unittest.TestCase):
    def setUp(self):
        self.initial = r.p.controls()['partial_stalled']
        self.ev = dict(id='transaction1', status='confirmed', label='violation',
            assertions=[dict(assertion='first_stalled', trigger=False, failure=False)])

    def test_unknown_cannot_authorize_edit(self):
        e = copy.deepcopy(self.ev); e['status'] = 'unknown'
        self.assertEqual(r.localize(self.initial, [e]), [])

    def test_narrow_trigger_and_scope_preservation(self):
        f = r.localize(self.initial, [self.ev])
        self.assertEqual({v['kind'] for v in f}, {'trigger_too_narrow', 'vacuity_or_insufficient_trigger'})
        value = dict(edits=[dict(op='replace_field', assertion='first_stalled',
            field='antecedent', value='first_present')], reason='test fixture, not model')
        new = r.apply_local_edits(self.initial, value, f)
        self.assertEqual(new[0]['consequent'], self.initial[0]['consequent'])
        self.assertEqual(self.initial[0]['antecedent'], 'first_present && !m_axis_tready')
        value['edits'][0]['field'] = 'consequent'
        with self.assertRaisesRegex(ValueError, 'unlocalized'):
            r.apply_local_edits(self.initial, value, f)

    def test_legal_alarm_is_ambiguous(self):
        e = copy.deepcopy(self.ev); e.update(label='legal')
        e['assertions'][0].update(trigger=True, failure=True)
        self.assertEqual({v['kind'] for v in r.localize(self.initial, [e])},
            {'trigger_too_broad', 'response_too_strict'})

    def test_supported_causal_classes_need_facts(self):
        e = copy.deepcopy(self.ev)
        e['independent_facts'] = dict(latency_mismatch=True, transaction_mismatch=True,
            legal_exception_missed=True, required_trigger_missing=True)
        self.assertTrue({'latency_window','transaction_matching','legal_exception','insufficient_trigger'} <=
            {v['kind'] for v in r.localize(self.initial, [e])})
        self.assertEqual(r.localize(self.initial, [e], enabled=False), [])

    def test_composition_waits_for_failed_local_attempt(self):
        add = dict(edits=[dict(op='add_assertion', assertion=r.p.controls()['replacement_ready'][0])], reason='fixture')
        with self.assertRaisesRegex(ValueError, 'composition_before'):
            r.apply_local_edits(self.initial, add, [])
        with self.assertRaisesRegex(ValueError, 'without_uncovered'):
            r.apply_local_edits(self.initial, add, [], local_failed=True)
        union = r.apply_local_edits(self.initial, add, [], local_failed=True, uncovered_obligations=[r.p.OB])
        self.assertEqual(len(union), 2)

    def test_history_gate_rejects_actual_regression(self):
        m = dict(ordinary_accept=True, historical_accept=False, lost=['past-target'],
                 false_positives=[], critical_unknown=[])
        self.assertTrue(r.decide('R1', m)['accepted'])
        self.assertFalse(r.decide('R3', m)['accepted'])
        m['critical_unknown'] = ['unresolved']
        self.assertFalse(r.decide('R1', m)['accepted'])

    def test_same_raw_evidence_and_fixed_sampling_all_arms(self):
        base = r.s.read(r.SOURCE / 'request.preview.json')
        bodies = []
        for strategy in r.STRATEGIES:
            req, _ = r.build_request(base, strategy, [self.ev], 19207, self.initial)
            self.assertEqual((req['model'], req['seed'], req['temperature'], req['max_tokens']),
                (r.MODEL, 19207, 0.2, 1024))
            bodies.append(json.loads(req['messages'][1]['content']))
        self.assertTrue(all(b['development_observations'] == [self.ev] for b in bodies))
        self.assertNotIn('bidirectional_feedback', bodies[0])
        self.assertNotIn('history_guard', bodies[1])
        self.assertNotIn('localization', bodies[2])
        self.assertIn('localization', bodies[3])


if __name__ == '__main__':
    unittest.main()
