"""Native SVA execution, with no assertion lowering or substitute checker.

Runs inside WSL. Verilator is unpacked locally; set VERILATOR if using another
installation. Trigger markers are diagnostics, independent of native verdicts.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import copy

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'deliverables/research_native_20261014_r01'


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def command(argv, folder, name, timeout=240, env=None):
    start = time.monotonic()
    record = dict(argv=[str(a) for a in argv], cwd=str(folder), timeout_seconds=timeout)
    try:
        proc = subprocess.run(argv, cwd=folder, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=timeout)
        record.update(exit_code=proc.returncode, status='completed')
        output = proc.stdout
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or b''
        if isinstance(output, bytes): output = output.decode(errors='replace')
        record.update(exit_code=None, status='timeout')
    except OSError as exc:
        output = repr(exc)
        record.update(exit_code=None, status='launch_failed')
    record['wall_seconds'] = time.monotonic() - start
    (folder / (name + '.log')).write_text(output)
    dump(folder / (name + '.json'), record)
    return record, output


def native_environment():
    env = os.environ.copy()
    unpack = OUT / 'tools/unpack/usr'
    binary = env.get('VERILATOR', str(unpack / 'bin/verilator'))
    if 'VERILATOR' not in env:
        env['VERILATOR_ROOT'] = str(unpack / 'share/verilator')
        # Debian puts executables in /usr/bin, separately from runtime headers.
        env['VERILATOR_BIN'] = '../../bin/verilator_bin'
    return binary, env


def run_native(source_text, directory, top='tb', extra_sources=(), timeout=240):
    """Return separate compile/support/execute/trigger/property states.

    A testbench must print NATIVE_RUN_COMPLETE on normal completion and may
    emit ASSERT_FAIL <id> / TRIGGER <id> / TRACE ... for replay diagnostics.
    Native assert property action blocks emit ASSERT_FAIL; assertions remain
    native Verilator SVA. No textual conversion of SVA is performed here.
    """
    folder = Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    source = folder / 'tb.sv'
    source.write_text(source_text)
    binary, env = native_environment()
    version, version_text = command([binary, '--version'], folder, 'tool_version', 15, env)
    result = dict(engine='Verilator native SVA simulation', formal_proof=False,
                  source_sha256=hashlib.sha256(source_text.encode()).hexdigest(),
                  tool_version=version_text.strip(), compile_status='not_run',
                  tool_support_status='unknown', execution_status='not_run',
                  trigger_status='unknown', property_status='unknown',
                  trigger_measurement='procedural antecedent diagnostic; not native cover proof',
                  formal_cost={'calls': 0, 'wall_seconds': 0},
                  native_simulation_calls=0)
    argv = [binary, '--binary', '--timing', '--assert', '--trace', '-j', '2', '-Wno-fatal',
            '--top-module', top, '--Mdir', str(folder / 'obj_dir'),
            '-o', 'native_sim', str(source), *[str(Path(p).resolve()) for p in extra_sources]]
    compile_record, output = command(argv, folder, 'compile', timeout, env)
    result['compile'] = compile_record
    if compile_record['exit_code'] != 0:
        result['compile_status'] = 'failed'
        if re.search(r'%Error(?:-UNSUPPORTED)?:.*(?:Unsupported|unsupported)', output):
            result['tool_support_status'] = 'unsupported_construct'
            result['compile_error_category'] = 'tool_unsupported'
        elif '%Error' in output and ('syntax error' in output or 'Cannot find' in output or 'not found' in output):
            result['tool_support_status'] = 'candidate_or_build_error'
            result['compile_error_category'] = 'syntax_error' if 'syntax error' in output else 'elaboration_or_build_error'
        else:
            result['tool_support_status'] = 'unknown_build_failure'
            result['compile_error_category'] = 'unknown'
    else:
        result.update(compile_status='passed', tool_support_status='supported_for_compiled_constructs',
                      native_simulation_calls=1)
        execute_record, output = command([str(folder / 'obj_dir/native_sim')], folder, 'execute', timeout, env)
        result['execute'] = execute_record
        fails = re.findall(r'^ASSERT_FAIL\s+(\S+)(.*)$', output, flags=re.M)
        triggers = re.findall(r'^TRIGGER\s+(\S+)(.*)$', output, flags=re.M)
        result.update(failures=[{'id': a, 'detail': b.strip()} for a, b in fails],
                      triggers=[{'id': a, 'detail': b.strip()} for a, b in triggers])
        complete = execute_record['exit_code'] == 0 and 'NATIVE_RUN_COMPLETE' in output
        result['execution_status'] = 'completed' if complete else 'incomplete_or_failed'
        result['trigger_status'] = 'observed' if triggers else 'no_trigger_marker_observed'
        result['property_status'] = ('violation' if fails else
            'no_violation_within_executed_scope' if complete else 'unknown')
        if not complete and not fails and re.search(r'Assertion failed', output):
            result['property_status'] = 'native_assertion_failure_unclassified'
    dump(folder / 'result.json', result)
    return result


def replay_native(compiled_directory, directory, runtime_args=(), timeout=60):
    """Replay an unchanged compiled assertion set on runtime-selected fault modes."""
    origin, folder = Path(compiled_directory).resolve(), Path(directory).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    result = copy.deepcopy(json.loads((origin / 'result.json').read_text()))
    result.update(reused_compilation=str(origin), native_simulation_calls=1)
    result.pop('compile', None)
    record, output = command([str(origin / 'obj_dir/native_sim'), *runtime_args], folder, 'execute', timeout)
    result['execute'] = record
    complete = record['exit_code'] == 0 and 'NATIVE_RUN_COMPLETE' in output
    result['failures'] = [dict(id=a, detail=b.strip()) for a,b in re.findall(r'^ASSERT_FAIL\s+(\S+)(.*)$', output, re.M)]
    result['triggers'] = [dict(id=a, detail=b.strip()) for a,b in re.findall(r'^TRIGGER\s+(\S+)(.*)$', output, re.M)]
    result.update(execution_status='completed' if complete else 'incomplete_or_failed',
                  trigger_status='observed' if result['triggers'] else 'no_trigger_marker_observed',
                  property_status='violation' if result['failures'] else 'no_violation_within_executed_scope' if complete else 'unknown')
    dump(folder / 'result.json', result)
    return result


def probe(folder=None):
    folder = Path(folder) if folder else OUT / 'probes'
    cases = {
        'nonoverlap_positive': ('a |=> b', 'a=1; b=0; @(negedge clk); a=0; b=1;'),
        'nonoverlap_negative': ('a |=> b', 'a=1; b=0; @(negedge clk); a=0; b=0;'),
        'past_positive': ('a |-> $past(b)', 'b=1; @(negedge clk); a=1;'),
        'sequence_delay': ('a |-> ##2 b', 'a=1; b=0;'),
    }
    records = {}
    for name, (prop, stimulus) in cases.items():
        source = '''module tb;
bit clk=0; always #5 clk=~clk;
bit rst=1, a=0, b=0;
assert property (@(posedge clk) disable iff (rst) PROP)
  else $display("ASSERT_FAIL probe time=%0t", $time);
always @(posedge clk) if (!rst && a) $display("TRIGGER probe time=%0t", $time);
initial begin
$dumpfile("wave.vcd"); $dumpvars(0,tb);
repeat(2) @(negedge clk); rst=0; STIM
repeat(4) @(negedge clk); $display("NATIVE_RUN_COMPLETE"); $finish;
end
endmodule
'''.replace('PROP', prop).replace('STIM', stimulus)
        records[name] = run_native(source, folder / name)
        if name == 'sequence_delay' and records[name]['compile_status'] == 'failed':
            records[name]['tool_support_status'] = 'known_valid_sva_feature_not_supported_by_tool'
            records[name]['feature_probe'] = 'IEEE SVA sequence delay ##2; syntax rejection is tool capability, not generated-candidate syntax error'
            dump(folder / name / 'result.json', records[name])
    dump(folder / 'result.json', records)
    print(json.dumps({k: {n: v[n] for n in ['compile_status', 'tool_support_status', 'property_status']} for k,v in records.items()}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['probe', 'run'])
    parser.add_argument('--source')
    parser.add_argument('--out')
    args = parser.parse_args()
    if args.action == 'probe': probe(args.out)
    else:
        print(json.dumps(run_native(Path(args.source).read_text(), args.out), indent=2))
