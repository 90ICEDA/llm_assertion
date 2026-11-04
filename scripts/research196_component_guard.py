"""Opt-in component activity gate. No changes to sealed R194/R195 modules.

Requires a confirmed native trigger witness for every added/changed component.
Finite inactivity is a failed acceptance condition, not logical vacuity proof.
No reference-unknown evidence grants activity. Aggregate history checks remain.
"""
import copy
from contextvars import ContextVar
import json

from research194_refinement import digest
from research195_refinement_adapter import clone, runtime as prior_runtime
from research194_refinement_safe_localization import safe_localize


def component_check(before, after, baseline, measured):
    unknown=[]; blocked=[]; records=[]
    if measured.get('candidate_sha256') != digest(after):unknown.append('proposal_candidate_binding')
    if baseline and baseline.get('candidate_sha256') != digest(before):unknown.append('baseline_candidate_binding')
    if measured.get('native_complete') is not True:unknown.append('native_incomplete')
    if not measured.get('executions'):unknown.append('native_jobs_missing')
    for job in measured.get('executions',[]):
        r=job.get('result',{})
        if r.get('compile_status')!='passed' or r.get('execution_status')!='completed':unknown.append('native_job_incomplete')
    previous={a['label']:a for a in before}
    for a in after:
        if previous.get(a['label'])==a:continue
        witnessed=[]; unconfirmed=[]
        for ev in measured.get('evidence',[]):
            observations=[x for x in ev.get('assertions',[]) if x.get('assertion')==a['label']]
            if not any(x.get('trigger') is True for x in observations):continue
            if ev.get('status')=='confirmed' and ev.get('label') in ('legal','violation') and ev.get('obligation') in a['obligations']:
                witnessed.append(ev['id'])
            else:unconfirmed.append(ev.get('id'))
        records.append(dict(assertion=a['label'],operation='changed' if a['label'] in previous else 'added',
            confirmed_activity_evidence_ids=sorted(set(witnessed)),unconfirmed_activity_ids=unconfirmed,
            verdict='confirmed_active' if witnessed else 'activity_unknown' if unconfirmed or unknown else 'finite_inactivity'))
        if not witnessed:
            if unconfirmed:unknown.append('component_activity_unconfirmed:'+a['label'])
            else:blocked.append(a['label'])
    return dict(version='research196-component-activity-v1',enabled=True,components=records,
        blocked_components=blocked,unknown=sorted(set(unknown)),passed=not blocked and not unknown,
        interpretation='Requires observed, obligation-bound native activity in the paid development history. Never a proof of logical non-vacuity or complete protection.')


def install(core, enabled=True):
    """Patch only a private module; guard runs before accept/fallback/freeze."""
    base_gate=core.gate; base_controller=core.Controller
    context=ContextVar('component_activity',default=None)
    def gate(*args,**kwargs):
        decision=base_gate(*args,**kwargs);audit=context.get()
        if not enabled or audit is None:
            decision['component_guard']=dict(enabled=False)
            return decision
        decision['component_guard']=copy.deepcopy(audit)
        if not audit['passed']:
            decision['accepted']=False;decision['complete']=False
            decision['timely_complete']=False;decision['any_cycle_complete']=False
            decision['critical_unknown'] += ['component_guard:'+x for x in audit['unknown']]
            decision['semantic_failure']=bool(audit['blocked_components']) and not decision['critical_unknown']
        return decision
    class Controller(base_controller):
        def observe(self,proposal,measurement,current_targets=None,edit_record=None,baseline=None):
            audit=component_check(self.active,proposal,baseline,measurement) if enabled else None
            token=context.set(audit)
            try:return super().observe(proposal,measurement,current_targets,edit_record,baseline)
            finally:context.reset(token)
    core.gate=gate;core.Controller=Controller
    old_request=core.build_request
    def build_request(*args,**kwargs):
        request=old_request(*args,**kwargs)
        payload=json.loads(request['messages'][-1]['content'])
        payload['component_activity_contract']=dict(enabled=enabled,
            rule='Every added or changed assertion must retain at least one independently confirmed, obligation-bound native trigger in development replay. An inactive component cannot borrow another component activity. Unknown evidence does not establish activity. Aggregate historical checks also apply.')
        request['messages'][-1]['content']=json.dumps(payload,separators=(',',':'))
        return request
    core.build_request=build_request
    return core


def runtime(arm=None, component_guard=True):
    if arm is not None:
        core,runner=prior_runtime(arm)
    else:
        core=clone('research194_refinement');runner=clone('research194_refinement_runner')
        core.localize=lambda candidate,evidence,enabled=True: safe_localize(candidate,evidence)['actionable_findings'] if enabled else []
        runner.r=core
    install(core,component_guard)
    return core,runner
