import unittest
from research194_active_analysis import context_gaps
from research194_metrics import temporal_detection


class TraceContextDedupTests(unittest.TestCase):
    def measurement(self,second_actual=4):
        evidence=[];jobs=[]
        for index,start in enumerate((3,20)):
            evidence.append(dict(id=str(index),evidence_id=str(index),status='confirmed',label='violation',counted_target=True,
                assertions=[dict(failure=False)],obligation='step',parent_bug='counter/artificial',transaction_id='tx'+str(index),
                transaction=start,cycle=start+1,query_id='query'+str(index),variant='primary'))
            jobs.append(dict(query_id='query'+str(index),variant='primary',trace=[dict(cycle=start,q=2,en=1),dict(cycle=start+1,q=4 if index==0 else second_actual,en=0)]))
        return dict(evidence=evidence,executions=jobs)

    def test_same_transaction_prefix_deduplicates_across_schedule_and_cycle(self):
        result=context_gaps(self.measurement())
        self.assertEqual(len(result),1)
        item=next(iter(result.values()));self.assertEqual(set(item['evidence_ids']),{'0','1'})

    def test_different_observed_fault_behavior_is_retained(self):
        self.assertEqual(len(context_gaps(self.measurement(5))),2)

    def test_unknown_is_not_a_context_gap(self):
        m=self.measurement();m['evidence'][0]['status']='unknown';m['evidence'][1]['counted_target']=False
        self.assertFalse(context_gaps(m))

    def test_late_alarm_is_detected_once_but_not_timely(self):
        m=dict(targets=['t'],detected_ids=[],evidence=[
            dict(evidence_id='t',status='confirmed',label='violation',obligation='data',cycle=5,counted_target=True,assertions=[]),
            dict(evidence_id='t',status='confirmed',label='violation',obligation='data',cycle=7,counted_target=False,assertions=[dict(failure=True,obligations=['data'])]),
            dict(evidence_id='t',status='confirmed',label='violation',obligation='data',cycle=8,counted_target=False,assertions=[dict(failure=True,obligations=['data'])])])
        result=temporal_detection(m)
        self.assertEqual(result['transaction_detected_ids'],['t']);self.assertEqual(result['late_detected_ids'],['t'])
        self.assertEqual(result['timely_detected_ids'],[]);self.assertEqual(result['detection_delay_cycles'],{'t':2})
        for key,value in [('status','unknown'),('label','legal'),('obligation','other')]:
            for ev in m['evidence'][1:]:ev[key]=value
            self.assertEqual(temporal_detection(m)['transaction_missed_ids'],['t'])
            for ev in m['evidence'][1:]:ev[key]={'status':'confirmed','label':'violation','obligation':'data'}[key]


if __name__=='__main__':unittest.main()
