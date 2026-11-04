import unittest
from research195_cost_sections import select_checkpoint

class CostCuts(unittest.TestCase):
    def setUp(self):
        self.points=[dict(round=0,cumulative_tokens=0,candidate_sha256='initial'),
                     dict(round=1,cumulative_tokens=100,candidate_sha256='accepted'),
                     dict(round=2,cumulative_tokens=180,candidate_sha256='accepted'),
                     dict(round=3,cumulative_tokens=300,candidate_sha256='later')]
    def test_over_budget_candidate_is_never_visible(self):
        self.assertEqual(select_checkpoint(self.points,99)['candidate_sha256'],'initial')
        self.assertEqual(select_checkpoint(self.points,299)['candidate_sha256'],'accepted')
    def test_failed_round_cost_is_charged(self):
        self.assertEqual(select_checkpoint(self.points,179)['round'],1)
        self.assertEqual(select_checkpoint(self.points,180)['round'],2)
    def test_zero_and_terminal(self):
        self.assertEqual(select_checkpoint(self.points,0)['round'],0)
        self.assertEqual(select_checkpoint(self.points,1000)['round'],3)
    def test_missing_initial_fails(self):
        with self.assertRaises(ValueError):select_checkpoint(self.points[1:],0)

if __name__=='__main__':unittest.main()
