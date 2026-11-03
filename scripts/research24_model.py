"""Lexically constrained local edits, without supplying any property answer."""
import json
import re
from pathlib import Path
import hashlib
from research23_model import Model as PreviousModel, edit_schema
import research17_model as base


def lexical_schema():
    schema = edit_schema()
    # Same public signals as the native frontend; decimal constants and
    # Boolean/arithmetic punctuation remain freely chosen by the model.
    names = list(base.SIGNALS) + ['$past', '$stable', '$rose', '$fell',
        '$changed', '$isunknown', '$unsigned', '$signed']
    # llama.cpp's schema converter does not accept Python-style escaped '-'
    # and '[' inside a character class. Public signals are scalar here, so no
    # indexing tokens are needed; a minus is an independent literal branch.
    expression = '('+'|'.join(re.escape(n) for n in names)+r'|[0-9]+|&&|\|\||==|!=|<=|>=|-|[ ()!<>,+*/%?:.])+'
    pattern = '^'+expression+r'(\|->|\|=>)'+expression+'$'
    schema['properties']['assertions']['items']['properties']['property']['pattern'] = pattern
    return schema


class Model(PreviousModel):
    def __init__(self, out, config):
        super().__init__(out, config)
        self.schema = lexical_schema()
        base.dump(self.out/'model_schema.json', self.schema)

    def call(self, folder, *args, **kwargs):
        log = Path(self.config['local_service_log'])
        offset = log.stat().st_size
        result, candidate = super().call(folder, *args, **kwargs)
        if not (Path(folder)/'attempt.json').is_file():
            assert candidate is None and result.get('model_calls')==0
            audit=dict(status='not_applicable_no_generation_attempt',
                preflight_status=result.get('status'),
                reason='Context preflight stopped before transport directory creation; no backend grammar request occurred.')
            base.dump(Path(folder).parent/'backend_preflight_skip.json',audit)
            result['backend_grammar_audit']=audit
            return result,candidate
        segment = log.read_bytes()[offset:]
        Path(folder, 'backend.log').write_bytes(segment)
        errors = [line for line in segment.decode(errors='replace').splitlines()
            if 'error parsing grammar' in line or 'failed to parse grammar' in line]
        audit = dict(log=str(log), offset=offset, bytes=len(segment), errors=errors,
            sha256=hashlib.sha256(segment).hexdigest(),
            status='unsupported' if errors else ('no_backend_grammar_error_observed' if segment else 'unknown'))
        base.dump(Path(folder)/'backend_audit.json', audit)
        result['backend_grammar_audit'] = audit
        if errors or not segment:
            result['frontend_status_before_backend_audit'] = result.get('candidate_status')
            result.update(status='tool_support_error' if errors else 'tool_support_unknown',
                candidate_status='not_accepted_backend_grammar_unconfirmed')
            candidate = None
        base.dump(Path(folder)/'result.json', result)
        base.dump(self.out/'model_cost_running.json', self.calls)
        return result, candidate

    def transform_request(self, request, current, target, feedback, phase):
        request = super().transform_request(request, current, target, feedback, phase)
        body = json.loads(request['messages'][1]['content'])
        task = body['boundary_repair']
        request['format'] = lexical_schema()
        targets = list(task['requested_obligations'])
        # These are the requested work items, not proof of protection. Native
        # evidence and the unchanged historical gate must establish each one.
        request['format']['properties']['assertions']['items']['properties']['obligation'] = dict(
            type='array', minItems=len(targets), maxItems=len(targets), uniqueItems=True,
            items=dict(type='string', enum=targets))
        request['messages'][0]['content'] += (
            ' ref_count is already the independent count of accepted, uncancelled inputs '
            'awaiting an output at this sampled edge; it is not necessary to reconstruct '
            'transaction history with quantifiers. Only the declared interface signals and '
            'native sampled functions exist. Decimal integer constants are supported by '
            'this generation grammar; the compiler still decides SVA validity. '
            'Actual previous diagnostic: '+json.dumps(task.get('diagnostics'))+'. '
            'Actual previous rejected proposal: '+json.dumps(task.get('previous_rejected_proposal'))+'. '
            'Revise the rejected expression; do not repeat it.')
        body['output_schema'] = request['format']
        request['messages'][1]['content'] = json.dumps(body)
        return request
