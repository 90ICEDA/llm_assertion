import unittest
from research196_temporal_qualification import oracle,waves,assertions


class TaggedTemporalOracle(unittest.TestCase):
    def test_reordering_cancellation_and_backpressure_are_legal(self):
        r=oracle(waves()['legal_reorder_cancel_backpressure'])
        self.assertEqual(r['status'],'legal');self.assertGreaterEqual(r['max_simultaneously_pending'],2)
        self.assertEqual(len(r['cancelled']),2)
    def test_distinct_violation_classes_and_incomplete_tail(self):
        for name in ('late_response','wrong_response_tag','dropped_response'):
            self.assertEqual(oracle(waves()[name])['status'],'violation')
        self.assertEqual(oracle(waves()['legal_reorder_cancel_backpressure'][:8])['status'],'unknown')
    def test_tag_reuse_is_unknown_not_valid_stimulus(self):
        wave=waves()['legal_reorder_cancel_backpressure'];wave[7]['req_id']=0
        self.assertEqual(oracle(wave)['status'],'unknown')


if __name__=='__main__':unittest.main()
