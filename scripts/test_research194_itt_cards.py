import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research194_case_cards as cards


class RetainedVersionCardsTests(unittest.TestCase):
    def save(self,path,value):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))

    def fixture(self,root,*,replacement_fp=False,retain_bridge=True,unknown=False,interruption='truncation'):
        initial=[dict(label='a',antecedent='req',consequent='ack',timing='same_sample',obligations=['ob'])]
        final=[dict(initial[0],consequent='correct_ack')];rows=[];grades=[];ind=root/'independent'
        method=root/'method/refinement';baseline=root/'baseline/refinement'
        event=dict(id='dev',evidence_id='dev',status='confirmed',label='violation',obligation='ob',cycle=1,counted_target=True,query_id='qdev',variant='primary',assertions=[dict(assertion='a',obligations=['ob'],failure=False)])
        before=dict(candidate_sha256=cards.cases.digest(initial),targets=['dev'],detected_ids=[],evidence=[event],executions=[])
        after=copy.deepcopy(before);after.update(candidate_sha256=cards.cases.digest(final),detected_ids=['dev']);after['evidence'][0]['assertions'][0]['failure']=True
        terminal=copy.deepcopy(after if retain_bridge else before);terminal['candidate_sha256']=cards.cases.digest(final)
        for folder,search,candidate in [(method,'S3',final),(baseline,'S0',initial)]:
            row=dict(folder=str(folder),case_id='fixture',parent_bug='fixture/parent',seed=19407,status='frozen',provenance='real_remote_model',
                strategy='R1',search_strategy=search,causal_comparison_eligible=True,actual_model_calls=2 if search=='S3' else 1,
                initial_sha256=cards.cases.digest(initial),frozen_sha256=cards.cases.digest(candidate),accepted_rounds=int(search=='S3'))
            if search=='S3' and interruption=='outer':row.update(termination_reason='unhandled_interruption_retained_last_checkpoint',error_type='TypeError',error='fixture failure',causal_comparison_eligible=False)
            rows.append(row)
            self.save(folder/'initial.json',initial);self.save(folder/'frozen.json',candidate)
            context=dict(current_assertions=initial,development_observations=[dict(id='dev',status='confirmed')])
            request=dict(model='fixed',temperature=.2,max_tokens=2048,seed=19407,messages=[dict(role='user',content=json.dumps(context))])
            self.save(folder/'round01/request.preview.json',request)
            rounds=[dict(round=1,status='accepted' if search=='S3' else 'no_change',model=dict(status='response_received'))]
            if search=='S3' and interruption=='truncation':
                rounds.append(dict(round=2,status='model_transport_or_decode_failure',model=dict(status='response_truncated',done_reason='length',completion_tokens=2048)))
                self.save(folder/'round02/request.preview.json',dict(request,seed=20416))
            self.save(folder/'rounds.json',rounds)
            self.save(folder/'terminal_measurement.json',terminal if search=='S3' else before)
            if search=='S3':
                self.save(folder/'round01/current_measurement.json',before);self.save(folder/'round01/proposal.json',final)
                self.save(folder/'round01/proposal_native/measurement.json',after)
            grades.append(dict(folder=str(folder),case_id='fixture',fault='primary',candidate_sha256=cards.cases.digest(candidate),
                native_complete=True,reference_complete=not unknown,unknown_records=int(unknown),valid_reachable_fault=True,
                target_ids=['independent_target'],transaction_detected_ids=['independent_target'] if search=='S3' else [],
                false_positive_records=int(replacement_fp)))
        self.save(ind/'outcome.json',dict(status='completed'));self.save(ind/'results.json',grades)
        self.save(ind/'plan.json',dict(fixture=dict(faults=['primary'])))
        self.save(ind/'fixture/version_mapping.json',dict(keys=[cards.cases.digest(final),cards.cases.digest(initial)]))
        for index,candidate in enumerate((final,initial)):
            legal=dict(id='same_coarse_eid',evidence_id='same_coarse_eid',query_id='legal_query',variant='correct',cycle=2 if index==0 else 1,
                obligation=None,status='confirmed',label='legal',assertions=[dict(assertion='renamed_'+str(index),failure=True)])
            self.save(ind/f'fixture/primary/projection{index}.json',dict(candidate_sha256=cards.cases.digest(candidate),targets=['independent_target'],
                false_positives=[legal] if replacement_fp else [],evidence=[legal] if replacement_fp else []))
        return rows,initial,ind

    def run_fixture(self,root,**kwargs):
        rows,initial,ind=self.fixture(root,**kwargs)
        with patch.object(cards.report,'trajectories',return_value=rows),patch.object(cards.cases,'get_case',return_value={'initial':initial}):
            return cards.build_itt(root,ind,root/'out')

    def test_budget_truncated_retained_real_bridge_can_be_itt_positive(self):
        with tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
            result=self.run_fixture(Path(tmp));item=result['cards'][0]
            self.assertEqual(result['positive_cards'],1);self.assertTrue(item['full_positive_chain'])
            self.assertTrue(item['not_complete_three_round_execution']);self.assertFalse(item['whole_strategy_pass_claim'])
            self.assertFalse(item['trajectory_qualification']['current']['eligible'])
            self.assertEqual(item['trajectory_qualification']['interruption_reasons'],['budget_output_truncation'])

    def test_outer_exception_preserves_reason_without_claiming_full_completion(self):
        with tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
            result=self.run_fixture(Path(tmp),interruption='outer');item=result['cards'][0]
            self.assertEqual(result['positive_cards'],1)
            self.assertEqual(item['trajectory_qualification']['current_error']['error_type'],'TypeError')
            self.assertFalse(item['trajectory_qualification']['strict_primary_eligible'])

    def test_equal_fp_counts_and_equal_coarse_ids_cannot_hide_new_context(self):
        with tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
            root=Path(tmp);result=self.run_fixture(root,replacement_fp=True)
            self.assertEqual(result['positive_cards'],0)
            record=cards.read(root/'out/itt_eligibility.json')[0]
            self.assertEqual(record['new_fp_units'],[['primary','legal_query','correct',2,None]])
            a=record['qualification']['current_fp_binding'];b=record['qualification']['comparison_fp_binding']
            self.assertEqual(a['fp_ids'],b['fp_ids']);self.assertFalse(cards.fp_context_comparison(a,b)['no_new_fp'])

    def test_lost_final_bridge_or_unknown_independent_cannot_qualify(self):
        for options in (dict(retain_bridge=False),dict(unknown=True)):
            with self.subTest(options=options),tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
                self.assertEqual(self.run_fixture(Path(tmp),**options)['positive_cards'],0)

    def test_strict_main_card_uses_context_inclusion_without_relaxing_completion(self):
        with tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
            root=Path(tmp);rows,initial,ind=self.fixture(root,replacement_fp=True,interruption='none')
            with patch.object(cards.report,'trajectories',return_value=rows),patch.object(cards.cases,'get_case',return_value={'initial':initial}):
                result=cards.build(root,ind,root/'out')
            positive=next(c for c in result if c['mechanism']=='active_search' and c['kind']=='positive')
            self.assertEqual(positive['status'],'no_qualifying_observed_chain')
            eligibility=cards.read(root/'out/eligibility.json')[0]
            self.assertTrue(eligibility['eligible']);self.assertFalse(eligibility['positive_outcome_before_bridge_check'])
            self.assertEqual(eligibility['qualification']['new_fp_units'],[['primary','legal_query','correct',2,None]])

    def test_pending_appendix_never_reads_partial_grades(self):
        with tempfile.TemporaryDirectory(dir=cards.report.D) as tmp:
            root=Path(tmp);(root/'independent').mkdir();(root/'independent/results.json').write_text('DO NOT READ')
            result=cards.build_itt(root,root/'independent',root/'out')
            self.assertFalse(result['independent_grades_read']);self.assertEqual(result['cards'],[])

    def test_legal_alarm_label_rename_does_not_create_a_new_context(self):
        binding=dict(eligible=True,fp_units=[['primary','q','correct',1,None]],fp_ids=[['primary','coarse']])
        result=cards.fp_context_comparison(binding,dict(binding,fp_ids=[['primary','renamed_coarse']]))
        self.assertTrue(result['no_new_fp']);self.assertEqual(result['added_units'],[])


if __name__=='__main__':unittest.main()
