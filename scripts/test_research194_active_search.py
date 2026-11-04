import copy
import tempfile
import unittest
from pathlib import Path
import research194_active_search as active
import research194_active_semantics as sem


class FakeAdapter:
    candidate=[dict(label='a',antecedent='req',consequent='ack',timing='same_sample',obligations=['response'])]
    def get_case(self,case_id):
        return dict(id=case_id,initial=self.candidate,candidate_pool=[self.candidate,[dict(self.candidate[0],timing='next_sample')]],disable='rst',output_signals={'ack':1})
    def query_pool(self,case_id,split,seed):
        assert split=='development'
        return [dict(id=f'q{i}',rows=[dict(rst=0,req=int(t==1)) for t in range(4)],obligations=['response'],estimated_cost=2,split=split) for i in range(3)]


class ActiveSearchTests(unittest.TestCase):
    def test_uart_helpers_input_only_and_reset(self):
        rows=[dict(rst_n=1,tx_enable=1,wr=1,wr_data=0xa5),dict(rst_n=1,tx_enable=1,wr=0,wr_data=0),dict(rst_n=1,tx_enable=0,wr=0,wr_data=0),dict(rst_n=1,tx_enable=1,wr=0,wr_data=0)]
        query=dict(rows=rows);before=copy.deepcopy(query)
        actual=active.planner_query(query,{'id':'uart'})['planner_rows']
        self.assertEqual([r['txn_age'] for r in actual],[0,0,1,0])
        self.assertEqual([r['txn_active'] for r in actual],[0,1,1,0]);self.assertEqual(query,before)

    def test_projection_never_credits_contrast_detection(self):
        candidate=FakeAdapter.candidate;combined,mapping=active.combine_candidates([candidate,candidate])
        event=dict(id='e',evidence_id='e',status='confirmed',label='violation',counted_target=True,obligation='response',transaction_id='t',parent_bug='p',assertions=[dict(assertion='c0_a0',trigger=False,failure=False),dict(assertion='c1_a0',trigger=True,failure=True)])
        result=active.project_measurement(dict(evidence=[event],cost={}),candidate,mapping)
        self.assertEqual(result['targets'],['e']);self.assertEqual(result['detected_ids'],[])
        self.assertEqual(result['evidence'][0]['assertions'][0]['assertion'],'a')
        self.assertTrue(result['evidence'][0]['candidate_predictions'][0]['independent_facts']['required_trigger_missing'])
        self.assertEqual(list(active.gaps(result['evidence'])),['FN:e'])
        event['counted_target']=False
        result=active.project_measurement(dict(evidence=[event],cost={}),candidate,mapping)
        self.assertEqual(result['targets'],[]);self.assertEqual(active.gaps(result['evidence']),{})

    def test_unknown_not_promoted_and_candidate_hash_protection(self):
        event=dict(id='e',status='unknown',label='violation',counted_target=True,obligation='response',transaction_id='t',parent_bug='p',assertions=[])
        self.assertFalse(active.gaps([event]));event.update(status='confirmed',candidate_sha256='old')
        event['assertions']=[dict(failure=True)]
        self.assertFalse(active.protected_obligations([event],'new'))
        self.assertEqual(active.protected_obligations([event],'old'),{'response'})
        event['assertions'][0]['failure']=False
        self.assertFalse(active.protected_obligations([event],'old'))

    def test_unknown_filter_preserves_current_and_global_failures(self):
        candidate=FakeAdapter.candidate;_,mapping=active.combine_candidates([candidate,candidate])
        raw=dict(evidence=[],cost={},critical_unknown=[dict(assertion='c1_a0',reason='other'),dict(assertion='c0_a0',reason='mine'),dict(reason='reference_incomplete')])
        result=active.project_measurement(raw,candidate,mapping)
        self.assertEqual(result['critical_unknown'],[dict(assertion='a',reason='mine'),dict(reason='reference_incomplete')])
        self.assertFalse(result['reference_complete'])

    def test_s3_does_not_repeat_public_schedule_while_unseen_remain(self):
        adapter=FakeAdapter();pool=adapter.query_pool('x','development',7)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'deliverables') as tmp:
            a=active.Session('x','S3',7,Path(tmp)/'a',initial_queries=[pool[0]],adapter=adapter,max_queries=2)
            b=active.Session('x','S3',7,Path(tmp)/'b',initial_queries=[pool[0]],adapter=adapter,max_queries=2)
            x=a.rank(adapter.candidate);y=b.rank(adapter.candidate)
            self.assertNotEqual(x['selected_query_id'],'q0');self.assertEqual(x['selected_query_id'],y['selected_query_id'])
            self.assertTrue(any(r['semantic_discrimination']==1 for r in x['ranked']))
            self.assertFalse(x['heldout_access'])

    def test_sv_reduction_and_case_reset_binding(self):
        self.assertEqual(sem.value(sem.parse('(|request) && !(|grant)'),[dict(request=4,grant=0)],0),1)
        self.assertEqual(sem.value(sem.parse('(^request)'),[dict(request=7)],0),1)
        c=active.semantic_candidate(FakeAdapter.candidate,{'disable':'!rst_n'})
        self.assertEqual(sem.evaluate_candidate(c,[dict(rst_n=0,req=1,ack=0)])['status'],'vacuous')


if __name__=='__main__':unittest.main()
