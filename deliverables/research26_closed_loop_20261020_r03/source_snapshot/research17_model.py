"""Real-model assertion-set edits with schema-constrained syntax, not templates."""
import copy
import hashlib
import json
import re
import time
import urllib.request
from pathlib import Path

import research15_native_interface as native
import research_native_closed_loop as source
from research_native_model import invoke

ROOT=native.ROOT
SIGNALS=dict(svalid='Input request presented; acceptance also requires sready.',
    sready='Input acceptance readiness.',sdata='Current presented input payload.',
    mvalid='Output response present.',mready='Output acceptance readiness.',mdata='Current output payload.',
    ref_count='Count of accepted, noncancelled inputs awaiting output acceptance; pre-NBA current sample.',
    ref_expected='Oldest outstanding accepted input payload; meaningful when ref_count>0.',
    drain_due='Environment checkpoint after >=18 continuously output-ready, input-idle cycles in supported parameters.')
SPECS=dict(order_payload='At an accepted output, with an outstanding input, the output payload equals the oldest accepted input payload at that same sample.',
    drain_no_loss='At a fair-drain checkpoint, the outstanding accepted-input count must be zero at that same sample. This requirement also applies when no output is presented or accepted.',
    no_unsolicited_output='Every accepted output must have an outstanding input since the latest reset.',
    stall_stability='Presented valid output and data remain stable during backpressure, except reset.',
    reset_cancellation='Reset cancels all pending accepted transactions; cancelled transactions must not reappear.')
# A declared conjunction/comparison expression subset. The schema excludes
# temporal-token characters inside expressions; temporal choice is separate.
# No predicate, signal combination or comparison value is preselected.
EXPRESSION=dict(type='string',minLength=1,maxLength=512,pattern=r"^[a-zA-Z0-9_ ()!<>=&$.'\[\],:+*/%?-]+$")
SCHEMA=dict(type='object',additionalProperties=False,required=['operation','assertions','reason'],properties=dict(
    operation=dict(type='string',enum=['keep','add','replace']),reason=dict(type='string'),
    assertions=dict(type='array',maxItems=3,items=dict(type='object',additionalProperties=False,
        required=['antecedent','consequent','timing','obligation'],properties=dict(
            antecedent=EXPRESSION,consequent=EXPRESSION,
            timing=dict(type='string',enum=['same_sample','next_sample']),
            obligation=dict(type='string',enum=list(SPECS)))))))


def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def structured(candidate):
    return [dict(antecedent=a['derived_antecedent'],consequent=a['consequent'],
        timing='same_sample' if a['derived_delay']==0 else 'next_sample',obligation=a['obligations'][0])
        for a in (candidate or {}).get('assertions',[])]


def assemble(value,current,syntax_profile=None):
    assert isinstance(value,dict) and set(value)=={'operation','assertions','reason'},'invalid_edit_schema'
    operation=value['operation'];items=value['assertions']
    assert isinstance(items,list) and len(items)<=3 and isinstance(value['reason'],str),'invalid_edit_fields'
    if operation=='keep':
        assert current and not items,'keep_requires_existing_set_and_empty_edits'
        return copy.deepcopy(current)
    assert operation in ('add','replace') and items,'nonempty_edit_required'
    props=[]
    for item in items:
        assert set(item)=={'antecedent','consequent','timing','obligation'},'invalid_assertion_fields'
        ant,cons=item['antecedent'],item['consequent']
        pattern=EXPRESSION['pattern'].replace('()!','()!|') if syntax_profile=='qualified_sampled_v1' else EXPRESSION['pattern']
        assert all(isinstance(x,str) and 1<=len(x)<=512 and re.fullmatch(pattern,x) for x in (ant,cons)),'expression_outside_declared_subset'
        assert item['obligation'] in SPECS,'unknown_obligation'
        checked=(ant+cons).replace('||','') if syntax_profile=='qualified_sampled_v1' else ant+cons
        assert not any(token in checked for token in ('|','##',';','`')),'non_boolean_expression_subset'
        op={'same_sample':'|->','next_sample':'|=>'}[item['timing']]
        props.append(dict(property=f'({ant}) {op} ({cons})',obligations=[item['obligation']],reason=value['reason']))
    if operation=='add':props=copy.deepcopy((current or {}).get('assertions',[]))+props
    assembled=dict(assertions=props)
    if syntax_profile:assembled['syntax_profile']=syntax_profile
    return native.normalize_candidate(assembled)


class Model:
    def transform_request(self, request, current, target, feedback, phase):
        """Optional experiment-specific presentation; no semantic assembly edits."""
        return request

    def __init__(self,out,config):
        self.out=Path(out);self.config=config
        self.calls=[];self.started=time.monotonic()
        self.ast_mode=config.get('expression_format')=='ast'
        if self.ast_mode:
            import research17_model_schema as grammar
            self.schema=grammar.schema();self.assemble=grammar.normalize
        else:self.schema=SCHEMA;self.assemble=assemble
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=10))
        self.digest=next(m['digest'] for m in tags['models'] if m['name']==config['model'])
        dump(self.out/'model_tags.json',tags)
        dump(self.out/'model_schema.json',self.schema)
        if config.get('preflight_tokens'):
            # Empty-prompt load is a model-management operation, not generation.
            # Preflight endpoints disappear when Ollama unloads an idle runner.
            request=dict(model=config['model'],prompt='',stream=False,keep_alive='30m',options=config['options'])
            dump(self.out/'model_load/request.json',request)
            started=time.monotonic()
            req=urllib.request.Request('http://127.0.0.1:11434/api/generate',
                data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
            response=json.load(urllib.request.urlopen(req,timeout=120))
            dump(self.out/'model_load/response.json',response)
            dump(self.out/'model_load/result.json',dict(wall_seconds=time.monotonic()-started,
                management_calls=1,generation_calls=0 if response.get('response','')=='' else None,
                actual_response=response,scope='Cold-runner loading only; not an SVA generation or repair.'))
            if response.get('response','')!='' or not response.get('done'):
                raise RuntimeError('unexpected_model_load_response')

    def call(self,folder,current,target,feedback,phase):
        used=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in self.calls)
        if len(self.calls)>=self.config['max_model_calls'] or used>=self.config['max_tokens']:
            raise RuntimeError('configured_model_budget_exhausted')
        if time.monotonic()-self.started>=self.config['max_wall_seconds']:
            raise RuntimeError('configured_wall_budget_exhausted')
        context=dict(rtl_shared=source.RTL.read_text(),
            rtl_before={'shared':'rtl_shared','boundary':"assign mdata = raw_data ^ 32'h1; assign mvalid = raw_valid;"},
            rtl_after={'shared':'rtl_shared','boundary':'assign mdata = raw_data; assign mvalid = raw_valid;'},
            provenance='Actual axis_fifo with artificial output-boundary faults, not an upstream historical bug.',
            bug='Output corruption violates accepted-input/output ordering. Related boundary faults may drop, duplicate or resurrect cancelled output.',
            clock_reset='posedge clock, active-high synchronous reset cancels transactions; SVA sampled pre-NBA, disable iff(rst). No fixed latency during arbitrary backpressure.',
            signals=SIGNALS,confirmed_obligations=SPECS,reference_rtl=native.REFERENCE,
            temporal_semantics={'same_sample':'Consequent checked on antecedent edge (overlapped implication).',
                                'next_sample':'Consequent checked on the next edge (nonoverlapped implication).'},
            syntax_scope='Native SVA assembled from model-chosen Boolean comparisons/conjunctions and a model-chosen temporal relation. No disjunction or sequence-delay syntax in this frontend.')
        if current is None:
            task='Generate ONE initial assertion for the requested obligation. Choose replace. Determine both Boolean expressions and timing from the specification. No other obligation is requested.'
        elif target is None:
            task='Review current accepted assertions with the supplied ordinary feedback. If there is no confirmed gap, choose keep with empty assertions. Otherwise propose edits. Do not invent unobserved failures.'
        else:
            task='Repair the requested obligation using the actual evidence. Prefer adding ONE complementary assertion when existing assertions protect other obligations; add includes ONLY new assertions. You may instead replace the complete set, but historical protection is checked. Consider when the violation can occur without an output handshake. Do not use a signal as a trigger merely because another obligation uses it.'
            task+=' If a rejected proposal is supplied, do not repeat that failed proposal. Use the actual legal and violating samples to choose when the requested requirement applies. Preserve existing protection.'
        if self.ast_mode:
            context['syntax_scope']='Choose expressions as AST objects: {signal: name}, {int: integer}, or {op: operator, args: expression array}. All predicates and timing are yours. Existing assertions are shown as text for reference only. Temporal implication is selected only by timing. No raw SVA strings in AST fields.'
            context['response_schema']=self.schema
            context['expression_style']='Use simple expressions with only the operators needed by the obligation. Do not include explanations in expressions; put a short explanation in reason.'
        request=dict(model=self.config['model'],stream=True,format=self.schema,options=self.config['options'],messages=[
            dict(role='system',content='Synthesize a structured native SVA edit from the RTL contract and real diagnostics. Return the schema exactly. You choose every predicate and its sampling relation; syntax assembly does not repair semantic mistakes.'),
            dict(role='user',content=json.dumps(context)),
            dict(role='user',content=json.dumps(dict(phase=phase,current_assertions=structured(current),
                actual_feedback=feedback,requested_obligation=target,requested_specification=SPECS.get(target),task=task)))])
        request=self.transform_request(request,current,target,feedback,phase)
        # Reserve a conservative context+output bound before another request.
        reserve=self.config['options']['num_ctx']+self.config['options']['num_predict']
        if used+reserve>self.config['max_tokens']:raise RuntimeError('insufficient_remaining_token_reserve')
        preflight=None
        if self.config.get('preflight_tokens'):
            from research18_context_budget import count
            preflight,_=count(request)
            prompt=preflight.pop('prompt')
            # Do not create the transport directory before invoke (exclusive).
            audit=Path(folder).parent/'context_preflight'
            dump(audit/'result.json',preflight)
            (audit/'rendered_prompt.txt').write_text(prompt)
            if preflight['fits_with_output_reserve'] is not True:
                dump(audit/'rejected_request.json',request)
                result=dict(status='context_budget_rejected_before_generation',model_calls=0,
                    candidate_status='not_generated',phase=phase,preflight=preflight)
                dump(audit/'decision.json',result)
                return result,None
        result,content=invoke(request,Path(folder),dump,self.digest,timeout=self.config['call_timeout'])
        if preflight is not None:
            observed=result.get('prompt_tokens')
            result['context_preflight']=dict(**preflight,observed_prompt_tokens=observed,
                observed_minus_rendered=(observed-preflight['rendered_prompt_tokens']) if observed is not None else None)
            # Large differences can indicate dropped messages or truncation.
            if observed is not None and abs(observed-preflight['rendered_prompt_tokens'])>preflight['wrapper_margin_tokens']:
                result.update(status='context_rendering_mismatch',candidate_status='not_evaluated')
        candidate=None;value=None
        if result['status']=='response_received':
            try:
                value=json.loads(content);dump(Path(folder)/'model_edit.json',value)
                candidate=self.assemble(value,current)
                result['candidate_status']='assembled_without_semantic_rewrite'
            except Exception as exc:result.update(candidate_status='interface_rejected',candidate_error=repr(exc))
        if candidate:
            dump(Path(folder)/'candidate.json',candidate)
            (Path(folder)/'candidate.sva').write_text(native.candidate_sva(candidate))
        result.update(phase=phase,requested_obligation=target,operation=value.get('operation') if isinstance(value,dict) else None,
            model_owns_predicates_and_timing=True,syntax_assembly_only=True)
        dump(Path(folder)/'result.json',result)
        self.calls.append(result);dump(self.out/'model_cost_running.json',self.calls)
        return result,candidate
