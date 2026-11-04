import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import research194_case_cards as cards
import research194_active_outcome_analysis as outcomes


class CaseCardQualificationTests(unittest.TestCase):
    def grade(self,**kwargs):
        result=dict(fault='primary',target_ids=['t'],valid_reachable_fault=True,native_complete=True,reference_complete=True,unknown_records=0)
        result.update(kwargs);return result

    def test_same_fault_name_does_not_hide_different_targets(self):
        result=cards.common_test_eligibility([self.grade()],[self.grade(target_ids=['other'])])
        self.assertFalse(result['eligible']);self.assertIn('different_target_population:primary',result['reasons'])

    def test_unexposed_is_named_and_unknown_never_qualifies(self):
        grade=self.grade(target_ids=[],valid_reachable_fault=False)
        self.assertEqual(cards.common_test_eligibility([grade],[grade])['excluded_unexposed_faults'],['primary'])
        self.assertFalse(cards.common_test_eligibility([self.grade()],[self.grade(unknown_records=1)])['eligible'])

    def test_declared_seed_schedule_is_allowed_but_transport_failure_is_not(self):
        with tempfile.TemporaryDirectory(dir=cards.report.ROOT/'deliverables') as tmp:
            folder=Path(tmp);row=dict(folder=str(folder),seed=19407,status='frozen',provenance='real_remote_model',causal_comparison_eligible=True,actual_model_calls=2)
            for n in (1,2):
                p=folder/f'round{n:02}'/'request.preview.json';p.parent.mkdir()
                p.write_text(json.dumps(dict(model='fixed',seed=19407+(n-1)*1009,temperature=.2,max_tokens=2048)))
            (folder/'rounds.json').write_text(json.dumps([dict(round=1,status='accepted'),dict(round=2,status='no_change')]))
            self.assertTrue(cards.trajectory_eligibility(row)['eligible'])
            (folder/'rounds.json').write_text(json.dumps([dict(round=1,status='accepted'),dict(round=2,status='model_transport_or_decode_failure')]))
            self.assertFalse(cards.trajectory_eligibility(row)['eligible'])

    def test_common_four_way_scope_excludes_unknown_and_missing_strategy(self):
        grades={s:self.grade() for s in outcomes.STRATEGIES}
        self.assertTrue(outcomes.qualify_common_fault(grades)['eligible'])
        grades['S3']=self.grade(unknown_records=1)
        self.assertFalse(outcomes.qualify_common_fault(grades)['eligible'])
        del grades['S3'];self.assertIn('missing_strategy_grade',outcomes.qualify_common_fault(grades)['reasons'])

    def test_budget_truncation_overrides_wrapper_and_retains_itt_assignment(self):
        with tempfile.TemporaryDirectory(dir=cards.report.ROOT/'deliverables') as tmp:
            folder=Path(tmp);row=dict(folder=str(folder),seed=19407,status='frozen',provenance='real_remote_model',causal_comparison_eligible=True,actual_model_calls=2)
            (folder/'rounds.json').write_text(json.dumps([dict(round=1,status='accepted'),dict(round=2,status='model_transport_or_decode_failure',model=dict(status='response_truncated',done_reason='length',completion_tokens=2048))]))
            result=cards.trajectory_eligibility(row)
            self.assertFalse(result['eligible']);self.assertFalse(result['full_three_round_decisions'])
            self.assertTrue(result['itt_frozen_assignment_eligible']);self.assertTrue(result['sealed_causal_comparison_eligible'])
            self.assertEqual(result['reasons'],['budget_output_truncation'])
            self.assertEqual(result['raw_round_classifications'][-1]['completion_tokens'],2048)

    def test_itt_parent_summary_retains_assigned_incomplete_round_outcome(self):
        pairs=[dict(parent_bug='parent',method='S3',comparator='S0',seed=seed,itt_eligible=True,eligible=False,
            itt_transaction_rate_delta=.25,itt_timely_rate_delta=.125,itt_no_loss_no_new_fp_gain=True,lost_ids=[],legal_fp_record_delta=0,common_faults=['primary']) for seed in outcomes.SEEDS]
        result=outcomes.summarize_itt(pairs)
        parent=next(p for p in result['parent_summary'] if p['method']=='S3' and p['comparator']=='S0')
        self.assertTrue(parent['fully_paired']);self.assertEqual(parent['seed_pairs_retained_despite_incomplete_rounds'],2)
        macro=next(p for p in result['population'] if p['method']=='S3' and p['comparator']=='S0')
        self.assertEqual(macro['parent_macro_transaction_rate_delta'],.25)

    def test_pending_analysis_never_reads_heldout_grades(self):
        with tempfile.TemporaryDirectory(dir=cards.report.ROOT/'deliverables') as tmp:
            campaign=Path(tmp)/'campaign';(campaign/'independent').mkdir(parents=True)
            (campaign/'independent'/'results.json').write_text('THIS FILE MUST NOT BE READ BEFORE COMPLETED')
            result=outcomes.build(campaign,Path(tmp)/'analysis')
            self.assertEqual(result['status'],'awaiting_completed_common_independent_acceptance')
            self.assertFalse(result['independent_grades_read'])

    def test_mid_round_gain_must_survive_final_candidate(self):
        with tempfile.TemporaryDirectory(dir=cards.report.ROOT/'deliverables') as tmp:
            folder=Path(tmp);rd=folder/'round01';initial=[dict(label='a')];final=[dict(label='b')]
            event=dict(id='t',evidence_id='t',status='confirmed',label='violation',obligation='data',cycle=1,counted_target=True,query_id='q',variant='primary',assertions=[dict(assertion='a',obligations=['data'],failure=False)])
            before=dict(candidate_sha256=cards.cases.digest(initial),targets=['t'],detected_ids=[],evidence=[event],executions=[])
            after=json.loads(json.dumps(before));after.update(candidate_sha256=cards.cases.digest(final),detected_ids=['t']);after['evidence'][0]['assertions'][0]['failure']=True
            def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
            save(folder/'initial.json',initial);save(folder/'frozen.json',final);save(folder/'rounds.json',[dict(round=1,status='accepted')])
            save(rd/'current_measurement.json',before);save(rd/'proposal_native/measurement.json',after);save(rd/'proposal.json',final)
            save(rd/'request.preview.json',dict(messages=[dict(content=json.dumps(dict(current_assertions=initial,development_observations=[dict(id='t',status='confirmed')])))]))
            terminal=json.loads(json.dumps(before));terminal['candidate_sha256']=cards.cases.digest(final);save(folder/'terminal_measurement.json',terminal)
            row=dict(folder=str(folder),case_id='fixture',frozen_sha256=cards.cases.digest(final))
            with patch.object(cards.cases,'get_case',return_value={'initial':initial}):
                self.assertFalse(cards.card(row,'positive','active_search',[],[],{})['full_positive_chain'])
                save(folder/'terminal_measurement.json',after)
                self.assertTrue(cards.card(row,'positive','active_search',[],[],{})['full_positive_chain'])


if __name__=='__main__':unittest.main()
