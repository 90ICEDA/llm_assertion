import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import research194_ablation_interactions as ablation
import research194_case_atlas as atlas


class AblationViewTests(unittest.TestCase):
    def fixture(self,root):
        independent=root/'independent';independent.mkdir()
        rows=[];grades=[];plan={}
        for case in ('arbiter','counter','uart','ibex_flush'):
            plan[case]=dict(faults=['primary'])
            for seed in (19407,19419):
                for arm,(search,refinement) in ablation.ARMS.items():
                    folder=f'fixture/{case}/{seed}/{arm}'
                    rows.append(dict(case_id=case,parent_bug=case+'/parent',seed=seed,search_strategy=search,strategy=refinement,folder=folder,initial_sha256='initial'))
                    grades.append(dict(case_id=case,parent_bug=case+'/parent',fault='primary',folder=folder.replace('/','\\'),
                        target_ids=['t2','t1'] if arm=='A1' else ['t1','t2'],native_complete=True,reference_complete=True,unknown_records=0,
                        unknown_queries=[],no_exposure_queries=[],valid_reachable_fault=True,transaction_detected=1,detected=1,
                        false_positive_records=0,necessary_obligations=['ob'],necessary_obligation_transaction_protection_rate=.5))
        def save():
            for name,value in [('outcome.json',dict(status='completed')),('plan.json',plan),('results.json',grades)]:
                (independent/name).write_text(json.dumps(value))
        save();return rows,grades,plan,save

    def run_build(self,root,rows,qualification=None):
        q=dict(eligible=True,itt_frozen_assignment_eligible=True,request_configuration=dict(model='fixed',temperature=.2,max_tokens=2048))
        with patch.object(ablation.report,'trajectories',return_value=rows),patch.object(ablation.cards,'trajectory_eligibility',side_effect=qualification or (lambda r:copy.deepcopy(q))):
            return ablation.build(root,root/'analysis')

    def test_target_order_and_folder_separators_do_not_change_scope(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            root=Path(tmp);rows,_,_,_=self.fixture(root);result=self.run_build(root,rows)
            self.assertTrue(all(c['itt_eligible'] and c['strict_eligible'] for c in result['cells']))
            self.assertEqual(result['summaries']['intention_to_treat']['fully_paired_parents'],4)

    def test_all_arm_missing_planned_fault_is_not_silently_known(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            root=Path(tmp);rows,_,plan,save=self.fixture(root);plan['counter']['faults'].append('reserved');save()
            cells=self.run_build(root,rows)['cells'];counter=[c for c in cells if c['case_id']=='counter']
            self.assertTrue(all(not c['itt_eligible'] and not c['full_fault_population_known'] for c in counter))
            self.assertIn('missing_arm',next(f for f in counter[0]['faults'] if f['fault']=='reserved')['reasons'])

    def test_unknown_fault_exclusion_and_budget_truncation_have_separate_views(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            root=Path(tmp);rows,grades,plan,save=self.fixture(root)
            plan['counter']['faults'].append('reserved')
            grades.extend(dict(g,fault='reserved',unknown_records=1,unknown_queries=['q']) for g in list(grades) if g['case_id']=='counter');save()
            def qualify(r):return dict(eligible=r['strategy']!='R3',itt_frozen_assignment_eligible=True,request_configuration={'model':'fixed'})
            result=self.run_build(root,rows,qualify);counter=[c for c in result['cells'] if c['case_id']=='counter']
            self.assertTrue(all(c['itt_eligible'] and not c['strict_eligible'] and not c['full_fault_population_known'] for c in counter))
            self.assertEqual(result['summaries']['intention_to_treat']['fully_paired_parents'],4)
            self.assertEqual(result['summaries']['strict_completed']['fully_paired_parents'],0)

    def test_missing_initial_or_mismatched_model_never_qualifies(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            root=Path(tmp);rows,_,_,_=self.fixture(root)
            for r in rows:
                if r['case_id']=='arbiter':r['initial_sha256']=None
            def qualify(r):return dict(eligible=True,itt_frozen_assignment_eligible=True,request_configuration={'model':r['search_strategy']})
            result=self.run_build(root,rows,qualify)
            self.assertTrue(all(not c['itt_eligible'] for c in result['cells']))

    def test_pending_acceptance_does_not_read_results(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            root=Path(tmp);(root/'independent').mkdir();(root/'independent/results.json').write_text('DO NOT READ')
            with self.assertRaisesRegex(ValueError,'not_completed_no_test_reads'):ablation.build(root,root/'out')


class NativeAtlasBindingTests(unittest.TestCase):
    def fixture(self,root):
        folder=root/'native/q0/correct';folder.mkdir(parents=True)
        candidate=[dict(label='chosen',antecedent='req',consequent='ack',timing='same_sample',obligations=['ob'])]
        other=dict(candidate[0],label='c1_a0',consequent='other_ack')
        native=[dict(candidate[0],label='c0_a0'),other]
        source='\n'.join(f'{a["label"]}: assert property (@(posedge clk) (req) |-> ({a["consequent"]})) else $display("ASSERT_FAIL {a["label"]}");' for a in native)
        (folder/'tb.sv').write_text(source)
        (root/'native/protocol.json').write_text(json.dumps(dict(candidate=native,case=dict(candidate_pool=[candidate]))))
        wsl='/mnt/d/'+atlas.ROOT.name+'/'+folder.relative_to(atlas.ROOT).as_posix()
        measurement=dict(candidate_sha256=atlas.digest(candidate),executions=[dict(folder=wsl,query_id='q',variant='correct',result=dict(compile_status='passed',execution_status='completed',source_sha256=hashlib.sha256(source.encode()).hexdigest()))])
        return candidate,measurement,folder

    def test_combined_candidate_and_wsl_path_are_bound_without_other_assertions(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            candidate,measurement,_=self.fixture(Path(tmp));result=atlas.native_sva_record(measurement,candidate)
            self.assertEqual(result['status'],'bound');self.assertEqual(len(result['lines']),1)
            self.assertIn('c0_a0:',result['lines'][0]);self.assertNotIn('other_ack',result['lines'][0])
            self.assertEqual(result['label_mapping'],[dict(native_label='c0_a0',candidate_label='chosen')])

    def test_candidate_mismatch_and_changed_source_do_not_render(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            candidate,measurement,folder=self.fixture(Path(tmp))
            self.assertEqual(atlas.native_sva_record(measurement,[dict(candidate[0],consequent='changed')])['reason'],'candidate_measurement_hash_mismatch')
            (folder/'tb.sv').write_text('modified source')
            result=atlas.native_sva_record(measurement,candidate)
            self.assertEqual(result['status'],'unavailable');self.assertIn('testbench_native_source_hash_mismatch',result['rejected_jobs'])

    def test_unexecuted_compile_and_absent_measurement_are_not_native_sva(self):
        with tempfile.TemporaryDirectory(dir=atlas.D) as tmp:
            candidate,measurement,_=self.fixture(Path(tmp));measurement['executions'][0]['result']['compile_status']='failed'
            self.assertEqual(atlas.native_sva_record(measurement,candidate)['status'],'unavailable')
            self.assertEqual(atlas.native_sva_record(None)['status'],'unavailable')


if __name__=='__main__':unittest.main()
