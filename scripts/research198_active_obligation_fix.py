"""Correct composition permission to use the retained candidate's evidence.

Never edit the sealed R198 campaign. This adapter changes only parser permission
at composition, not prompts, operations, native verdicts or acceptance gates.
"""
from research198_refinement import runtime as original_runtime

def active_uncovered(core,candidate,evidence):
    records=core.normalize_evidence(evidence);h=core.digest(candidate)
    if any(r.get('candidate_sha256')!=h for r in records):
        raise ValueError('composition_evidence_not_bound_to_retained_candidate')
    observed={r['obligation'] for r in records if r['status']=='confirmed' and r['label']=='violation' and r.get('obligation') and r.get('counted_target',True)}
    covered={r['obligation'] for r in records if r['status']=='confirmed' and r['label']=='violation' and r.get('obligation')
        and (r.get('detection_status')=='timely' or any(a.get('failure') is True for a in r['assertions']))}
    return observed-covered

def runtime(policy='local_first'):
    core,runner=original_runtime(policy);base=core.Controller
    class Controller(base):
        def parse(self,response,evidence,validate):
            if self.strategy!='R3' or self.stage!='compose':return super().parse(response,evidence,validate)
            if self.finished or self.rounds>=self.max_rounds:raise ValueError('controller_terminal_or_budget')
            uncovered=active_uncovered(core,self.active,evidence)
            return core.apply_patch(self.active,response,core.localize(self.active,evidence,self.localization_enabled),
                validate,self.stage,self.receipt,uncovered)
    core.Controller=Controller
    return core,runner
