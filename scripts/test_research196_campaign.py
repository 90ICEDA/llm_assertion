import copy
from pathlib import Path
import tempfile
import unittest
import research194_refinement_runner as common
from research196_campaign import adapter_runtime
from research196_active_search import Session
import research196_cases as cases
from research196_independent import NEW_FAULTS
import research194_ibex as ibex


class CampaignTests(unittest.TestCase):
    def test_reserved_sites_unique_and_separate(self):
        ibex.register()
        for cid,mutant in NEW_FAULTS.items():
            source=(ibex.SOURCE/'after/ibex_compressed_decoder.sv') if cid=='ibex_flush' else common.ROOT/cases.get_case(cid)['sources'][mutant.get('file',0)]
            self.assertEqual(source.read_text(encoding='utf-8').count(mutant['search']),1,cid)
            self.assertNotIn(mutant['site'],{f['site'] for f in cases.old.FAULTS[cid]})

    def test_private_runtime_does_not_mutate_legacy(self):
        old_gate=common.r.gate;old_cases=common.cases
        core,runner=adapter_runtime()
        self.assertIsNot(core,common.r);self.assertIs(runner.cases,cases)
        self.assertIs(common.r.gate,old_gate);self.assertIs(common.cases,old_cases)

    def test_paid_selection_replays_without_native_or_model_calls(self):
        root=common.ROOT/'deliverables/research196_first_acquisitions_20261103_r01'
        p=common.read(root/'protocol.json');progress=common.read(root/'progress.json')
        self.assertGreater(len(progress),0)
        with tempfile.TemporaryDirectory() as temp:
            for index,e in enumerate(progress):
                base=common.read(p['baselines'][e['case_id']]);record=common.read(e['path'])
                session=Session(e['case_id'],e['strategy'],e['seed'],Path(temp)/str(index),initial_queries=base['queries'],
                    initial_evidence=base['measurement']['evidence'],max_queries=2,adapter=cases,cost_model=p['cost_models'][e['case_id']],wall_budget=120)
                reused=session.reuse_acquisition(copy.deepcopy(record),cases.get_case(e['case_id'])['initial'])
                self.assertEqual(reused['cost']['native_execution_attempts'],0)
                self.assertEqual(reused['cost']['r196_total_seconds'],record['cost']['r196_total_seconds'])


if __name__=='__main__':unittest.main()
