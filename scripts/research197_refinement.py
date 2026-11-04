"""Opt-in native temporal operators; all expressions/bounds remain model-owned."""
import copy
import json
from research196_component_guard import runtime as guarded_runtime
import research197_cases as cases

OPS={'set_delay','set_window','set_response_window','match_transaction','match_transaction_window','except_when'}

def sample(expression,n):
    if not isinstance(expression,str) or not expression.strip() or type(n) is not int or not 0<=n<=32:raise ValueError('sample_0_to32')
    return cases.past(expression,n)

def install(core,typed_only=False):
    original=core.render_operation;core._sample=sample
    def render(edit):
        common={'op','assertion','field'};op=edit.get('op')
        if op=='set_window':
            if set(edit)!=common|{'expression','min_cycles','max_cycles','quantifier'}:raise ValueError('window_schema')
            lo,hi=edit['min_cycles'],edit['max_cycles']
            if type(lo)is not int or type(hi)is not int or not 0<=lo<=hi<=32 or edit['quantifier'] not in ('any','all'):raise ValueError('window_bounds')
            return edit['field'],'('+(' || ' if edit['quantifier']=='any' else ' && ').join(sample(edit['expression'],n) for n in range(lo,hi+1))+')'
        if op=='set_response_window':
            if set(edit)!=common|{'response','min_cycles','max_cycles','anchor_cycles'} or edit['field']!='consequent':raise ValueError('response_window_schema')
            lo,hi,anchor=edit['min_cycles'],edit['max_cycles'],edit['anchor_cycles']
            if any(type(v)is not int for v in (lo,hi,anchor)):raise ValueError('integer_bounds')
            return edit['field'],cases.response_window(edit['response'],lo,hi,anchor)
        if op=='match_transaction_window':
            keys={'request','request_id','request_data','response_id','response_data','cancel','min_cycles','max_cycles'}
            if set(edit)!=common|keys or edit['field']!='consequent':raise ValueError('matching_window_schema')
            lo,hi=edit['min_cycles'],edit['max_cycles']
            if type(lo)is not int or type(hi)is not int or not 1<=lo<=hi<=8:raise ValueError('matching_window_bounds')
            terms=[]
            for n in range(lo,hi+1):
                active=' && '.join('!'+sample(edit['cancel'],k) for k in range(n))
                terms.append(f"({sample(edit['request'],n)} && (({edit['response_id']}) == {sample(edit['request_id'],n)}) && (({edit['response_data']}) == {sample(edit['request_data'],n)}) && ({active}))")
            return edit['field'],' || '.join(terms)
        if typed_only and op not in OPS:raise ValueError('typed_local_operator_required')
        return original(edit)
    core.render_operation=render;old_contract=core.output_contract
    def contract(stage):
        result=copy.deepcopy(old_contract(stage))
        if stage=='local':
            result['r197_temporal_operations']=dict(
                set_response_window=['assertion','field:consequent','response','min_cycles','max_cycles','anchor_cycles:1..32'],
                match_transaction_window=['assertion','field:consequent','request','request_id','request_data','response_id','response_data','cancel','min_cycles:1..8','max_cycles:1..8'])
            result['r197_semantics']='set_response_window checks no response at ages 1..min-1 and some response at min..max, relative to an EXISTING request antecedent anchored anchor_cycles samples ago. Bounds must agree with that antecedent; the executor does not fix them. match_transaction_window matches a response to an accepted request ID+payload within the supplied age range, with no intervening cancel. It does not prove uniqueness of consumption. set_delay and retrospective set_window support 0..32 samples.'
            result['typed_only']=typed_only
            if typed_only:result['operations_allowed']=sorted(OPS)
        return result
    core.output_contract=contract
    return core

def runtime(arm=None):
    core,runner=guarded_runtime('L' if arm=='T' else arm)
    install(core,typed_only=arm=='T');runner.cases=cases
    original=core.build_request
    def request(*args,**kwargs):
        result=original(*args,**kwargs);context=json.loads(result['messages'][-1]['content'])
        context['experiment']=dict(version='research197',arm=arm or 'main_R0_R3',
            comparison='F/P/T share evidence, fixed labels and R3 history/activity gates; F omits localization, P permits field rewriting, T requires typed local operators.' if arm else 'Registered adaptive S0-S3/R0-R3 trajectory; three model rounds maximum.')
        result['messages'][-1]['content']=json.dumps(context,separators=(',',':'));return result
    core.build_request=request
    return core,runner
