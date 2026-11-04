import unittest
from research196_cost_sections import select


class CostPrefixTests(unittest.TestCase):
    def setUp(self):
        self.points=[dict(round=0,tokens=0,service_seconds=0,candidate_sha256='initial'),
            dict(round=1,tokens=100,service_seconds=80,candidate_sha256='accepted1'),
            dict(round=2,tokens=220,service_seconds=150,candidate_sha256='accepted2')]

    def test_exceeding_call_never_grants_candidate(self):
        self.assertEqual(select(self.points,'tokens',219)['candidate_sha256'],'accepted1')
        self.assertEqual(select(self.points,'tokens',220)['candidate_sha256'],'accepted2')

    def test_unknown_cost_never_counts_as_zero(self):
        self.points[2]['tokens']=None
        self.assertEqual(select(self.points,'tokens',10000)['candidate_sha256'],'accepted1')

    def test_axes_are_distinct(self):
        self.assertEqual(select(self.points,'service_seconds',155)['candidate_sha256'],'accepted2')
        self.assertEqual(select(self.points,'tokens',155)['candidate_sha256'],'accepted1')


if __name__=='__main__':unittest.main()
