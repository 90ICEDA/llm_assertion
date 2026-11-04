"""Preregistered typed-local-operation qualification fixtures, not LLM results.

Counter fixtures use public real RTL with artificial defects. Ibex uses the
existing real flush sub-fix harness and a development stall mutation.
"""
import copy
from pathlib import Path
import time
import research194_cases as cases
import research194_refinement_runner as oldrunner


def evaluate_locked(case_id,candidate,out,queries,fault,split='development',trusted=False):
    import fcntl
    lock=oldrunner.ROOT/'deliverables/research195_active_native_execution.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    waiting=time.monotonic()
    with lock.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX)
        wait=time.monotonic()-waiting
        try:
            measured=cases.evaluate(case_id,candidate,out,queries=queries,split=split,fault=fault,_trusted_bundle=trusted)
        finally:fcntl.flock(handle,fcntl.LOCK_UN)
    measured['cost']['shared_lock_wait_seconds']=wait
    measured['cost']['native_wall_excludes_shared_lock_wait']=True
    oldrunner.dump(Path(out)/'shared_lock.json',dict(path=str(lock),wait_seconds=wait,scope='one candidate over its at-most-two registered queries'))
    return oldrunner.bind_measurement(measured,candidate)


def prop(label,ant,cons,ob,timing='same_sample'):
    return dict(label=label,antecedent=ant,consequent=cons,timing=timing,obligations=list(ob))


def counter_pulses():
    rows=[]
    def add(**kw):
        row=dict(rst_n=1,clr=0,en=0,load=0,down=0,d=0);row.update(kw);rows.append(row)
    for _ in range(3):add(rst_n=0)
    add();add();add(load=1,d=7);add();add();add(en=1);add();add();add(en=1)
    add();add(load=1,d=13);add();add();add(clr=1,en=1);add();add();add()
    return dict(id='counter/r195_pulses/'+cases.digest(rows)[:12],family='r195_pulses',rows=rows,
        obligations=cases.get_case('counter')['obligations'],dimensions=['window','transaction','exception'],
        constraints=['fixed pre-edge sampling','isolated load and enable pulses','d changes after request'],
        split='development',estimated_cost=2,evidence_visibility='public_development')


def fixtures():
    up=next(q for q in cases.query_pool('counter') if q['family']=='up')
    pulses=counter_pulses()
    load_anchor=prop('load_anchor','load && !clr','q == $past(d)',['counter_load'],'next_sample')
    import research194_ibex as ibex
    return {
      'delay':dict(case_id='counter',fault='primary',queries=[up],
        interpretation='Exact one-sample applicability delay, not a temporal-window repair.',
        initial=[prop('step','en && !load && !clr && !down',"q == (($past(q)+1)&4'hf)",['counter_step'])],
        edit=dict(op='set_delay',assertion='step',field='antecedent',expression='en && !load && !clr && !down',cycles=1)),
      'window':dict(case_id='counter',fault='dev_load_offbyone',queries=[pulses],
        interpretation='Necessary bounded cause: a q change must follow an enable/load/clear in the previous 1..2 samples; not a complete arithmetic specification. load_anchor preserves measured defect detection.',
        initial=[prop('change_has_cause','rst_n && $past(rst_n) && q != $past(q)',
            '$past(en || load || clr,2)',['counter_step','counter_load','clear_cancel']),load_anchor],
        edit=dict(op='set_window',assertion='change_has_cause',field='consequent',expression='en || load || clr',min_cycles=1,max_cycles=2,quantifier='any')),
      'single_inflight_match':dict(case_id='counter',fault='dev_load_offbyone',queries=[pulses],
        interpretation='Single in-flight load request-data to next-sample response matching; not multiple outstanding transaction-ID or reordered response validation.',
        initial=[prop('load_response','load && !clr','q == d',['counter_load'],'next_sample')],
        edit=dict(op='match_transaction',assertion='load_response',field='consequent',base_expression="1'b1",request_id='d',response_id='q',cycles=1)),
      'exception':dict(case_id='ibex_flush',fault='dev_stall_advance',
        queries=[q for q in ibex.query_pool() if q['family'] in ('normal','flush_stall')],
        interpretation='Holding an expanded output while stalled permits the legal flush cancellation exception. Binding alone is never counted as protection.',
        initial=[prop('stall_output','valid && !ready','$stable(instr_out)',['stall_hold','flush_cancel'],'next_sample')],
        edit=dict(op='except_when',assertion='stall_output',field='antecedent',base_expression='valid && !ready',exception='flush')),
    }


class FixtureAdapter(oldrunner.CaseAdapter):
    def __init__(self,name):
        self.fixture=copy.deepcopy(fixtures()[name]);super().__init__(self.fixture['case_id'])
        self.case['initial']=copy.deepcopy(self.fixture['initial'])
        self.case['specification']=dict(public_case_specification=self.case['specification'],
            qualification_scope=self.fixture['interpretation'])
        self.case['candidate_provenance']='R195 preregistered handwritten defective seed; not model generated'
    def evaluate(self,candidate,out,queries):
        return evaluate_locked(self.case_id,candidate,out,queries,self.fixture['fault'])
