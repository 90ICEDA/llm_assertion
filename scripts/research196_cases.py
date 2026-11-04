"""Existing RTL, executor and oracle; opt-in broader development schedules."""
import copy
from pathlib import Path
import time
import research194_cases as old
from research195_active_queries import query_pool as generated_pool


get_case=old.get_case
validate=old.validate
ROOT=old.ROOT


def query_pool(case_id,split='development',seed=19607):
    if case_id in ('arbiter','counter'):return generated_pool(case_id,seed,split)
    return old.query_pool(case_id,split,seed)


def evaluate(case_id,candidate,out,queries=None,split='development',fault='primary',**kwargs):
    import fcntl
    lock=ROOT/'deliverables/research196_native_execution.lock';start=time.monotonic()
    with lock.open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX);wait=time.monotonic()-start
        try:m=old.evaluate(case_id,candidate,out,queries,split,fault,**kwargs)
        finally:fcntl.flock(handle,fcntl.LOCK_UN)
    m['cost']['shared_lock_wait_seconds']=wait
    return m
