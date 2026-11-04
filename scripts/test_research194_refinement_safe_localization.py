"""Regression controls for the isolated adapter; not experiment outcomes."""
import copy
import unittest
import research194_refinement as old
from research194_refinement_safe_localization import safe_localize

C=[dict(label='a',antecedent='en',consequent='q',timing='same_sample',obligations=['step'])]

def ev(eid,obligation,label,trigger,failure):
    return dict(id=eid,obligation=obligation,label=label,status='confirmed',
        assertions=[dict(assertion='a',obligations=['step'],trigger=trigger,failure=failure)])


class SafeLocalizationTests(unittest.TestCase):
    def test_null_legal_alarm_retained_without_permission(self):
        evidence=[ev('unmapped',None,'legal',True,True)];snapshot=copy.deepcopy(evidence)
        with self.assertRaises(TypeError):old.localize(C,evidence)
        result=safe_localize(C,evidence)
        self.assertEqual(evidence,snapshot);self.assertEqual(result['evidence'],snapshot)
        self.assertEqual(result['status'],'partial_unknown');self.assertEqual(result['actionable_findings'],[])
        self.assertEqual(result['unmapped_localizations'][0]['oracle_label'],'legal')
        self.assertEqual(result['unmapped_localizations'][0]['editable_fields'],[])
        self.assertTrue(result['withheld_hypotheses']);self.assertEqual(result['evidence_records_dropped'],0)

    def test_unmapped_observed_trigger_prevents_false_inactivity(self):
        evidence=[ev('target','step','violation',False,False),ev('unmapped',None,'legal',True,True)]
        result=safe_localize(C,evidence)
        kinds={f['kind'] for f in result['actionable_findings']}
        self.assertIn('trigger_too_narrow',kinds);self.assertNotIn('finite_inactivity',kinds)
        self.assertEqual(len(result['evidence']),2)

    def test_ordinary_inputs_keep_original_findings(self):
        evidence=[ev('target','step','violation',False,False)]
        result=safe_localize(C,evidence)
        self.assertEqual(result['actionable_findings'],old.localize(C,evidence))
        self.assertEqual(result['unmapped_localizations'],[])

    def test_other_unmapped_types_do_not_invent_obligations(self):
        for value in ('',[],17):
            result=safe_localize(C,[ev('x',value,'legal',True,True)])
            self.assertEqual(result['unmapped_localizations'][0]['obligation'],value)
            self.assertEqual(result['actionable_findings'],[])


if __name__=='__main__':unittest.main()
