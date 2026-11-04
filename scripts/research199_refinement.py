"""Factorial routing x contract, with common retained-candidate composition gate."""
import copy
import json
from research198_refinement import runtime as previous
from research198_active_obligation_fix import active_uncovered
from research197_refinement import OPS

ARMS={
 'B0':dict(cohort='factorial',routing='legacy',contract='generic',strategy='R3',search='S3'),
 'B1':dict(cohort='factorial',routing='local_first',contract='generic',strategy='R3',search='S3'),
 'B2':dict(cohort='factorial',routing='legacy',contract='typed',strategy='R3',search='S3'),
 'B3':dict(cohort='factorial',routing='local_first',contract='typed',strategy='R3',search='S3'),
 'A0':dict(cohort='online',routing='legacy',contract='generic',strategy='R1',search='S0'),
 'A1':dict(cohort='online',routing='legacy',contract='generic',strategy='R1',search='S3'),
 'A2':dict(cohort='online',routing='local_first',contract='typed',strategy='R3',search='S0'),
 'A3':dict(cohort='online',routing='local_first',contract='typed',strategy='R3',search='S3')}

def runtime(arm):
    spec=ARMS[arm];core,runner=previous(spec['routing'])
    typed,_=previous('local_first');generic,_=previous('legacy')
    render=typed.render_operation if spec['contract']=='typed' else generic.render_operation
    def render_checked(edit):
        allowed=OPS if spec['contract']=='typed' else {'replace_field'}
        if edit.get('op') not in allowed:raise ValueError('registered_local_contract_required')
        return render(edit)
    core.render_operation=render_checked
    old_contract=core.output_contract
    def contract(stage):
        if stage!='local':return old_contract(stage)
        if spec['contract']=='typed':return copy.deepcopy(typed.output_contract('local'))
        return dict(schema={'edits':'Array of 1..4 objects with op, assertion, field, value.','reason':'string'},
            operations={'replace_field':['assertion','field:antecedent|consequent|timing','value:string']},
            operations_allowed=['replace_field'],typed_only=False,
            rule='Replace only localized fields on existing assertions. Labels and obligation mappings are immutable. Supply complete SVA expressions; no new labels or whole-assertion replacement.')
    core.output_contract=contract
    parent=core.Controller
    class Controller(parent):
        def parse(self,response,evidence,validate):
            if self.strategy!='R3' or self.stage!='compose':return super().parse(response,evidence,validate)
            if self.finished or self.rounds>=self.max_rounds:raise ValueError('controller_terminal_or_budget')
            return core.apply_patch(self.active,response,core.localize(self.active,evidence,self.localization_enabled),validate,
                self.stage,self.receipt,active_uncovered(core,self.active,evidence))
    core.Controller=Controller
    old_request=core.build_request
    def request(*args,**kwargs):
        value=old_request(*args,**kwargs);ctx=json.loads(value['messages'][-1]['content'])
        ctx.pop('local_priority',None);ctx.pop('operation_selection',None)
        ctx['experiment']=dict(version='research199',arm=arm,**spec,
            evidence='Identical fixed S3 development evidence within factorial blocks; online blocks reacquire using the retained current candidate.',
            budget='At most three model calls; failures consume rounds. No transport retries.',
            fallback='Native confirmed failure or a source-bound structural certificate only. Never propose an intentionally bad repair to manufacture branch traversal.')
        value['messages'][-1]['content']=json.dumps(ctx,separators=(',',':'));return value
    core.build_request=request
    return core,runner
