"""Audited real OpenAI-compatible transport for research20; no local service.

Importing or constructing this class does not read credentials or make requests.
Only ``call`` submits a request; no retry, template response or predicate repair.
"""
import copy
import json
from pathlib import Path
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import research17_model as base
from research20_model import Model as PresentationModel, assemble

DEFAULT_URL = 'https://api.highwayapi.ai/openai/chat/completions'
DEFAULT_MODEL = 'qwen/qwen-2.5-72b-instruct'


def safe_error(exc):
    """Never serialize exception text, request objects, headers or error bodies."""
    result = {'type': type(exc).__name__}
    if isinstance(exc, urllib.error.HTTPError):
        result['http_status'] = exc.code
    if isinstance(exc, urllib.error.URLError):
        result['reason_type'] = type(exc.reason).__name__
    return result


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Authorization must not be forwarded to another origin.
        return None


class _RawLog:
    """Flush raw response bytes progressively, with credential-echo protection.

    Retain a short boundary so even a secret split across network chunks cannot
    enter the log. The raw body is otherwise unmodified; no headers are stored.
    """
    def __init__(self, path, secret):
        self.file = Path(path).open('wb')
        self.secret = secret.encode()
        self.pending = b''
        self.redactions = 0

    def write(self, chunk):
        self.pending += chunk
        while self.secret in self.pending:
            self.pending = self.pending.replace(self.secret, b'[REDACTED_CREDENTIAL]')
            self.redactions += 1
        keep = max(0, len(self.secret) - 1)
        if len(self.pending) > keep:
            count = len(self.pending) - keep
            self.file.write(self.pending[:count])
            self.file.flush()
            self.pending = self.pending[count:]

    def close(self):
        self.write(b'')
        self.file.write(self.pending)
        self.file.flush()
        self.file.close()


class RemoteModel(PresentationModel):
    def __init__(self, out, config):
        # Deliberately do not invoke the Ollama constructor.
        self.out = Path(out)
        self.config = copy.deepcopy(config)
        self.url = self.config.get('remote_url', DEFAULT_URL)
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('remote_url_requires_https_without_credentials_query_or_fragment')
        self.remote_model = self.config.get('remote_model', DEFAULT_MODEL)
        self.config['model'] = self.remote_model
        self.key_file = Path(self.config.get('key_file', base.ROOT / '.secrets/qwen_api_key.txt'))
        if not self.key_file.is_absolute():
            self.key_file = base.ROOT / self.key_file
        self.calls = []
        self.started = time.monotonic()
        self.digest = None
        self.ast_mode = False
        self.assemble = assemble
        self.schema = {'format': 'json_object', 'predicate_source': 'real_model'}
        base.dump(self.out / 'remote_transport_config.json', dict(
            endpoint=self.url, model=self.remote_model, provider='openai_compatible',
            key_file=str(self.key_file), key_file_exists=self.key_file.is_file(),
            secret_value_logged=False, model_digest=None, tokenizer_preflight='unavailable',
            max_output_tokens=min(1024, self.config['options'].get('num_predict', 1024)),
            timeout_seconds=min(180, self.config.get('call_timeout', 180)), retries=0,
            no_request_submitted_during_initialization=True))
        base.dump(self.out / 'model_schema.json', self.schema)

    def _payload(self, current, target, feedback, phase):
        context = dict(rtl_shared=base.source.RTL.read_text(),
            rtl_before={'shared': 'rtl_shared', 'boundary': "assign mdata = raw_data ^ 32'h1; assign mvalid = raw_valid;"},
            rtl_after={'shared': 'rtl_shared', 'boundary': 'assign mdata = raw_data; assign mvalid = raw_valid;'},
            provenance='Actual axis_fifo with artificial output-boundary faults, not an upstream historical bug.',
            bug='Output corruption violates accepted-input/output ordering. Related boundary faults may drop, duplicate or resurrect cancelled output.',
            clock_reset='posedge clock, active-high synchronous reset cancels transactions; SVA sampled pre-NBA, disable iff(rst). No fixed latency during arbitrary backpressure.',
            signals=base.SIGNALS, confirmed_obligations=base.SPECS, reference_rtl=base.native.REFERENCE,
            temporal_semantics={'same_sample': 'Consequent checked on antecedent edge (overlapped implication).',
                                'next_sample': 'Consequent checked on the next edge (nonoverlapped implication).'})
        task = dict(phase=phase, current_assertions=base.structured(current), actual_feedback=feedback,
                    requested_obligation=target, requested_specification=base.SPECS.get(target))
        request = dict(model=self.remote_model, options=self.config['options'], messages=[
            dict(role='system', content='Generate native SVA.'),
            dict(role='user', content=json.dumps(context)), dict(role='user', content=json.dumps(task))])
        presented = self.transform_request(request, current, target, feedback, phase)
        options = self.config['options']
        payload = dict(model=self.remote_model, messages=presented['messages'], stream=True,
                       stream_options={'include_usage': True}, response_format={'type': 'json_object'},
                       temperature=options.get('temperature', 0),
                       max_tokens=min(1024, max(1, options.get('num_predict', 1024))))
        if 'seed' in options:
            payload['seed'] = options['seed']
        return payload

    def call(self, folder, current, target, feedback, phase):
        folder = Path(folder)
        payload = self._payload(current, target, feedback, phase)
        # No remote tokenizer is available. This byte-based reservation is NOT
        # reported as actual usage or context qualification. Unknown prior use
        # consumes its reserved budget rather than silently becoming zero.
        reserve = sum(len(m['content'].encode('utf-8')) for m in payload['messages']) + 2048 + payload['max_tokens']
        used = sum((c['prompt_tokens'] + c['completion_tokens']) if
                   c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None else
                   c['token_budget_reservation'] for c in self.calls)
        if len(self.calls) >= self.config['max_model_calls']:
            raise RuntimeError('configured_model_budget_exhausted')
        if used + reserve > self.config['max_tokens']:
            raise RuntimeError('insufficient_remaining_conservative_remote_token_budget')
        remaining = self.config['max_wall_seconds'] - (time.monotonic() - self.started)
        if remaining <= 0:
            raise RuntimeError('configured_wall_budget_exhausted')
        timeout = min(180, self.config.get('call_timeout', 180), remaining)
        # Read credential only now, immediately before an actual call. Never
        # serialize it or an exception containing its file contents.
        try:
            secret = self.key_file.read_text(encoding='utf-8-sig').strip()
            if not secret or any(ch.isspace() for ch in secret):
                raise ValueError('invalid_credential_file')
        except Exception:
            raise RuntimeError('remote_credential_unavailable_or_invalid') from None
        folder.mkdir(parents=True, exist_ok=False)
        base.dump(folder / 'request.json', payload)
        base.dump(folder / 'generation_config.json', dict(
            endpoint=self.url, provider='openai_compatible', model=self.remote_model,
            options=self.config['options'], effective_parameters={k:v for k,v in payload.items() if k != 'messages'},
            token_budget_reservation=reserve, tokenizer_preflight='unavailable',
            reservation_basis='UTF-8 message bytes plus 2048 template margin and maximum output; not actual tokens',
            timeout_seconds=timeout, credential_source='configured_file', secret_value_logged=False))
        result = dict(status='pending', model=self.remote_model, digest=None, model_calls=1,
                      retries=0, prompt_tokens=None, completion_tokens=None, token_budget_reservation=reserve,
                      provider='openai_compatible', endpoint=self.url, candidate_status='not_generated')
        base.dump(folder / 'attempt.json', dict(status='submitted', model_digest=None, model=self.remote_model,
            timeout_seconds=timeout, started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), retries=0))
        started = time.monotonic()
        content, finish, usage, server_model, response_id = '', None, None, None, None
        terminal = False
        expired = threading.Event()
        response = None
        timer = None
        raw_log = None
        cancelled = False
        candidate, value = None, None

        def expire():
            expired.set()
            # Shut down the owned response socket so a stalled stream cannot
            # turn the socket timeout into an unbounded total deadline.
            try:
                response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass

        def redact(value):
            if isinstance(value, str):
                return value.replace(secret, '[REDACTED_CREDENTIAL]')
            if isinstance(value, dict):
                return {redact(k):redact(v) for k,v in value.items()}
            if isinstance(value, list):
                return [redact(v) for v in value]
            return value

        def consume(event):
            nonlocal content, finish, usage, server_model, response_id
            if event.get('error') is not None:
                raise RuntimeError('remote_service_error_event')
            if event.get('usage') is not None:
                usage = event['usage']
            server_model = event.get('model', server_model)
            response_id = event.get('id', response_id)
            for choice in event.get('choices', []):
                if choice.get('index', 0) != 0:
                    continue
                text = choice.get('delta', choice.get('message', {})).get('content')
                if isinstance(text, str):
                    content += text
                if choice.get('finish_reason') is not None:
                    finish = choice['finish_reason']
            base.dump(folder / 'response.partial.json', redact(dict(message={'role':'assistant', 'content':content},
                finish_reason=finish, usage=usage, terminal=False)))

        try:
            req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers={
                'Content-Type':'application/json', 'Accept':'text/event-stream', 'Authorization':'Bearer ' + secret})
            opener = urllib.request.build_opener(_NoRedirect())
            response = opener.open(req, timeout=timeout)
            timer = threading.Timer(max(0.001, timeout - (time.monotonic() - started)), expire)
            timer.daemon = True
            timer.start()
            raw_log = _RawLog(folder / 'response.stream.raw', secret)
            content_type = response.headers.get('Content-Type', '')
            if 'text/event-stream' in content_type:
                data_lines = []
                with (folder / 'response.events.jsonl').open('w', encoding='utf-8') as events:
                    while True:
                        raw = response.readline()
                        if expired.is_set():
                            raise TimeoutError('total_deadline')
                        if not raw:
                            break
                        raw_log.write(raw)
                        line = raw.decode('utf-8').rstrip('\r\n')
                        if line.startswith('data:'):
                            data_lines.append(line[5:].lstrip())
                        elif line == '' and data_lines:
                            data = '\n'.join(data_lines)
                            data_lines = []
                            if data == '[DONE]':
                                terminal = True
                                break
                            event = json.loads(data)
                            events.write(json.dumps(redact(event), ensure_ascii=False) + '\n')
                            events.flush()
                            consume(event)
                    if data_lines:
                        # A stream ending in an unterminated event is partial,
                        # never silently promoted to a complete response.
                        base.dump(folder / 'unterminated_event.json', redact({'data':data_lines}))
            else:
                # Some compatible services return non-streaming JSON despite
                # stream=True. Preserve each received block before parsing.
                blocks = []
                while True:
                    block = response.read1(65536)
                    if expired.is_set():
                        raise TimeoutError('total_deadline')
                    if not block:
                        break
                    raw_log.write(block)
                    blocks.append(block)
                event = json.loads(b''.join(blocks))
                base.dump(folder / 'response.server.json', redact(event))
                consume(event)
                terminal = finish is not None
            if not terminal or finish is None:
                result['status'] = 'incomplete_stream'
            elif finish != 'stop':
                result['status'] = 'response_truncated' if finish == 'length' else 'response_not_normal_completion'
            else:
                result['status'] = 'response_received'
        except KeyboardInterrupt:
            result.update(status='cancelled_by_operator', error={'type':'KeyboardInterrupt'})
            cancelled = True
        except urllib.error.HTTPError as exc:
            result.update(status='service_http_error', error=safe_error(exc))
            exc.close()
        except (TimeoutError, socket.timeout) as exc:
            result.update(status='transport_timeout', error=safe_error(exc))
        except Exception as exc:
            timed_out = expired.is_set() or isinstance(getattr(exc, 'reason', None), (TimeoutError, socket.timeout))
            result.update(status='transport_timeout' if timed_out else 'service_or_transport_error', error=safe_error(exc))
        finally:
            if timer is not None:
                timer.cancel()
            if response is not None:
                response.close()
            if raw_log is not None:
                raw_log.close()
            # No token estimates substitute for provider-reported usage.
            if isinstance(usage, dict):
                for field in ('prompt_tokens', 'completion_tokens'):
                    value_token = usage.get(field)
                    if type(value_token) is int and value_token >= 0:
                        result[field] = value_token
            result.update(wall_seconds=time.monotonic() - started,
                          partial_response_characters=len(content), done_reason=finish,
                          stream_terminal_received=terminal, actual_server_model=server_model,
                          response_id=response_id, usage_available=isinstance(usage, dict),
                          raw_credential_echo_redactions=raw_log.redactions if raw_log else 0)
            base.dump(folder / 'response.assembled.json', redact(dict(message={'role':'assistant', 'content':content},
                representation='Locally assembled first-choice content, not an upstream response envelope. Original bytes are response.stream.raw; parsed upstream SSE events are response.events.jsonl or full JSON is response.server.json.',
                service_done={'finish_reason':finish, 'terminal_received':terminal, 'usage':usage,
                              'model':server_model, 'id':response_id})))
            base.dump(folder / 'transport_result.json', redact(result))
            if result['status'] == 'response_received':
                try:
                    value = json.loads(content)
                    base.dump(folder / 'model_edit.json', redact(value))
                    candidate = self.assemble(value, current)
                    result['candidate_status'] = 'assembled_without_semantic_rewrite'
                    base.dump(folder / 'candidate.json', redact(candidate))
                    (folder / 'candidate.sva').write_text(base.native.candidate_sva(candidate).replace(secret, '[REDACTED_CREDENTIAL]'), encoding='utf-8')
                except Exception as exc:
                    candidate = None
                    # This is a local JSON/frontend exception, not a transport
                    # exception. Its bounded redacted detail is actionable for
                    # model correction (e.g. interface_unknown), without ever
                    # exposing HTTP request/response headers or error bodies.
                    local_error = safe_error(exc)
                    local_error['detail'] = str(exc).replace(secret, '[REDACTED_CREDENTIAL]')[:512]
                    result.update(candidate_status='interface_rejected', candidate_error=local_error)
            result.update(phase=phase, requested_obligation=target,
                          operation=value.get('operation') if isinstance(value, dict) else None,
                          model_owns_predicates_and_timing=True, syntax_assembly_only=True)
            result = redact(result)
            base.dump(folder / 'result.json', result)
            self.calls.append(result)
            base.dump(self.out / 'model_cost_running.json', self.calls)
        if cancelled:
            raise KeyboardInterrupt
        return result, candidate


Model = RemoteModel
