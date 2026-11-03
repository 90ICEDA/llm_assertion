"""Regression checks for pre-NBA diagnostic alignment, not native SVA proof."""
import unittest
from research17_fifo_feedback import qualify_sampling


class SamplingChecks(unittest.TestCase):
    def examples(self):
        trace=[dict(cycle=0,rst=1,svalid=0,sready=1,sdata=0,mvalid=0,mready=1,mdata=0),
               dict(cycle=1,rst=0,svalid=1,sready=1,sdata=123,mvalid=0,mready=1,mdata=0),
               dict(cycle=2,rst=0,svalid=1,sready=1,sdata=456,mvalid=1,mready=1,mdata=123),
               dict(cycle=3,rst=1,svalid=0,sready=1,sdata=0,mvalid=1,mready=0,mdata=456),
               dict(cycle=4,rst=0,svalid=0,sready=1,sdata=0,mvalid=0,mready=1,mdata=0)]
        refs=[dict(t,ref_count=count,ref_expected=data,drain_due=0) for t,count,data in zip(trace,(0,0,1,1,0),(0,0,123,456,456))]
        return trace,refs

    def test_pre_update_simultaneous_push_pop_and_reset(self):
        trace,refs=self.examples()
        self.assertEqual(qualify_sampling(trace,refs)['status'],'passed')

    def test_post_update_value_cannot_masquerade_as_sample(self):
        trace,refs=self.examples();refs[1]['ref_count']=1
        result=qualify_sampling(trace,refs)
        self.assertEqual(result['status'],'unknown')
        self.assertIn('pre_NBA_count_mismatch',[x['reason'] for x in result['mismatches']])

    def test_missing_native_trace_not_success(self):
        trace,refs=self.examples()
        self.assertEqual(qualify_sampling(trace,refs[:-1])['status'],'unknown')
        self.assertEqual(qualify_sampling([],[])['status'],'unknown')


if __name__=='__main__':unittest.main()
