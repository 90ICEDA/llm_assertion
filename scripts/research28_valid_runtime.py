"""Explicit valid-withdrawal faults on the existing native FIFO harness.

Mode 6 withdraws valid during continued backpressure; mode 7 at ready release.
These are artificial output-boundary faults, not historical upstream defects.
The protocol oracle and all pre-existing modes are unchanged.
"""
from contextlib import contextmanager
import research20_stall_runtime as stall

runtime = stall.runtime
MODES = ('valid_withdraw_stalled', 'valid_withdraw_release')
_active = False


def template(depth=2, pipeline=0):
    source = stall.template(depth, pipeline)
    anchor = '  assign mvalid = '
    assert source.count(anchor) == 1
    source = source.replace(anchor, '''
  reg previous_raw_stall=0;
  always @(posedge clk) begin
    if (rst) previous_raw_stall<=0;
    else previous_raw_stall<=raw_valid && !mready;
  end
  // Deliberate external valid suppression; data, input driver and raw FIFO
  // ready connection are unchanged. Subsequent losses are separately unknown.
  assign mvalid = (!rst && previous_raw_stall &&
    ((fault_mode==6 && !mready) || (fault_mode==7 && mready))) ? 1'b0 :
''')
    return source


def install():
    global _active
    if _active:
        assert runtime.testbench_template is template
        return False
    stall.install()
    assert runtime.testbench_template is stall.template
    runtime.testbench_template = template
    runtime.MODES = stall._original_modes + (stall.MODE,) + MODES
    _active = True
    return True


def uninstall():
    global _active
    if not _active:
        return
    assert runtime.testbench_template is template
    runtime.testbench_template = stall.template
    runtime.MODES = stall._original_modes + (stall.MODE,)
    _active = False
    stall.uninstall()


@contextmanager
def installed():
    changed = install()
    try:
        yield
    finally:
        if changed:
            uninstall()
