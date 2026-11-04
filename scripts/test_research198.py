"""Controller regression checks using archived native evidence, not model trials."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from research194_refinement_runner import ROOT, read
from research198_refinement import runtime
import research197_cases as cases

PREP = ROOT/'deliverables/research197_refinement_prepare_20261104_r01'

class Routing(unittest.TestCase):
    def states(self):
        return [e for e in read(PREP/'protocol.json')['entries'] if e['arm'] is None and e['strategy']=='R3']

    def test_real_initial_evidence_local_first(self):
        changed=0
        for e in self.states():
            state=read(e['state']); a=cases.CaseAdapter(e['case_id'])
            old,ro=runtime('legacy'); new,rn=runtime('local_first')
            c0=ro.controller_from(a,'R3',state['baseline'],5)
            c1=rn.controller_from(a,'R3',state['baseline'],5)
            c0.consider_empty_domain(state['first_measurement'])
            c1.consider_empty_domain(state['first_measurement'])
            findings=new.localize(c1.active,state['first_measurement']['evidence'])
            if findings:
                self.assertEqual(c1.stage,'local')
                changed += c0.stage=='compose'
            self.assertEqual(c1.active,c0.active)
        self.assertEqual(changed,8)

    def test_unknown_never_authorizes_structural_skip(self):
        e=self.states()[0];s=read(e['state']);a=cases.CaseAdapter(e['case_id'])
        core,r=runtime();c=r.controller_from(a,'R3',s['baseline'],5)
        m=copy.deepcopy(s['first_measurement']);m['critical_unknown']=['unknown']
        self.assertIsNone(c.consider_empty_domain(m));self.assertEqual(c.stage,'local')

    def test_invalid_interfaces_do_not_create_failure_receipt(self):
        e=self.states()[0];s=read(e['state']);a=cases.CaseAdapter(e['case_id'])
        core,r=runtime();c=r.controller_from(a,'R3',s['baseline'],5)
        for _ in range(2):c.interface_failure('schema','invalid operation')
        self.assertEqual(c.stage,'local');self.assertIsNone(c.receipt);self.assertFalse(c.finished)
        for _ in range(3):c.interface_failure('schema','invalid operation')
        self.assertTrue(c.finished)

    def test_corrected_contract_and_module_isolation(self):
        import research194_refinement as old
        original=old.Controller
        c,r=runtime();contract=c.output_contract('local')
        self.assertNotIn('replace_field',json.dumps(contract))
        self.assertEqual(set(contract['operations']),set(contract['operations_allowed']))
        with self.assertRaises(ValueError):c.render_operation(dict(op='replace_field',assertion='x',field='consequent',value='1'))
        self.assertIs(old.Controller,original)

    def test_archived_real_edits_under_automatic_controller(self):
        accepted=0
        for e in self.states():
            if e['search']!='S0':continue
            s=read(e['state']);a=cases.CaseAdapter(e['case_id'])
            core,r=runtime();c=r.controller_from(a,'R3',s['baseline'],5)
            c.consider_empty_domain(s['first_measurement'])
            folder=ROOT/'deliverables/research197_typed_execute_20261104_r01'/e['case_id']/str(e['seed'])/'T/refinement/round01'
            proposal,record=c.parse(read(folder/'model_edit.json'),s['public_evidence'],a.validate)
            self.assertEqual(proposal,read(folder/'proposal.json'))
            measured=r.bind_measurement(read(folder/'proposal_native/measurement.json'),proposal)
            decision=c.observe(proposal,measured,edit_record=record,baseline=s['first_measurement'])
            accepted+=decision['decision']['accepted']
            self.assertEqual(decision['stage'],'local')
        self.assertEqual(accepted,4)  # Archived replay, NOT six new model calls.

    def test_fixed_acquisition_cost_is_not_charged_as_new_search(self):
        from research198_execute import FixedSession
        session=FixedSession({},'S0',{},ROOT)
        record=dict(cost=dict(native_seconds=42,native_compile_attempts=2))
        result=session.reuse_acquisition(record,[])
        self.assertEqual(result['cost']['native_seconds'],0)
        self.assertEqual(result['historical_acquisition_cost']['native_seconds'],42)
        self.assertEqual(record['cost']['native_seconds'],42)

    def test_five_round_runner_uses_same_candidate_native_cache(self):
        from research198_execute import fixed_runtime,FixedSession
        e=next(e for e in self.states() if e['case_id']==cases.IDS[0] and e['search']=='S0')
        state=read(e['state']);a=cases.CaseAdapter(e['case_id'])
        archive=ROOT/'deliverables/research197_typed_execute_20261104_r01'/e['case_id']/str(e['seed'])/'T/refinement/round01'
        proposal=read(archive/'proposal.json');native=read(archive/'proposal_native/measurement.json');edit=read(archive/'model_edit.json')
        def evaluate(candidate,folder,queries):
            self.assertEqual(candidate,proposal)
            self.assertEqual(cases.digest(queries),cases.digest(state['queries']))
            m=copy.deepcopy(native)
            m['cost']=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0)
            return runner.bind_measurement(m,candidate)
        a.evaluate=evaluate
        core,runner,cache=fixed_runtime('local_first',state,a)
        class Replay:
            provenance='archived_response_replay_not_fresh_model'
            def __call__(self,request,folder):
                return dict(model_calls=0,status='archived_response_replay',prompt_tokens=0,completion_tokens=0),copy.deepcopy(edit)
        with tempfile.TemporaryDirectory(prefix='r198_test_',dir=ROOT/'deliverables') as folder:
            folder=Path(folder);prep=folder/'prep'
            runner.prepare_first(a,'R3',e['seed'],state['baseline'],state['queries'],state['first_acquisition'],prep,
                max_rounds=5,current_measurement=state['first_measurement'])
            session=FixedSession(state,'S0',cache,folder/'acquisition')
            result=runner.run_trajectory(a,'R3',e['seed'],folder/'run',state['baseline'],state['queries'],session,Replay(),max_rounds=5,prepared=prep)
            self.assertEqual(result['accepted_rounds'],1)
            self.assertEqual(result['actual_model_calls'],0)
            self.assertEqual(len(read(folder/'run/rounds.json')),5)
            self.assertEqual(result['native_compile_attempts'],0)

if __name__=='__main__':unittest.main()
