"""Public search policies. No oracle/hidden scenarios/acceptance labels imported.

Ordinary and disagreement use only port widths and public environment constraints.
Obligation scheduling is explicit and confined to guided(). Budget is external.
"""
import copy
import random


def repair_environment(d, rows):
    prev = None
    for i, r in enumerate(rows):
        r['cycle'] = i
        r['stimulus_id'] = f'input:{i}'
        if prev and prev[d['rst']] and r[d['rst']]:
            if d['key'] == 'fifo' and prev['push_i'] and not prev['pop_i']:
                r['push_i'], r['data_i'] = 1, prev['data_i']
            if d['key'] == 'filter':
                r['thresh_i'] = prev['thresh_i']
        prev = r
    return rows


def ordinary(d, seed):
    rng = random.Random(seed)
    rows = []
    for i in range(24):
        r = {n: rng.randrange(1 << w) for n, w in d['inputs'].items()}
        if rows and rng.random() < .4:
            r = {n: rows[-1][n] for n in d['inputs']}
        r[d['rst']] = int(i >= 2 and rng.random() >= .06)
        if d['key'] == 'filter': r['thresh_i'] = 2
        if i >= 20:
            r = {n: rows[-1][n] for n in d['inputs']}
            r[d['rst']] = 1
            if d['key'] == 'stat': r['frame_done_i'] = 0
            if d['key'] == 'spill': r.update(push_i=0, flush_i=0)
            if d['key'] == 'fifo': r['pop_i'] = 1
        rows.append(r)
    return repair_environment(d, rows)


def disagreement(d, seed, incumbent):
    if incumbent is None:
        return ordinary(d, seed)
    rng = random.Random(seed)
    rows = copy.deepcopy(incumbent)
    # Mutate input bits/positions with no obligation or oracle label access.
    for _ in range(6):
        i = rng.randrange(2, 20)
        name = rng.choice(list(d['inputs']) + [d['rst']])
        width = d['inputs'].get(name, 1)
        rows[i][name] = rng.randrange(1 << width)
    return repair_environment(d, rows)


def guided(d, seed, step):
    rng = random.Random(seed)
    key = d['key']
    b = {n: 0 for n in d['inputs']}
    b[d['rst']] = 0
    if key == 'filter': b.update(thresh_i=2, enable_i=1)
    rows = []
    def add(n=1, **kw):
        b.update(kw)
        for _ in range(n): rows.append(dict(b))
    add(2); b[d['rst']] = 1
    variant = step % 4
    idle = rng.randrange(1, 4)
    if key == 'onehot':
        vals = [0, 1, 2, 4, 8, 3, 5, 6, 9, 10, 12, 15]
        rng.shuffle(vals)
        for value in vals:
            add(oh_i=value, en_i=int(bool(value)), addr_i=rng.randrange(4))
    elif key == 'fifo':
        add(idle)
        for value in [0, rng.randrange(256), 255]:
            add(1 + variant, push_i=1, pop_i=0, data_i=value)
            add(pop_i=1); add(push_i=0)
    elif key == 'filter':
        add(2, filter_i=1); add(filter_i=0); add(2, filter_i=1)
        add(5, filter_i=0); add(5, filter_i=1)
        if variant == 1: add(2, enable_i=0, filter_i=0)
    elif key == 'spill':
        add(idle)
        add(push_i=1, data_i=0 if variant == 0 else rng.randrange(1, 256))
        add(1 + variant, flush_i=1)
        add(2, push_i=0, flush_i=0)
        add(push_i=1, data_i=255); add(push_i=0, flush_i=1)
    elif key == 'stat':
        add(idle)
        for value in [0, 255, rng.randrange(1, 255)]:
            add(frame_done_i=1, frame_len_i=value)
            if variant == 0: add(3, frame_done_i=0)
        add(4, frame_done_i=0)
    else:
        add(2, event_intr_i=1, reg2hw_intr_enable_q_i=1)
        add(3, event_intr_i=0, reg2hw_intr_enable_q_i=0)
        add(sw_clear=1); add(3, sw_clear=0, reg2hw_intr_enable_q_i=1)
    if variant == 3:
        # Explicit cancellation experiment, not a semantics-preserving delay.
        add(2, **{d['rst']: 0}); add(1, **{d['rst']: 1})
    if key == 'stat': b['frame_done_i'] = 0
    if key == 'spill': b.update(push_i=0, flush_i=0)
    if key == 'fifo': b['pop_i'] = 1
    while len(rows) < 24: add()
    return repair_environment(d, rows[:24])
