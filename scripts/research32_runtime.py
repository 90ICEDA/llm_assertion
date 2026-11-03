"""Long-stall counter boundary mutations; original FIFO and oracle unchanged.

These are deliberately injected faults, not upstream bug fixes. Modes 8/9
withdraw valid after eight consecutive raw stalled samples. Reset clears the
counter. Existing modes 0..7 remain unchanged.
"""
from contextlib import contextmanager
import research28_valid_runtime as previous

runtime = previous.runtime
MODES = ('long_valid_withdraw_stalled', 'long_valid_withdraw_release')


def template(depth=2, pipeline=0):
    source = previous.template(depth, pipeline)
    anchor = '  assign mvalid = '
    assert source.count(anchor) == 1
    return source.replace(anchor, '''
  integer raw_stall_run=0;
  always @(posedge clk) begin
    if (rst || !raw_valid || mready) raw_stall_run<=0;
    else if (raw_stall_run<255) raw_stall_run<=raw_stall_run+1;
  end
  assign mvalid = (!rst && raw_stall_run>=8 &&
    ((fault_mode==8 && !mready) || (fault_mode==9 && mready))) ? 1'b0 :
''')


@contextmanager
def installed():
    with previous.installed():
        old_template, old_modes = runtime.testbench_template, runtime.MODES
        runtime.testbench_template = template
        runtime.MODES = old_modes + MODES
        try:
            yield
        finally:
            runtime.testbench_template, runtime.MODES = old_template, old_modes
