"""Real archived evidence for contract/routing regression, no model calls."""
import copy
import unittest
import json
from research194_refinement_runner import ROOT,read
from research199_refinement import runtime,ARMS
from research198_active_obligation_fix import active_uncovered
from research199_independent import mutate,FAULTS
import research197_cases as cases

P=ROOT/'deliverables/research198_refinement_prepare_20261104_r01'

def states():
    return [e for e in read(P/'protocol.json')['entries'] if e['policy']=='local_first' and e['search']=='S3']

class Factorial(unittest.TestCase):
    def test_routing_independent_of_contract(self):
        changes=0
        for e in states():
            s=read(e['state']);a=cases.CaseAdapter(e['case_id']);stages={}
            for arm in ('B0','B1','B2','B3'):
                c,r=runtime(arm);ctl=r.controller_from(a,'R3',s['baseline'],3);ctl.consider_empty_domain(s['first_measurement']);stages[arm]=ctl.stage
            self.assertEqual(stages['B0'],stages['B2']);self.assertEqual(stages['B1'],stages['B3'])
            changes+=stages['B0']!=stages['B1']
        self.assertEqual(changes,4)

    def test_contract_independent_of_routing_and_enforced(self):
        cores={a:runtime(a)[0] for a in ('B0','B1','B2','B3')}
        self.assertEqual(cores['B0'].output_contract('local'),cores['B1'].output_contract('local'))
        self.assertEqual(cores['B2'].output_contract('local'),cores['B3'].output_contract('local'))
        generic=dict(op='replace_field',assertion='x',field='consequent',value='out_valid')
        typed=dict(op='set_delay',assertion='x',field='antecedent',expression='valid',cycles=1)
        for arm in ('B0','B1'):
            self.assertEqual(cores[arm].render_operation(generic),('consequent','out_valid'))
            with self.assertRaises(ValueError):cores[arm].render_operation(typed)
        for arm in ('B2','B3'):
            self.assertIn('$past',cores[arm].render_operation(typed)[1])
            with self.assertRaises(ValueError):cores[arm].render_operation(generic)

    def test_same_archived_native_proposal_same_gate(self):
        totals=[]
        for arm in ('B1','B3'):
            accepted=0
            for e in states():
                # Same native S0 T archive, same initial candidate; retain its
                # original evidence for this equivalence qualification only.
                original=next(x for x in read(P/'protocol.json')['entries'] if x['case_id']==e['case_id'] and x['seed']==e['seed'] and x['search']=='S0' and x['policy']=='local_first')
                s=read(original['state']);core,r=runtime(arm);adapter=cases.CaseAdapter(e['case_id'])
                ctl=r.controller_from(adapter,'R3',s['baseline'],3);ctl.consider_empty_domain(s['first_measurement'])
                folder=ROOT/'deliverables/research197_typed_execute_20261104_r01'/e['case_id']/str(e['seed'])/'T/refinement/round01'
                response=read(folder/'model_edit.json')
                if arm=='B1':
                    typed=runtime('B3')[0];response=copy.deepcopy(response)
                    response['edits']=[dict(op='replace_field',assertion=x['assertion'],field=typed.render_operation(x)[0],value=typed.render_operation(x)[1]) for x in response['edits']]
                proposal,edits=ctl.parse(response,s['public_evidence'],adapter.validate)
                self.assertEqual(proposal,read(folder/'proposal.json'))
                m=r.bind_measurement(read(folder/'proposal_native/measurement.json'),proposal)
                accepted+=ctl.observe(proposal,m,edit_record=edits,baseline=s['first_measurement'])['decision']['accepted']
            totals.append(accepted)
        self.assertEqual(totals,[4,4])

    def test_composition_binding_in_all_arms(self):
        e=states()[0];s=read(e['state'])
        for arm in ARMS:
            c,_=runtime(arm);ev=copy.deepcopy(s['public_evidence']);ev[0]['candidate_sha256']='wrong'
            with self.assertRaises(ValueError):active_uncovered(c,s['initial'],ev)

    def test_failures_do_not_authorize_fallback(self):
        e=states()[0];s=read(e['state'])
        for arm in ('B1','B3'):
            c,r=runtime(arm);ctl=r.controller_from(cases.CaseAdapter(e['case_id']),'R3',s['baseline'],3)
            ctl.interface_failure('schema','invalid');self.assertEqual(ctl.stage,'local');self.assertIsNone(ctl.receipt)
            m=copy.deepcopy(s['first_measurement']);m['critical_unknown']=['unknown']
            self.assertIsNone(ctl.consider_empty_domain(m));self.assertEqual(ctl.stage,'local')

    def test_reserved_replacement_only_selected_occurrence(self):
        f=FAULTS[cases.IDS[0]];text='a'+f['search']+'b'+f['search']+'c'
        self.assertEqual(mutate(text,f),'a'+f['search']+'b'+f['replace']+'c')
        with self.assertRaises(ValueError):mutate('unmatched',f)

if __name__=='__main__':unittest.main()
