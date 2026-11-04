"""Opt-in local-first automatic refinement. Sealed predecessors stay unchanged."""
import copy
import json
from research197_refinement import runtime as previous_runtime, OPS


def runtime(policy='local_first'):
    if policy not in ('feedback', 'legacy', 'local_first'):
        raise ValueError('unknown_policy')
    core, runner = previous_runtime()
    if policy == 'local_first':
        # Use the corrected typed contract inside the automatic controller,
        # without the isolated T controller that disables fallback.
        from research197_refinement import install
        install(core, typed_only=True)
        old_contract = core.output_contract
        def contract(stage):
            value = copy.deepcopy(old_contract(stage))
            if stage != 'local':
                return value
            value['operations'] = {k:v for k,v in value['operations'].items() if k in OPS}
            value['operations'].update(value.pop('r197_temporal_operations'))
            value['operations']['set_delay'] = ['assertion','field','expression','cycles:integer 0..32']
            value['operations']['set_window'] = ['assertion','field','expression','min_cycles:integer 0..32','max_cycles:integer 0..32','quantifier:any|all']
            value['operations_allowed'] = sorted(OPS)
            value['schema'] = {'edits':'Array of 1..4 objects with op and exactly its listed operands.','reason':'string'}
            value['rule'] = 'Choose every operand yourself. Only localized fields may change. Labels and obligation mappings are immutable. No arbitrary field replacement.'
            return value
        core.output_contract = contract
    base = core.Controller
    class Controller(base):
        def __post_init__(self):
            limit = self.max_rounds
            if not 1 <= limit <= 5:
                raise ValueError('call_limit_1_to5')
            self.max_rounds = min(limit,3)
            super().__post_init__()
            self.max_rounds = limit
            self.local_priority_log = []

        def consider_empty_domain(self, measurement):
            if policy != 'local_first' or self.strategy != 'R3' or self.stage != 'local':
                return super().consider_empty_domain(measurement)
            if measurement.get('candidate_sha256') != core.digest(self.active):
                raise ValueError('domain_certificate_candidate_binding')
            if (measurement.get('native_complete') is not True or
                measurement.get('reference_complete') is not True or
                measurement.get('critical_unknown') or not measurement.get('native_bindings')):
                return None
            findings = core.localize(self.active, measurement['evidence'], self.localization_enabled)
            if findings:
                self.local_priority_log.append(dict(candidate_sha256=core.digest(self.active),
                    measurement_sha256=core.digest(measurement), decision='attempt_existing_local_fields_first',
                    fields=sorted({(f['assertion'],f['field']) for f in findings}),
                    evidence_ids=sorted({eid for f in findings for eid in f['evidence_ids']})))
                return None
            return super().consider_empty_domain(measurement)
    core.Controller = Controller
    old_request = core.build_request
    def request(*args, **kwargs):
        value = old_request(*args, **kwargs)
        context = json.loads(value['messages'][-1]['content'])
        ctl = args[1] if len(args)>1 else kwargs['controller']
        context['experiment'] = dict(version='research198', policy=policy,
            evidence='Fixed, already acquired development query union; identical within each search/case/seed block.',
            budget='At most five calls in every arm; identical model parameters. Transport is never retried.',
            fallback='Only changed, natively measured, confirmed semantic failures authorize stage escalation. Interface errors consume calls without escalation. Never intentionally propose a bad repair to exercise a branch.')
        if policy == 'local_first':
            context['local_priority'] = ctl.local_priority_log[-1:]
            context['operation_selection'] = {
                'latency_window':'set_delay, set_window or set_response_window according to the specification and trigger anchor',
                'transaction_matching':'match_transaction or match_transaction_window',
                'legal_exception':'except_when',
                'note':'These are hypotheses, not a prescribed repair. Native replay and history/activity gates decide acceptance.'}
        value['messages'][-1]['content'] = json.dumps(context,separators=(',',':'))
        return value
    core.build_request = request
    return core, runner
