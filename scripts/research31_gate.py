"""Evidence-scoped gate: exempt only independently confirmed reset-cancelled stalls.

The original strict gate remains available and every non-trigger rejection is
preserved. Missing evidence never establishes non-applicability. No SVA text
is used to decide whether the hardware obligation applies.
"""
import hashlib
from pathlib import Path

import research15_acceptance as strict
import research17_loop as loop

VERSION = 'reset_cancelled_stall_v1'


def portable(value):
    text = str(value).replace('\\', '/')
    marker = '/AssertionForge-main1/'
    return loop.ROOT / text.split(marker, 1)[1] if marker in text else Path(text)


def applicability(row, cache):
    result = dict(status='unknown', evidence_id=row.get('evidence_id'))
    try:
        path = portable(row['source_directory']) / 'replay.json'
        if path not in cache:
            raw = path.read_bytes()
            record = loop.read(path)
            cache[path] = (record, hashlib.sha256(raw).hexdigest())
        record, digest = cache[path]
        result.update(source=str(path), source_sha256=digest)
        native, oracle = record['native'], record['oracle']
        from research15_evidence import INPUTS
        bound_input = strict.sha(dict(scenario=row['scenario_id'],
            inputs=[{k:t.get(k) for k in INPUTS} for t in record['trace']]))
        qualified = (
            record['sampling_qualification']['status'] == 'passed' and
            native['compile_status'] == 'passed' and
            native['tool_support_status'] == 'supported_for_compiled_constructs' and
            native['execution_status'] == 'completed' and
            oracle['legality'] == 'legal' and not oracle['unknown'] and
            row['oracle']['validator'] == 'independent_fifo_port_history_queue' and
            bound_input == row['stimulus_sha256'] and record['mode'] == row['variant'] and
            row['oracle']['paired_control_pass'] is True and
            row['oracle']['identical_input_handshakes'] is True)
        if not qualified:
            result['reason'] = 'unqualified_source'
            return result
        cycle = row['cycle']
        samples = {s['cycle']: s for s in record['reference_trace']}
        trace = {s['cycle']: s for s in record['trace']}
        previous, current = samples.get(cycle-1), samples.get(cycle)
        result['samples'] = [previous, current]
        checks = [c for c in oracle['checks']
                  if c['cycle'] == cycle and c['obligation'] == row['obligation']]
        result['independent_checks'] = checks
        if checks:
            result.update(status='required', reason='independent_obligation_check_present')
        elif row['oracle']['verdict'] == 'violated':
            result['reason'] = 'violation_without_independent_check'
        elif row['obligation'] == 'stall_stability' and previous and current:
            # Verify reset in both independent port samples and qualified SVA
            # reference samples. Synchronous reset clears oracle.prior.
            resets = [(trace.get(c, {}).get('rst'), samples[c].get('rst'))
                      for c in (cycle-1, cycle)]
            if resets == [(1, 1), (0, 0)]:
                result.update(status='not_applicable', reason='previous_reset_cancelled_stall')
            else:
                result['reason'] = 'no_confirmed_reset_cancellation'
        else:
            result['reason'] = 'no_independent_non_applicability_certificate'
    except (OSError, KeyError, TypeError, ValueError) as exc:
        result['reason'] = 'unavailable_or_malformed_source'
        result['error'] = type(exc).__name__
    return result


def decide(before, after, target_keys=()):
    result = strict.decide(before, after, target_keys)
    old, new = strict.inspect(before), strict.inspect(after)
    cache, assessments, exemptions, reasons = {}, [], [], []
    for reason in result['reasons']:
        if reason['kind'] != 'lost_obligation_trigger':
            reasons.append(reason)
            continue
        retained = []
        for key in reason['evidence_keys']:
            left = applicability(old['rows'][key], cache)
            right = applicability(new['rows'].get(key, {}), cache)
            # Both candidate runs must independently agree on the same sampled
            # hardware behavior. An exemption cannot repair missing replay,
            # changed evidence, lost detections, false positives, or unknowns.
            exempt = (left['status'] == right['status'] == 'not_applicable' and
                      left.get('samples') == right.get('samples') and
                      left.get('independent_checks') == right.get('independent_checks'))
            assessments.append(dict(evidence_id=key, before=left, after=right,
                                    exempt_trigger_preservation=exempt))
            (exemptions if exempt else retained).append(key)
        if retained:
            reasons.append(dict(kind='lost_obligation_trigger', evidence_keys=retained))
    result.update(accepted=not reasons, reasons=reasons, gate_version=VERSION,
                  trigger_applicability=assessments,
                  exempt_nonapplicable_trigger_losses=exemptions,
                  strict_gate_accepted=result['accepted'],
                  scope='Identical replay only. Reset-cancelled stall triggers alone may be exempted using both native runs and the independent oracle. Unknown applicability remains rejection; no global guarantee.')
    return result
