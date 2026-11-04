import copy
import unittest
from research196_component_guard import runtime, component_check
from research194_refinement import digest


def fixture():
    before=[dict(label=n,antecedent='req',consequent='ack',timing='same_sample',obligations=['respond']) for n in ('edited','anchor')]
    after=copy.deepcopy(before);after[0]['antecedent']='req && enable'
    def measurement(candidate, active, fp):
        return dict(candidate_sha256=digest(candidate),targets=['t'],detected_ids=['t'],triggered_ids=['t'],
            transaction_detected_ids=['t'],false_positives=[dict(id='fp')] if fp else [],
            native_complete=True,reference_complete=True,critical_unknown=[],native_bindings={'fixture':'digest'},
            executions=[dict(result=dict(compile_status='passed',execution_status='completed'))],
            evidence=[dict(id='t',status='confirmed',label='violation',obligation='respond',
                assertions=[dict(assertion='anchor',trigger=True,failure=True),dict(assertion='edited',trigger=active,failure=False)])])
    return before,after,measurement(before,True,True),measurement(after,False,False)


class ComponentGuard(unittest.TestCase):
    def test_runtime_blocks_inactive_component_masked_by_anchor(self):
        before,after,base,measured=fixture();core,_=runtime('L')
        ctl=core.Controller(before,'R3',['respond'],protected={'t'})
        decision=ctl.observe(after,measured,baseline=base)['decision']
        self.assertFalse(decision['accepted']);self.assertEqual(ctl.active,before)
        self.assertEqual(decision['component_guard']['blocked_components'],['edited'])

    def test_switch_off_reproduces_old_acceptance(self):
        before,after,base,measured=fixture();core,_=runtime('L',False)
        ctl=core.Controller(before,'R3',['respond']);self.assertTrue(ctl.observe(after,measured,baseline=base)['decision']['accepted'])

    def test_legal_narrowing_with_remaining_confirmed_trigger_is_allowed(self):
        before,after,base,measured=fixture();measured['evidence'][0]['assertions'][1]['trigger']=True
        core,_=runtime('L');ctl=core.Controller(before,'R3',['respond'])
        self.assertTrue(ctl.observe(after,measured,baseline=base)['decision']['accepted'])

    def test_unknown_witness_cannot_grant_activity(self):
        before,after,base,measured=fixture();measured['evidence'][0].update(status='unknown')
        measured['evidence'][0]['assertions'][1]['trigger']=True
        check=component_check(before,after,base,measured)
        self.assertFalse(check['passed']);self.assertIn('component_activity_unconfirmed:edited',check['unknown'])

    def test_new_label_cannot_hide_inactive_replacement(self):
        before,after,base,measured=fixture();after[0]['label']='renamed';measured['candidate_sha256']=digest(after)
        self.assertFalse(component_check(before,after,base,measured)['passed'])

    def test_confirmed_failure_allows_existing_fallback_without_accepting(self):
        before,after,base,measured=fixture();core,_=runtime()
        ctl=core.Controller(before,'R3',['respond']);entry=ctl.observe(after,measured,baseline=base)
        self.assertEqual(entry['next_stage'],'compose');self.assertEqual(ctl.active,before)


if __name__=='__main__':unittest.main()
