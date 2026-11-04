"""Freeze guards, using temporary development-only fixtures; zero native jobs."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import research194_independent as a


class FreezeGuards(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=a.ROOT/'deliverables')
        self.folder=Path(self.temp.name);self.registration=self.folder/'registration.json'
        self.rows=[]
        for strategy in ('R0','R1'):
            e=dict(id='fixture/'+strategy,case_id='arbiter',seed=19407,search_strategy='S0',strategy=strategy)
            folder=self.folder/strategy;candidate=a.cases.get_case('arbiter')['initial']
            a.cases.dump(folder/'frozen.json',candidate)
            a.cases.dump(folder/'outcome.json',dict(**{k:v for k,v in e.items() if k!='id'},status='frozen',provenance='real_remote_model',frozen_sha256=a.cases.digest(candidate)))
            self.rows.append(dict(**e,folder=str(folder.relative_to(a.ROOT))))
        self.source=self.folder/'source';self.source.write_text('fixed')
        a.cases.dump(self.registration,dict(entries=[{k:v for k,v in e.items() if k!='folder'} for e in self.rows],source_bindings={str(self.source):a.sha(self.source)}))
        self.reg_patch=patch.object(a,'REGISTRATION',self.registration);self.reg_patch.start()

    def tearDown(self):self.reg_patch.stop();self.temp.cleanup()

    def test_success_has_initial_control_and_no_test_access(self):
        with patch.object(a.cases,'query_pool',side_effect=AssertionError('no test construction during freeze')):
            a.freeze(self.rows,2,self.folder/'freeze.json')
        result=a.read(self.folder/'freeze.json')
        self.assertEqual(len(result['controls']),1);self.assertEqual(result['registration_sha256'],a.sha(self.registration))

    def test_duplicate_folder_cannot_fill_population(self):
        rows=copy.deepcopy(self.rows);rows[1]['folder']=rows[0]['folder']
        with self.assertRaisesRegex(ValueError,'duplicate_trajectory_folder'):a.freeze(rows,2,self.folder/'freeze.json')

    def test_identity_mismatch_is_rejected(self):
        path=a.ROOT/self.rows[0]['folder']/'outcome.json';value=a.read(path);value['seed']=999;a.cases.dump(path,value)
        with self.assertRaisesRegex(ValueError,'terminal_identity_mismatch'):a.freeze(self.rows,2,self.folder/'freeze.json')

    def test_source_change_is_rejected(self):
        self.source.write_text('changed')
        with self.assertRaisesRegex(ValueError,'preregistered_source_changed'):a.freeze(self.rows,2,self.folder/'freeze.json')

    def test_missing_arm_is_rejected(self):
        rows=copy.deepcopy(self.rows);rows[1]['id']='replacement'
        with self.assertRaisesRegex(ValueError,'registered_population_mismatch'):a.freeze(rows,2,self.folder/'freeze.json')


if __name__=='__main__':unittest.main()
