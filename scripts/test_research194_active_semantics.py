"""Behavioral cases for the bounded temporal planner, independent of RTL oracle."""
import copy
import unittest
from research194_active_semantics import parse,value,evaluate_assertion,evaluate_candidate,plan_goal,verify_native_predictions


class TemporalSemanticsTests(unittest.TestCase):
    def assertion(self,**kw):
        return dict(label='a',antecedent=kw.get('antecedent','req'),consequent=kw.get('consequent','ack'),
                    timing=kw.get('timing','same_sample'),**{k:v for k,v in kw.items() if k not in ('antecedent','consequent','timing')})

    def test_exact_delay_vs_window(self):
        trace=[dict(cycle=i,rst=0,req=int(i==1),ack=int(i==3)) for i in range(5)]
        exact=evaluate_assertion(self.assertion(timing='next_sample'),trace)
        ranged=evaluate_assertion(self.assertion(window=[1,2]),trace)
        self.assertEqual(exact['failures'],[2]);self.assertEqual(ranged['status'],'passed')

    def test_captured_transaction_and_response_mismatch(self):
        trace=[dict(cycle=0,rst=0,req=1,req_id=2,rsp_id=0,ack=0),
               dict(cycle=1,rst=0,req=0,req_id=3,rsp_id=2,ack=1),
               dict(cycle=2,rst=0,req=0,req_id=0,rsp_id=0,ack=0)]
        good=self.assertion(timing='next_sample',consequent='ack && rsp_id == $past(req_id)')
        wrong=self.assertion(timing='next_sample',consequent='ack && rsp_id == req_id')
        self.assertEqual(evaluate_assertion(good,trace)['status'],'passed')
        self.assertEqual(evaluate_assertion(wrong,trace)['failures'],[1])

    def test_reset_and_flush_cancel_pending(self):
        trace=[dict(cycle=0,rst=0,req=1,ack=0,flush=0),dict(cycle=1,rst=1,req=0,ack=0,flush=0)]
        result=evaluate_assertion(self.assertion(timing='next_sample'),trace)
        self.assertFalse(result['failures']);self.assertEqual(result['attempts'][0]['verdict'],'cancelled')
        trace[1].update(rst=0,flush=1)
        self.assertEqual(evaluate_assertion(self.assertion(timing='next_sample',cancel='flush'),trace)['status'],'passed')
        self.assertEqual(evaluate_assertion(self.assertion(timing='next_sample'),trace)['status'],'failed')

    def test_unknown_history_tail_and_unsupported(self):
        trace=[dict(cycle=0,rst=0,req=1,ack=1)]
        for a in (self.assertion(consequent='$past(ack,2)'),self.assertion(timing='next_sample'),self.assertion(consequent='helper(ack)')):
            self.assertEqual(evaluate_assertion(a,trace)['status'],'unknown')
        self.assertEqual(value(parse('0 && missing'),trace,0),0)
        self.assertEqual(value(parse('1 || missing'),trace,0),1)
        self.assertIsNone(value(parse('1 && missing'),trace,0))

    def test_parser_bit_history_and_conditional(self):
        trace=[dict(x=6,flag=1),dict(x=9,flag=0)]
        self.assertEqual(value(parse("x[3:1] == 3'b100"),trace,1),1)
        self.assertEqual(value(parse('$past(x,1)+3 == x'),trace,1),1)
        self.assertEqual(value(parse('flag ? x : $past(x)'),trace,1),6)

    def test_equivalent_text_has_no_fake_semantic_disagreement(self):
        q=dict(id='q',rows=[dict(cycle=i,rst=0,req=int(i==1)) for i in range(4)],constraints=['reset_valid'])
        original=copy.deepcopy(q)
        a=[self.assertion(consequent='ack != 0')];b=[self.assertion(consequent='!!ack')]
        goal=plan_goal(q,[a,b],{'ack':1},16)
        self.assertEqual(goal['semantic_discrimination'],0);self.assertEqual(q,original)
        c=[self.assertion(timing='next_sample')]
        goal=plan_goal(q,[[self.assertion()],c],{'ack':1},16)
        self.assertEqual(goal['semantic_discrimination'],1)
        self.assertTrue(goal['witnesses']);self.assertEqual(goal['native_queries'],0)

    def test_native_mismatch_is_unknown_not_evidence(self):
        c=[self.assertion()];trace=[dict(cycle=0,rst=0,req=1,ack=0)]
        native=dict(compile_status='passed',execution_status='completed',triggers=[dict(id='a',cycle=0)],failures=[dict(id='a',cycle=0)])
        self.assertEqual(verify_native_predictions(c,trace,native)['status'],'confirmed_semantics')
        native['failures']=[]
        self.assertEqual(verify_native_predictions(c,trace,native)['status'],'unknown')


if __name__=='__main__':unittest.main()
