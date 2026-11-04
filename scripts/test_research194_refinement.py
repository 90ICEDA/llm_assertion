import copy
import unittest
import research194_refinement as r

INITIAL=[dict(label='p',antecedent='req && ready',consequent='ack',timing='same_sample',obligations=['o'])]
EVIDENCE=[dict(id='new',status='confirmed',label='violation',obligation='o',assertions=[dict(assertion='p',trigger=False,failure=False)])]
def validate(x):
    if len({a['label'] for a in x})!=len(x):raise ValueError('duplicate_label')
    return x
def measurement(candidate,detected=(),fps=(),unknown=False):
    return dict(candidate_sha256=r.digest(candidate),targets=['old','new'],detected_ids=list(detected),
        triggered_ids=list(detected),false_positives=[dict(id=x) for x in fps],critical_unknown=['x'] if unknown else [],
        native_complete=not unknown,reference_complete=not unknown,native_bindings={'fixture':'test_only'},
        evidence=[dict(id=x,status='confirmed',label='violation',obligation='o',assertions=[]) for x in ('old','new')])

class RefinementTests(unittest.TestCase):
    def test_exact_noop_does_not_expand_domain(self):
        findings=r.localize(INITIAL,EVIDENCE)
        response=dict(edits=[dict(op='replace_field',assertion='p',field='antecedent',value='req'),
                             dict(op='replace_field',assertion='p',field='consequent',value='ack')],reason='fixture')
        candidate,meta=r.apply_patch(INITIAL,response,findings,validate)
        self.assertEqual(candidate[0]['antecedent'],'req');self.assertEqual(len(meta['noops']),1)
        response['edits'][1]['value']=' ack'
        with self.assertRaisesRegex(ValueError,'not_localized'):r.apply_patch(INITIAL,response,findings,validate)

    def test_duplicate_noop_still_rejected(self):
        edit=dict(op='replace_field',assertion='p',field='consequent',value='ack')
        with self.assertRaisesRegex(ValueError,'duplicate'):
            r.apply_patch(INITIAL,dict(edits=[edit,edit],reason='fixture'),[],validate)

    def test_unknown_never_grants_fallback(self):
        c=r.Controller(INITIAL,'R3',['o'],protected={'old'})
        proposed=copy.deepcopy(INITIAL);proposed[0]['antecedent']='req'
        c.observe(proposed,measurement(proposed,unknown=True),baseline=measurement(INITIAL,['old']))
        self.assertEqual(c.stage,'local');self.assertIsNone(c.receipt);self.assertTrue(c.finished)

    def test_three_measured_stages_and_history(self):
        c=r.Controller(INITIAL,'R3',['o'],protected={'old'})
        failed=copy.deepcopy(INITIAL);failed[0]['antecedent']='ready'
        c.observe(failed,measurement(failed,[]),baseline=measurement(INITIAL,['old']))
        self.assertEqual(c.stage,'compose');self.assertEqual(c.active,INITIAL)
        extra=dict(INITIAL[0],label='p2',antecedent='other')
        composed,edit=c.parse(dict(edits=[dict(op='add_assertion',assertion=extra)],reason='fixture'),EVIDENCE,validate)
        c.observe(composed,measurement(composed,['old']),baseline=measurement(INITIAL,['old']),edit_record=edit)
        self.assertEqual(c.stage,'regenerate')
        final,edit=c.parse(dict(assertions=[dict(INITIAL[0],antecedent='req')],reason='fixture'),EVIDENCE,validate)
        c.observe(final,measurement(final,['old','new']),baseline=measurement(INITIAL,['old']),edit_record=edit)
        self.assertTrue(c.finished);self.assertEqual(c.active,final);self.assertEqual(c.rounds,3)

    def test_receipt_binds_active_and_proposal(self):
        other=[dict(INITIAL[0],antecedent='different')]
        d=r.gate(measurement(other), 'R3', {'old'})
        rec=r.FailureReceipt.from_measurement('local',INITIAL,other,measurement(other),d)
        self.assertFalse(rec.valid_for(other,'local'))
        with self.assertRaisesRegex(ValueError,'mismatch'):
            r.FailureReceipt.from_measurement('local',INITIAL,other,measurement(INITIAL),d)
        with self.assertRaisesRegex(ValueError,'unchanged'):
            r.FailureReceipt.from_measurement('local',INITIAL,INITIAL,measurement(INITIAL),d)

    def test_r2_protects_lost_while_r1_current_progress(self):
        m=measurement(INITIAL,['new']);baseline=measurement(INITIAL,['old'])
        self.assertTrue(r.gate(m,'R1',{'old'},['new'],['o'],baseline)['accepted'])
        self.assertFalse(r.gate(m,'R2',{'old'},['new'],['o'],baseline)['accepted'])
        self.assertTrue(r.gate(m,'R2',{'old'},['new'],['o'],baseline)['regression'])

    def test_new_false_positive_rejects(self):
        decision=r.gate(measurement(INITIAL,['old','new'],['legal']),'R3',{'old'},baseline=measurement(INITIAL,['old']))
        self.assertFalse(decision['accepted']);self.assertTrue(decision['regression'])

    def test_unexposed_obligation_does_not_fabricate_coverage(self):
        decision=r.gate(measurement(INITIAL,['old','new']),'R3',{'old'},necessary_obligations=['o','hidden'],baseline=measurement(INITIAL,['old']))
        self.assertTrue(decision['accepted']);self.assertFalse(decision['complete'])
        self.assertEqual(decision['unexposed_obligations'],['hidden'])

    def test_structured_operations_are_explicit_sva(self):
        base=dict(assertion='p',field='consequent')
        _,text=r.render_operation(dict(base,op='set_window',expression='ack',min_cycles=1,max_cycles=2,quantifier='any'))
        self.assertEqual(text,'($past((ack), 1) || $past((ack), 2))')
        _,text=r.render_operation(dict(base,op='match_transaction',base_expression='ack',request_id='req_id',response_id='rsp_id',cycles=2))
        self.assertIn('$past((req_id), 2)',text)
        with self.assertRaisesRegex(ValueError,'window_bounds'):
            r.render_operation(dict(base,op='set_window',expression='ack',min_cycles=3,max_cycles=2,quantifier='any'))

    def test_no_global_fault_fact_grants_local_edit(self):
        row=dict(EVIDENCE[0],independent_facts={'latency_mismatch':True})
        self.assertNotIn(('p','consequent'),{(x['assertion'],x['field']) for x in r.localize(INITIAL,[row])})

    def test_structural_empty_domain_is_bound_and_free(self):
        c=r.Controller(INITIAL,'R3',['o','missing'])
        m=measurement(INITIAL)
        for ev in m['evidence']:ev['obligation']='missing'
        certificate=c.consider_empty_domain(m)
        self.assertEqual(c.stage,'compose');self.assertEqual(c.rounds,0)
        self.assertFalse(certificate['semantic_failure']);self.assertTrue(c.receipt.valid_for(INITIAL,'local'))
        extra=dict(INITIAL[0],label='extra',obligations=['missing'])
        proposal,_=c.parse(dict(edits=[dict(op='add_assertion',assertion=extra)],reason='fixture'),m['evidence'],validate)
        self.assertEqual(len(proposal),2)

    def test_existing_obligation_and_unknown_cannot_skip_local(self):
        for m in (measurement(INITIAL),measurement(INITIAL,unknown=True)):
            c=r.Controller(INITIAL,'R3',['o','missing'])
            self.assertIsNone(c.consider_empty_domain(m));self.assertEqual(c.stage,'local')

    def test_late_history_loss_is_rejected_and_preservation_allowed(self):
        baseline=measurement(INITIAL,[]);baseline['transaction_detected_ids']=['old']
        proposed=measurement(INITIAL,['new']);proposed['transaction_detected_ids']=['new']
        decision=r.gate(proposed,'R3',baseline=baseline,protected_transactions={'old'})
        self.assertFalse(decision['accepted']);self.assertEqual(decision['historical_any_cycle_lost_ids'],['old'])
        proposed['transaction_detected_ids']=['old','new']
        decision=r.gate(proposed,'R3',baseline=baseline,protected_transactions={'old'})
        self.assertTrue(decision['accepted']);self.assertFalse(decision['timely_complete']);self.assertTrue(decision['any_cycle_complete'])

    def test_new_late_detection_is_progress_but_not_timely_gain(self):
        baseline=measurement(INITIAL,[]);baseline['transaction_detected_ids']=['old']
        proposed=measurement(INITIAL,[]);proposed['transaction_detected_ids']=['old','new']
        decision=r.gate(proposed,'R3',baseline=baseline,protected_transactions={'old'})
        self.assertTrue(decision['accepted']);self.assertEqual(decision['timely_gained_ids'],[])
        self.assertEqual(decision['transaction_gained_ids'],['new'])

    def test_detection_without_native_trigger_is_unknown(self):
        proposed=measurement(INITIAL,['new']);proposed['triggered_ids']=[]
        decision=r.gate(proposed,'R3')
        self.assertFalse(decision['accepted']);self.assertTrue(decision['critical_unknown'])

if __name__=='__main__':unittest.main()
