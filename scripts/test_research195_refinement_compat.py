"""Synthetic tests of the unsealed metadata adapter; no native/model calls."""
import copy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import research195_refinement_independent_compat as compat


class MetadataCompatibilityTests(unittest.TestCase):
    def exercise(self, mutated=False):
        query={'id':'synthetic_query','rows':[{'cycle':0,'ready':1}], 'constraints':['synthetic']}
        untouched=copy.deepcopy(query)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);failed=folder/'failed'
            compat.common.dump(failed/'plan.json',{'queries':{'synthetic':[query]}})
            generated=copy.deepcopy(query)
            if mutated:generated['rows'][0]['ready']=0
            fake=SimpleNamespace(__file__=__file__,generate=lambda case,seed:copy.deepcopy(generated))
            captured=[]
            def run(prepared,execution,out):
                captured.append(fake.generate('synthetic',7))
            fake.run=run
            with patch.object(compat,'clone',return_value=fake):
                if mutated:
                    with self.assertRaisesRegex(ValueError,'query_changed_from_failed_registered_plan'):
                        compat.run(folder/'prepared',folder/'execution',failed,folder/'out',folder/'audit')
                    self.assertEqual(captured,[])
                    return
                compat.run(folder/'prepared',folder/'execution',failed,folder/'out',folder/'audit')
            self.assertEqual(query,untouched)
            self.assertEqual({k:v for k,v in captured[0].items() if k!='semantic_key'},query)
            self.assertEqual(captured[0]['semantic_key'],compat.common.r.digest(query['rows']))
            diff=compat.common.read(folder/'audit/query_metadata_diff.json')
            self.assertTrue(diff[0]['all_original_fields_identical'])
            self.assertEqual(compat.common.read(folder/'audit/outcome.json')['new_model_calls'],0)

    def test_only_derived_metadata_added(self):self.exercise()

    def test_changed_rows_rejected_before_acceptance(self):self.exercise(mutated=True)


if __name__=='__main__':unittest.main()
