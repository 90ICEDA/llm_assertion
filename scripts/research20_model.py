"""Fresh real JSON-mode generation with unchanged model-owned predicates."""
import copy
import json
import research17_model as base
import research15_search_runtime as runtime
from research19_feedback import focus_feedback


def project_feedback(feedback, target):
    full=focus_feedback(feedback,target)
    def side(value):
        return {k:copy.deepcopy(value[k]) for k in ('mode','sample','independent_oracle','sampling_qualification') if k in value}
    pairs=[dict(scenario=p['scenario'],cycle=p['cycle'],fixed=side(p['fixed']),mutant=side(p['mutant']))
           for p in full['paired_target_samples'][:4]]
    legal=[dict(scenario=p['scenario'],cycle=p['cycle'],fixed=side(p['fixed']))
           for p in full['legal_control_failure_samples'][:2]]
    history=[dict(scenario=h['scenario'],target_evidence_count=h['target_evidence_count'],
        fixed_native_failure_count=h['fixed_native_failure_count']) for h in full['historical_observations']]
    result=dict(paired_target_samples=pairs,legal_control_failure_samples=legal,
        historical_observations=history,counts=feedback.get('counts'),
        selection=dict(paired_available=len(full['paired_target_samples']),paired_shown=len(pairs),
            legal_failures_available=len(full['legal_control_failure_samples']),legal_failures_shown=len(legal),
            policy='First actual target pairs and legal failures; summarize repeated historical metadata. Full native replay remains mandatory for admission. Never alter sampled values or oracle judgments.'))
    for key in ('actual_rejection','previous_rejected_proposal','accepted_version_retained'):
        if key in full:result[key]=full[key]
    diagnostic=feedback.get('transport_or_interface_diagnostic',feedback.get('call',{}))
    result['interface_diagnostic']={k:diagnostic[k] for k in ('status','candidate_status','candidate_error') if k in diagnostic}
    result['coverage_samples']=[{k:s[k] for k in ('scenario','independent_check','samples')} for s in feedback.get('coverage_samples',[])[:2]]
    return result


def assemble(value, current):
    """Preserve model-declared many-to-many labels; never infer protection."""
    if value.get('operation') == 'keep':
        return base.assemble(value, current, 'qualified_sampled_v1')
    assert set(value)=={'operation','assertions','reason'}
    assert value['operation'] in ('add','replace') and 1<=len(value['assertions'])<=3
    props = copy.deepcopy((current or {}).get('assertions', [])) if value['operation']=='add' else []
    for item in value['assertions']:
        labels = item['obligation'] if isinstance(item['obligation'], list) else [item['obligation']]
        assert labels and len(set(labels))==len(labels) and set(labels)<=set(base.SPECS)
        if 'property' in item:
            assert set(item)=={'property','obligation'} and isinstance(item['property'],str) and len(item['property'])<=1024
            prop=dict(property=item['property'],reason=value['reason'])
        else:
            temporary = {**item, 'obligation': labels[0]}
            parsed = base.assemble(dict(operation='replace', assertions=[temporary], reason=value['reason']), None, 'qualified_sampled_v1')
            prop = parsed['assertions'][0]
        prop['obligations'] = labels
        props.append(prop)
    return base.native.normalize_candidate(dict(assertions=props, syntax_profile='qualified_sampled_multi_v2'))


class Model(base.Model):
    def __init__(self, out, config):
        super().__init__(out, config)
        self.assemble = assemble
        self.schema=copy.deepcopy(base.SCHEMA)
        item=self.schema['properties']['assertions']['items']
        item['properties']['obligation']={'oneOf':[{'type':'string','enum':list(base.SPECS)},
            {'type':'array','minItems':1,'uniqueItems':True,'items':{'type':'string','enum':list(base.SPECS)}}]}
        if config.get('direct_property'):
            self.schema['properties']['assertions']['items']=dict(type='object',additionalProperties=False,
                required=['property','obligation'],properties=dict(property=dict(type='string',minLength=1,maxLength=1024),
                    obligation=item['properties']['obligation']))
        base.dump(self.out/'model_schema.json',self.schema)

    def transform_request(self, request, current, target, feedback, phase):
        request = copy.deepcopy(request)
        if not feedback.get('actual_native_evidence') and isinstance(feedback.get('native'),dict):
            feedback={**feedback,'actual_native_evidence':feedback['native'].get('feedback',[])}
        context = json.loads(request['messages'][1]['content'])
        task = json.loads(request['messages'][2]['content'])
        context['actual_testbench_and_fault_boundaries'] = runtime.testbench_template(2, 0)
        context['testbench_scope'] = 'Exact shared testbench template; DEPTH/RAM_PIPELINE vary per recorded case. Fault modes are engineering mutations, not historical fixes. The assertion markers are deliberately empty.'
        context['syntax_scope'] = 'Native Boolean expressions, &&, ||, comparisons, $rose/$past in antecedents; $stable/$past in consequents. Exactly one implication selected by timing. Clock/reset wrappers supplied separately. No procedural code or internal DUT signals.'
        context['response_schema'] = dict(operation='keep | add | replace', assertions=[dict(
            antecedent='model-selected Boolean expression', consequent='model-selected Boolean expression',
            timing='same_sample | next_sample', obligation='one confirmed obligation name, or a list of confirmed names if the same property protects them')],
            reason='Explain applicability and how the actual legal/violating samples are handled.')
        task['actual_feedback'] = project_feedback(feedback, target)
        target_modes=sorted({p['mutant']['mode'] for p in task['actual_feedback']['paired_target_samples']})
        if current is None:target_modes=['corrupt']
        context['rtl_before']=dict(shared='rtl_shared',wrapper='actual_testbench_and_fault_boundaries',
            runtime_fault_modes={name:runtime.MODES.index(name) for name in target_modes})
        context['rtl_after']=dict(shared='rtl_shared',wrapper='actual_testbench_and_fault_boundaries',runtime_fault_mode=0)
        context['bug']='The requested obligation is checked against actual paired native observations below. The before wrapper selects the recorded runtime fault modes; the after wrapper selects correct mode 0. Do not substitute a different fault or confuse input presentation with acceptance.'
        task['current_assertions'] = [dict(property=a['property'], obligations=a['obligations']) for a in (current or {}).get('assertions', [])]
        task['requested_obligations'] = feedback.get('requested_obligations', [target])
        task['task'] = ('Generate ONE initial assertion for the requested obligation; use replace.' if current is None else
            'Resolve the requested obligation using the actual development observations. Prefer adding one complementary property while retaining the current accepted set. If replacing, supply the entire new set.')
        task['task'] += (' Return one JSON object with operation, assertions, reason. Keep explanations outside expressions. '
            'Separate the circumstances requiring a check from the value required by that check. '
            'Test applicability on the violating observation as well as legal observations; an assertion that never checks the violation is not a repair. '
            'Use only the provided interface signals. Do not assume constant latency under arbitrary backpressure. '
            'Choose all expressions yourself; the frontend will not repair them. Adding includes only new properties, not copies of retained properties. '
            'Protect all requested_obligations; a single property may declare multiple names when justified, otherwise add complementary properties. Declared labels alone never count as protection: native triggering and violation detection are checked for each obligation. '
            'A previous rejected proposal remains rejected; use its actual diagnostics to revise your proposal.')
        if 'no_unsolicited_output' in task['requested_obligations']:
            task['contract_clarification']='Payload zero is an ordinary data value. An output without an outstanding accepted input is forbidden regardless of its payload value. Reset cancels pending transactions rather than converting them into zero-valued valid outputs.'
        if self.config.get('direct_property'):
            requested=feedback.get('requested_obligations',[target])
            context['confirmed_obligations']={o:base.SPECS[o] for o in requested if o in base.SPECS}
            context['other_obligations_preserved_by_replay']=[o for o in base.SPECS if o not in requested]
            context['response_schema']=dict(operation='keep | add | replace',assertions=[dict(
                property='Complete model-chosen SVA expression containing one |-> or |=>; no clock/reset wrapper',
                obligation='confirmed name or list of confirmed names')],reason='Concise evidence-based explanation')
            task['task']+=' Write only the implication expression in the property field, rather than separate antecedent/consequent/timing fields. The harness supplies the assertion statement, name, clock and reset: do not include property/endproperty, assert, a label, @(posedge clk), disable iff, or a semicolon. No example assertion is supplied. The frontend preserves your full expression.'
        request['format'] = 'json'
        request['messages'] = [dict(role='system', content='Write a native SVA assertion-set edit as JSON. Interpret the supplied RTL, contract and actual observations. You choose predicates and temporal relations. Return only JSON, with concise reason after assertions.'),
            dict(role='user', content=json.dumps(dict(rtl_and_common_contract=context, requested_work=task)))]
        return request
