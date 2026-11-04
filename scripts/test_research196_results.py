import copy
import unittest
from research196_results import paired,GROUPS


def rows():
    output=[];arms=set(a for g in GROUPS.values() for a in g.values())
    for case,count,detected in [('small',2,1),('large',200,200)]:
        for seed in (1,2):
            for arm in arms:
                search,strategy=arm.split('_')
                output.append(dict(case_id=case,parent_bug=case,seed=seed,fault='f',search_strategy=search,strategy=strategy,
                    valid_reachable_fault=True,native_complete=True,reference_complete=True,unknown_records=0,
                    target_ids=list(range(count)),transaction_detected=detected,detected=detected,target_transaction_obligations=count,
                    false_positive_records=0,necessary_obligation_transaction_protection_rate=.5))
    return output


class PairedAnalysisTests(unittest.TestCase):
    def test_parents_have_equal_weight_not_failure_cycle_weight(self):
        result=paired(rows());a0=next(r for r in result['summary'] if r['group']=='A' and r['arm']=='A0')
        self.assertEqual(a0['paired_parents'],2);self.assertEqual(a0['transaction_rate'],.75)
        self.assertEqual(result['interactions']['transaction_rate'],0)

    def test_one_unknown_excludes_parent_fault_in_both_seeds_and_all_arms(self):
        data=rows();next(r for r in data if r['case_id']=='large' and r['seed']==2 and r['search_strategy']=='S3' and r['strategy']=='R3')['unknown_records']=1
        result=paired(data)
        for r in result['summary']:
            if r['group']=='A':self.assertEqual(r['paired_parents'],1);self.assertEqual(r['transaction_rate'],.5)

    def test_target_set_mismatch_cannot_be_scored_as_improvement(self):
        data=rows();next(r for r in data if r['case_id']=='small' and r['seed']==1 and r['search_strategy']=='S3' and r['strategy']=='R3')['target_ids']=[99]
        result=paired(data)
        self.assertTrue(any('target_mismatch' in c['reasons'] for c in result['cells']))
        self.assertEqual(next(r for r in result['summary'] if r['group']=='A' and r['arm']=='A3')['paired_parents'],1)

    def test_necessary_protection_combines_faults_without_erasing_a_miss(self):
        data=rows();extra=[]
        for r in data:
            r.update(necessary_obligations=['a','b'],exposed_obligations=['a'],fully_transaction_protected_exposed_obligations=['a'])
            other=copy.deepcopy(r);other.update(fault='g',exposed_obligations=['b'],fully_transaction_protected_exposed_obligations=['b']);extra.append(other)
        result=paired(data+extra)
        self.assertEqual(next(r for r in result['summary'] if r['group']=='A' and r['arm']=='A0')['necessary_obligation_rate'],1)
        for r in extra:r.update(exposed_obligations=['a'],fully_transaction_protected_exposed_obligations=[])
        result=paired(data+extra)
        self.assertEqual(next(r for r in result['summary'] if r['group']=='A' and r['arm']=='A0')['necessary_obligation_rate'],0)


if __name__=='__main__':unittest.main()
