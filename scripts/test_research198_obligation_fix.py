"""Parser regression qualification; constructed edits are not model results."""
import copy
import json
import unittest
from research194_refinement_runner import ROOT,read
from research198_refinement import runtime as old_runtime
from research198_active_obligation_fix import runtime,active_uncovered
import research197_cases as cases

class RetainedCoverage(unittest.TestCase):
    def context(self):
        rd=ROOT/'deliverables/research198_refinement_execute_20261104_r01/historical_delta_counter/19711/S0_local_first/refinement/round02'
        return json.loads(read(rd/'request.preview.json')['messages'][-1]['content']),read(rd/'model_edit.json')
    def controller(self,factory,context):
        core,_=factory();cfg=cases.get_case(cases.IDS[2])
        c=core.Controller(cfg['initial'],'R3',cfg['obligations'],max_rounds=5)
        c.active=copy.deepcopy(context['current_assertions']);c.history=copy.deepcopy(context['earlier_rounds'])
        c.rounds=context['round'];c.stage='compose';c.receipt=core.FailureReceipt(**context['fallback_receipt'])
        return core,c
    def test_rejected_proposal_does_not_erase_retained_gap(self):
        context,_=self.context();core,c=self.controller(runtime,context)
        self.assertIn('overflow_capture',active_uncovered(core,c.active,context['development_observations']))
        supplement=copy.deepcopy(c.active[0]);supplement['label']='supplement_capture'
        response=dict(edits=[dict(op='add_assertion',assertion=supplement)],reason='Constructed parser regression, not an LLM result.')
        old,oc=self.controller(old_runtime,context)
        with self.assertRaisesRegex(ValueError,'addition_requires_uncovered_obligation'):
            oc.parse(response,context['development_observations'],lambda x:cases.validate(cases.IDS[2],x))
        after,_=c.parse(response,context['development_observations'],lambda x:cases.validate(cases.IDS[2],x))
        self.assertEqual(after[:-1],c.active)
    def test_actual_unexposed_additions_stay_rejected(self):
        context,response=self.context();core,c=self.controller(runtime,context)
        with self.assertRaisesRegex(ValueError,'addition_requires_uncovered_obligation'):
            c.parse(response,context['development_observations'],lambda x:cases.validate(cases.IDS[2],x))
    def test_candidate_binding_is_mandatory(self):
        context,_=self.context();core,c=self.controller(runtime,context)
        evidence=copy.deepcopy(context['development_observations']);evidence[0]['candidate_sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'composition_evidence_not_bound'):
            active_uncovered(core,c.active,evidence)

if __name__=='__main__':unittest.main()
