/* Read-only VPI trace of the original v3_probe_checker counters.
 * Build: iverilog-vpi -o fail_time_vpi.vpi scripts/fail_time_vpi.c
 * Run:   vvp -M <module-dir> -m fail_time_vpi <original-probe.out>
 */
#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>
#include <vpi_user.h>

static PLI_INT32 changed(p_cb_data cb) {
    s_vpi_time now = {0};
    s_vpi_value value = {0};
    now.type = vpiSimTime;
    value.format = vpiIntVal;
    vpi_get_time(cb->obj, &now);
    vpi_get_value(cb->obj, &value);
    uint64_t ticks = ((uint64_t)now.high << 32) | (uint32_t)now.low;
    const char *kind = (const char *)cb->user_data;
    vpi_printf("AUDIT_VPI_%s t_ticks=%" PRIu64 " value=%d\n", kind, ticks, value.value.integer);
    return 0;
}

static PLI_INT32 start_trace(p_cb_data unused) {
    (void)unused;
    const char *names[2] = {"v3_probe_checker.ant_hits", "v3_probe_checker.fail_hits"};
    const char *kinds[2] = {"ANT", "FAIL"};
    for (int i = 0; i < 2; ++i) {
        vpiHandle h = vpi_handle_by_name((PLI_BYTE8 *)names[i], NULL);
        if (!h) {
            vpi_printf("AUDIT_VPI_ERROR missing=%s\n", names[i]);
            continue;
        }
        s_cb_data cb = {0};
        cb.reason = cbValueChange;
        cb.cb_rtn = changed;
        cb.obj = h;
        cb.user_data = (PLI_BYTE8 *)kinds[i];
        vpi_register_cb(&cb);
    }
    return 0;
}

static void register_start(void) {
    s_cb_data cb = {0};
    cb.reason = cbStartOfSimulation;
    cb.cb_rtn = start_trace;
    vpi_register_cb(&cb);
}

void (*vlog_startup_routines[])(void) = {register_start, 0};
