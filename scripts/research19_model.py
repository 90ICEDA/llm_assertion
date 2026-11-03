"""Reason-first text-expression interface; model still chooses all SVA semantics.

No generated predicate is substituted or repaired. Actual native execution is
the only assertion evaluator used by the enclosing experiment.
"""
import copy
import json
import time
import hashlib
from pathlib import Path
import research17_model as base
from research19_feedback import focus_feedback


class Model(base.Model):
    def __init__(self,out,config):
        super().__init__(out,config)
        self.pending_edits=[]
        if config.get('native_profile'):
            self.assemble=lambda value,current:base.assemble(value,current,'qualified_sampled_v1')
        expression=dict(type='string',minLength=1,maxLength=128)
        # Output ordering lets the model state applicability before choosing
        # predicates. No obligation-specific expression or example is supplied.
        self.schema=dict(type='object',additionalProperties=False,
            required=['reason','operation','assertions'],properties=dict(
                reason=dict(type='string',maxLength=128),
                operation=dict(type='string',enum=['keep','add','replace']),
                assertions=dict(type='array',maxItems=3,items=dict(type='object',additionalProperties=False,
                    required=['antecedent','consequent','timing','obligation'],properties=dict(
                        antecedent=expression,consequent=expression,
                        timing=dict(type='string',enum=['same_sample','next_sample']),
                        obligation=dict(type='string',enum=list(base.SPECS)))))))
        base.dump(self.out/'model_schema.json',self.schema)

    def call(self,folder,current,target,feedback,phase):
        self.contract_draft=None
        if phase=='core_both_mechanisms' and self.pending_edits:
            # Capability upgrades may make an earlier real response executable.
            # Consume every eligible pending response in chronological order;
            # no predicate edits, new transport attempt, or synthetic response.
            source=self.pending_edits.pop(0)
            recorded=base.read(source/'result.json')
            raw=base.read(source/'response.raw.json')['message']['content']
            edit=json.loads(raw)
            if edit!=base.read(source/'model_edit.json'):raise ValueError('archived_model_edit_mismatch')
            if recorded['status']!='response_received' or recorded['candidate_status']!='interface_rejected':
                raise ValueError('not_an_unexecuted_real_response')
            if recorded.get('requested_obligation')!=target:raise ValueError('archived_obligation_mismatch')
            record=dict(status='replayed_actual_prior_response',candidate_status='interface_rejected',
                model_calls=0,retries=0,prompt_tokens=None,completion_tokens=None,phase=phase,
                requested_obligation=target,source=str(source),accounting='Original call remains charged only in source run; this is an automatic syntax-capability retry, not new generation.')
            candidate=None
            try:
                candidate=self.assemble(edit,current)
                record['candidate_status']='assembled_without_semantic_rewrite'
            except Exception as exc:record['candidate_error']=repr(exc)
            base.dump(Path(folder)/'reused_response.json',dict(source=str(source),original_call=recorded,
                hashes={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in ('request.json','response.raw.json','model_edit.json','result.json')},
                edit=edit,selection='All interface-rejected real responses from source core, chronological. No independent outcomes consulted.'))
            base.dump(Path(folder)/'result.json',record)
            if candidate:
                base.dump(Path(folder)/'candidate.json',candidate)
                (Path(folder)/'candidate.sva').write_text(base.native.candidate_sva(candidate))
            return record,candidate
        if self.config.get('contract_planning'):
            used=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in self.calls)
            reserve=2*(self.config['options']['num_ctx']+self.config['options']['num_predict'])
            if len(self.calls)+2>self.config['max_model_calls'] or used+reserve>self.config['max_tokens']:
                raise RuntimeError('insufficient_budget_for_planning_and_generation')
            if time.monotonic()-self.started>=self.config['max_wall_seconds']:
                raise RuntimeError('configured_wall_budget_exhausted')
            focused=focus_feedback(feedback,target)
            samples=[]
            for card in focused['paired_target_samples']:
                samples.append(dict(cycle=card['cycle'],obligation=target,
                    fixed={k:card['fixed'].get(k) for k in ('sample','independent_oracle')},
                    mutant={k:card['mutant'].get(k) for k in ('sample','independent_oracle')}))
            for card in focused['legal_control_failure_samples']:
                samples.append(dict(cycle=card['cycle'],legal_control=True,
                    fixed={k:card['fixed'].get(k) for k in ('sample','independent_oracle')}))
            content=dict(requested_obligation=target,requirement=base.SPECS.get(target),signals=base.SIGNALS,
                existing_obligations=[a['obligations'] for a in (current or {}).get('assertions',[])],
                actual_development_samples=samples,
                scope='Planning only. Full RTL is supplied to the subsequent SVA generation call. This draft is never executed or accepted directly.',
                task='Explain briefly when the requested requirement applies, which observed value it constrains and at what sampling time. Propose an SVA condition using the named signals. Check it against the actual samples if available. If no requested gap exists, say retain existing assertions. Do not infer a new gap without evidence.')
            request=dict(model=self.config['model'],stream=True,options={**self.config['options'],'num_predict':384},
                messages=[dict(role='system',content='Analyze the hardware obligation. Give a concise contract interpretation and proposed assertion; do not discuss unrelated properties.'),
                    dict(role='user',content=json.dumps(content))])
            from research18_context_budget import count
            checked,_=count(request)
            prompt=checked.pop('prompt')
            plan_root=Path(folder).parent/'planning'
            base.dump(plan_root/'context_preflight/result.json',checked)
            (plan_root/'context_preflight/rendered_prompt.txt').write_text(prompt)
            if not checked['fits_with_output_reserve']:raise RuntimeError('planning_context_budget_exceeded')
            record,draft=base.invoke(request,plan_root/'model_call',base.dump,self.digest,timeout=self.config['call_timeout'])
            record.update(phase=phase+'_contract_planning',candidate_status='planning_only_never_native_candidate',
                context_preflight=checked)
            base.dump(plan_root/'model_call/result.json',record)
            self.calls.append(record);base.dump(self.out/'model_cost_running.json',self.calls)
            if record['status']!='response_received':return record,None
            self.contract_draft=draft
        return super().call(folder,current,target,feedback,phase)

    def transform_request(self,request,current,target,feedback,phase):
        request=copy.deepcopy(request)
        context=json.loads(request['messages'][1]['content'])
        task=json.loads(request['messages'][2]['content'])
        task['actual_feedback']=focus_feedback(feedback,target)
        if self.contract_draft is not None:
            task['real_model_contract_draft']=self.contract_draft
            task['draft_status']='Advisory output of a separate real call, not a verified assertion. Check against complete RTL and actual evidence before selecting expressions.'
        task['task'] += (' Write reason first: identify the condition under which this requirement applies '
            'and the value that must hold. Then choose the expressions and timing yourself. '
            'Check your chosen trigger against the supplied target and legal samples. '
            'A condition used for a different obligation is not automatically applicable here. '
            'Do not put implication operators, clock declarations or reset clauses inside expression fields.')
        context['response_schema']=self.schema
        context['syntax_scope']='Text Boolean/comparison/conjunction expressions; sampled functions only in consequent. No disjunction, sequence delays, clock or reset clauses. All predicates and timing selected by model.'
        if self.config.get('native_profile'):
            context['syntax_scope']='Text Boolean expressions including && and ||. $rose and $past are qualified in antecedents; other sampled functions only in consequents. No sequence delays, clock or reset clauses. All predicates and timing selected by model.'
        request['format']=self.schema
        request['messages']=[request['messages'][0],dict(role='user',content=json.dumps(dict(
            rtl_and_common_contract=context,requested_work=task)))]
        return request
