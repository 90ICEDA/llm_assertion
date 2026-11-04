"""Synthetic tests for a posthoc audit, never experimental evidence."""
import copy
import unittest
from research194_refinement_fp_audit import compare


def fixture(cycles, label='old', projected=False):
    candidate=[dict(label=label, obligations=['o'])]
    marker_label='c0_a0' if projected else label
    job=dict(query_id='q',variant='correct',folder='/synthetic/q',
        trace=[dict(cycle=i, value=i%2) for i in range(5)],
        result=dict(compile_status='passed',execution_status='completed',
            failures=[dict(id=marker_label,detail='cycle='+str(c)) for c in cycles]),
        reference=dict(unknown=[],checks=[dict(passed=True)]))
    evs=[dict(id='coarse',status='confirmed',label='legal',variant='correct',
        query_id='q',cycle=c,obligation='o',source_log='/synthetic/q/execute.log',
        assertions=[dict(assertion=label,obligations=['o'],failure=True)]) for c in cycles]
    return dict(executions=[job],evidence=evs,false_positives=evs[:1]),candidate


class AuditTest(unittest.TestCase):
    def test_coarse_collision_and_renaming(self):
        b,bc=fixture([1],projected=True);a,ac=fixture([1,3],label='renamed')
        result=compare(b,a,bc,ac)
        self.assertEqual([x['cycle'] for x in result['coarse_id_masked_new_legal_alarm_events']],[3])
        self.assertEqual(result['unresolved_native_marker_bindings'],[])

    def test_different_trace_not_history_regression(self):
        b,bc=fixture([1]);a,ac=fixture([1,3]);a['executions'][0]['trace'][0]['value']=99
        result=compare(b,a,bc,ac)
        self.assertEqual(result['new_legal_alarm_events_on_same_queries'],[])
        self.assertEqual(result['query_trace_mismatch'],['q'])

    def test_unconfirmed_or_non_native_not_accused(self):
        b,bc=fixture([]);a,ac=fixture([3]);a['executions'][0]['result']['failures']=[]
        result=compare(b,a,bc,ac)
        self.assertEqual(result['new_legal_alarm_events_on_same_queries'],[])
        self.assertEqual(len(result['unresolved_native_marker_bindings']),1)
        a['executions'][0]['reference']['unknown']=['unknown']
        self.assertEqual(compare(b,a,bc,ac)['after_alarm_units'],0)


if __name__=='__main__': unittest.main()
