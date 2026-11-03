"""Hand-written tool-semantic probe, never an LLM-generation experiment.

One native compile/execution checks Boolean OR and sampled-value antecedents
against an explicit clock schedule, including held levels and reset intervals.
No production frontend restrictions are changed by this qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

import research15_native_interface as native


# cycle: reset, a, b, consequent. Values are applied at the preceding negedge.
STIMULUS = [
    (1, 0, 0, 0), (1, 0, 0, 0),
    (0, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 1), (0, 1, 0, 0),
    (1, 0, 0, 0), (1, 1, 0, 0),
    (0, 1, 0, 0), (0, 0, 0, 1), (0, 1, 0, 1), (0, 1, 0, 0),
]
PROPERTIES = {'boolean_or': '(a || b)', 'rose_antecedent': '$rose(a)',
              'past_antecedent': '$past(a)'}


def expectations():
    result = {name: dict(triggers=[], failures=[]) for name in PROPERTIES}
    previous_a = 0
    for cycle, (reset, a, b, consequent) in enumerate(STIMULUS):
        antecedents = dict(boolean_or=bool(a or b),
                           rose_antecedent=bool(a and not previous_a),
                           past_antecedent=bool(previous_a))
        for name, active in antecedents.items():
            if not reset and active:
                result[name]['triggers'].append(cycle)
                if not consequent:
                    result[name]['failures'].append(cycle)
        # Sampling history exists across disabled assertion edges; reset only
        # aborts checking, it does not redefine the operand's sampled value.
        previous_a = a
    return result


def source():
    properties = []
    for name, ant in PROPERTIES.items():
        properties += [
            f'{name}: assert property (@(posedge clk) disable iff (rst) ({ant} |-> okay))',
            f'  else $display("ASSERT_FAIL {name} cycle=%0d", $sampled(native_cycle));',
            f'cv_{name}: cover property (@(posedge clk) disable iff (rst) ({ant}))',
            f'  $display("TRIGGER {name} cycle=%0d", $sampled(native_cycle));']
    rows = []
    for cycle, (reset, a, b, okay) in enumerate(STIMULUS):
        rows.append(f'@(negedge clk); native_cycle={cycle}; rst={reset}; a={a}; b={b}; okay={okay};')
    return '''module tb;
bit clk=0; always #5 clk=~clk;
bit rst=1,a=0,b=0,okay=0;
integer native_cycle=-1;
PROPERTIES
always @(posedge clk) if ($sampled(native_cycle)>=0)
  $display("SAMPLE cycle=%0d rst=%0d a=%0d b=%0d okay=%0d", $sampled(native_cycle), $sampled(rst), $sampled(a), $sampled(b), $sampled(okay));
initial begin
$dumpfile("wave.vcd"); $dumpvars(0,tb);
STIMULUS
@(negedge clk); $display("NATIVE_RUN_COMPLETE"); $finish;
end
endmodule
'''.replace('PROPERTIES', '\n'.join(properties)).replace('STIMULUS', '\n'.join(rows))


def markers(result, kind, name):
    return [int(re.fullmatch(r'cycle=(\d+)', row['detail']).group(1))
            for row in result.get(kind, []) if row['id'] == name]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    if native.ROOT not in out.parents:
        raise ValueError('Output must be a new workspace artifact directory')
    out.mkdir(parents=True, exist_ok=False)
    native.dump(out / 'invocation.json', dict(argv=sys.argv,
        scope='Hand-written native tool qualification only; no LLM, no FIFO repair.'))
    native.dump(out / 'stimulus.json', [dict(cycle=i, rst=r, a=a, b=b, okay=o)
                                     for i, (r, a, b, o) in enumerate(STIMULUS)])
    expected = expectations()
    native.dump(out / 'expected_before_execution.json', dict(properties=expected,
        semantics='All operands sampled at posedge. disable iff(rst) suppresses assertion/cover during reset; sampled operand history continues. $rose fires only on 0-to-1, not on held-high samples.',
        declared_supported_scope='Two-state operands, same-cycle implication, explicit clock/reset and finite schedule.'))
    result = native.run_native(source(), out / 'native', timeout=180)
    samples = []
    if (out / 'native/execute.log').exists():
        log = (out / 'native/execute.log').read_text()
        for values in re.findall(r'^SAMPLE cycle=(\d+) rst=(\d+) a=(\d+) b=(\d+) okay=(\d+)$', log, re.M):
            samples.append(tuple(map(int, values)))
    correct_samples = samples == [(i, *row) for i, row in enumerate(STIMULUS)]
    checks = {}
    for name in PROPERTIES:
        observed = dict(triggers=markers(result, 'triggers', name),
                        failures=markers(result, 'failures', name))
        passed = (result['compile_status'] == 'passed' and result['execution_status'] == 'completed'
                  and correct_samples and observed == expected[name])
        checks[name] = dict(passed=passed, expected=expected[name], observed=observed,
            status='qualified_for_tested_schedule' if passed else 'unknown_or_failed_qualification')
    summary = dict(passed=all(v['passed'] for v in checks.values()),
        stimulus_samples_match=correct_samples, properties=checks,
        compile_status=result['compile_status'], tool_support_status=result['tool_support_status'],
        execution_status=result['execution_status'], tool_version=result['tool_version'],
        compile_calls=1, native_simulation_calls=result['native_simulation_calls'],
        model_calls=0, formal_calls=0, implementation_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        scope='Hand-authored tool capability qualification, not a generated candidate or refinement. Intentional assertion failures must match expectations; no formal proof and no production frontend changes.')
    native.dump(out / 'qualification.json', summary)
    print(json.dumps(summary))
    if not summary['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
