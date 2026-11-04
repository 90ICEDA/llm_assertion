import unittest
from research194_report import cross_design_table


def grade(fault, protected, unknown=0):
    return dict(case_id='counter', search_strategy='S0', strategy='R3',
        parent_bug='counter/artificial', historical_fix_confirmed=False,
        id='base/counter/19407/S0_R3',fault=fault,native_complete=True,
        reference_complete=True,valid_reachable_fault=True,unknown_records=unknown,
        fault_kind='unseen_fault_at_reserved_site',necessary_obligations=['step','boundary'],
        exposed_obligations=['step'],fully_transaction_protected_exposed_obligations=protected,
        target_ids=['one'],target_transaction_obligations=1,misses=int(not protected),
        transaction_misses=int(not protected),transaction_detected=int(bool(protected)),
        false_positive_records=0,no_exposure_queries=['reset'],full_planned_transaction_scope_pass=False)


class CrossDesignMetrics(unittest.TestCase):
    def test_same_obligation_failure_in_any_fault_prevents_full_protection(self):
        row=cross_design_table([grade('a',['step']),grade('b',[])])[0]
        self.assertEqual(row['necessary_obligation_protection_rate'],0)
        self.assertEqual(row['versions'],1)
        self.assertEqual(row['unseen_known_version_faults'],2)

    def test_unexposed_obligation_stays_in_denominator(self):
        row=cross_design_table([grade('a',['step'])])[0]
        self.assertEqual(row['necessary_obligation_protection_rate'],0.5)
        self.assertEqual(row['full_scope_passed_version_faults'],0)

    def test_unknown_not_reported_as_zero_or_pass(self):
        row=cross_design_table([grade('a',['step']),grade('b',['step'],1)])[0]
        self.assertIsNone(row['necessary_obligation_protection_rate'])
        self.assertEqual(row['unknown_version_faults'],1)
        self.assertEqual(row['all_faults_known_versions'],0)


if __name__=='__main__':unittest.main()
