"""Prospective schedules for valid retention, independent of SVA contents."""
import random
from research28_valid_runtime import MODES


def cases(seed, independent=False):
    rng = random.Random(seed)
    result = []
    parameters = ((4, 2), (8, 2)) if independent else ((2, 0), (5, 1))
    for depth, pipeline in parameters:
        for mode in MODES:
            for family in ('continuous', 'reset_cancels_stall'):
                length = 96
                payloads = rng.sample(range(1, 2**32), length)
                start = rng.randrange(10, 17)
                duration = rng.randrange(3, 7)
                rows = []
                for c in range(length):
                    reset = c < 2 or (family == 'reset_cancels_stall' and c in (start+1, start+2))
                    # A second stall after reset permits both checking reset
                    # cancellation and exposing a non-reset valid obligation.
                    low = start <= c < start+duration or start+15 <= c < start+20
                    rows.append(dict(cycle=c, rst=int(reset), intent=int(3 <= c < 55),
                        ready=int(not low), data=payloads[c], drain_due=int(c == length-1)))
                result.append(dict(id=f'valid28:s{seed}:d{depth}:p{pipeline}:{mode}:{family}',
                    depth=depth, pipeline=pipeline, mode=mode, rows=rows, seed=seed,
                    family=family, split='independent_test' if independent else 'development',
                    source='prospective_valid_retention_contract_schedule',
                    target_obligation='stall_stability', stall_start=start, stall_duration=duration,
                    dedup_class=f'stall_stability:{mode}',
                    scope='Artificial boundary fault on actual axis_fifo. Parameter and waveform variants are replications.'))
    return result
