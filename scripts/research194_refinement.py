"""Versioned multi-round temporal refinement contracts, independent of case RTL.

No model invocation occurs in this module. Structured operations render actual
SVA sampled expressions; they are not annotations or substitute verdicts. Native
case validation remains mandatory. research192 code/results are unchanged.
"""
from dataclasses import dataclass, field
import copy
import hashlib
import json
import re


FIELDS={'antecedent','consequent','timing'}
STRATEGIES=('R0','R1','R2','R3')
TRAJECTORIES=(('S0','R0'),('S0','R1'),('S0','R2'),('S0','R3'),
              ('S1','R1'),('S2','R1'),('S3','R1'),('S3','R3'))
ABLATION_ALIASES={'A0':('S0','R1'),'A1':('S3','R1'),
                 'A2':('S0','R3'),'A3':('S3','R3')}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def normalize_evidence(records):
    """Normalize public adapter observations without inventing oracle labels."""
    result=[]
    for raw in records:
        row=copy.deepcopy(raw)
        row['id']=row.get('id',row.get('evidence_id'))
        if not row['id']:raise ValueError('evidence_requires_stable_id')
        status=row.get('status');oracle=row.get('oracle_status')
        if oracle in ('legal','violation'):
            row.setdefault('label',oracle);row.setdefault('status','confirmed')
        elif oracle=='unknown':
            row['status']='unknown';row.setdefault('label','unknown')
        elif isinstance(oracle,dict):
            row.setdefault('label',oracle.get('kind','unknown'))
            row.setdefault('status','confirmed' if oracle.get('confirmed') is True else 'unknown')
        row.setdefault('status',status or 'unknown')
        row.setdefault('label','unknown')
        predictions=row.get('assertions',row.get('candidate_predictions',[]))
        if isinstance(predictions,dict):
            predictions=[dict(assertion=key,**value) for key,value in predictions.items()]
        row['assertions']=predictions
        result.append(row)
    return result


def localize(candidate,evidence,enabled=True):
    if not enabled:return []
    evidence=normalize_evidence(evidence);labels={a['label'] for a in candidate};found={}
    def add(kind,label,field,row,reason):
        key=(label,field,kind)
        value=found.setdefault(key,dict(assertion=label,field=field,kind=kind,
            evidence_ids=[],status='supported_hypothesis_requires_native_validation',reason=reason))
        if row['id'] not in value['evidence_ids']:value['evidence_ids'].append(row['id'])
    for row in evidence:
        if row['status']!='confirmed' or row['label'] not in ('legal','violation'):continue
        for observation in row['assertions']:
            label=observation.get('assertion')
            if label not in labels:continue
            trigger,failure=observation.get('trigger'),observation.get('failure')
            if row['label']=='violation' and trigger is False:
                add('trigger_too_narrow',label,'antecedent',row,'Confirmed target is outside measured native trigger.')
            if row['label']=='violation' and trigger is True and failure is False:
                add('response_missing',label,'consequent',row,'Measured native trigger permits a confirmed violation.')
            if row['label']=='legal' and failure is True:
                add('trigger_too_broad',label,'antecedent',row,'Legal alarm: trigger applicability and consequent are alternative hypotheses.')
                add('response_too_strict',label,'consequent',row,'Legal alarm alone cannot identify a unique cause.')
            defective=(row['label']=='legal' and failure is True) or (row['label']=='violation' and failure is False)
            assertion=next(a for a in candidate if a['label']==label)
            if defective:
                # These are hypotheses tied to a failing assertion and its
                # observed transaction, not independent oracle conclusions.
                if re.search(r'\$past|\b(?:cycle|txn_age|age|delay)\b',assertion['antecedent']+' '+assertion['consequent']):
                    for field in ('antecedent','consequent'):
                        add('latency_window',label,field,row,'A failed native assertion uses explicit temporal samples/bounds; test a local window change.')
                if re.search(r'data|match|expansion|order|transaction',row.get('obligation','')):
                    add('transaction_matching',label,'consequent',row,'A failed assertion is bound to this transaction-matching obligation; matching is a hypothesis, not a proven root cause.')
                sample=row.get('previous_observations',row.get('observations',{}))
                exception=any(sample.get(k)==v for k,v in (('flush',1),('clr',1),('rst',1),('rst_n',0),('tx_enable',0),('ready',0)))
                if row['label']=='legal' and exception:
                    add('legal_exception',label,'antecedent',row,'A confirmed legal alarm occurs at an observed cancellation/backpressure condition; test applicability locally.')
                # Compare only two observed samples. Unsupported expressions or
                # missing history cannot grant a timing edit.
                if row.get('observations') and row.get('previous_observations'):
                    import research194_active_semantics as semantics
                    trace=[row['previous_observations'],row['observations']]
                    try:
                        ant=semantics.parse(assertion['antecedent']);cons=semantics.parse(assertion['consequent'])
                        now=semantics.value(ant,trace,1);prior=semantics.value(ant,trace,0)
                        cv=semantics.value(cons,trace,1)
                        actual=prior if assertion['timing']=='next_sample' else now
                        alternative=now if assertion['timing']=='next_sample' else prior
                        agrees=actual is not None and bool(actual)==trigger
                        improves=(row['label']=='legal' and alternative==0) or (row['label']=='violation' and alternative not in (0,None) and cv==0)
                        if agrees and improves and actual!=alternative:
                            add('implication_alignment',label,'timing',row,'Native trigger agrees with evaluated observed samples; flipping implication alignment changes this failure. Full native replay is still required.')
                    except (ValueError,TypeError,KeyError,IndexError):pass
            # Facts must be assertion-specific. A global transaction mismatch
            # must not authorize edits to every unrelated assertion.
            facts=observation.get('independent_facts',{})
            for fact,kind,field in (
                ('latency_mismatch','latency_window','antecedent'),
                ('latency_mismatch','latency_window','consequent'),
                ('implication_timing_mismatch','latency_window','timing'),
                ('transaction_mismatch','transaction_matching','consequent'),
                ('legal_exception_missed','legal_exception','antecedent'),
                ('required_trigger_missing','insufficient_trigger','antecedent')):
                if facts.get(fact) is True:add(kind,label,field,row,'Case monitor confirms '+fact+' for this assertion.')
    for label in labels:
        observations=[(row,a) for row in evidence if row['status']=='confirmed'
            for a in row['assertions'] if a.get('assertion')==label]
        targets=[row for row,a in observations if row['label']=='violation']
        if targets and all(a.get('trigger') is False for _,a in observations):
            add('finite_inactivity',label,'antecedent',targets[0],
                'No trigger on the observed finite suite; not a proof of logical vacuity.')
    return sorted(found.values(),key=lambda x:(x['assertion'],x['field'],x['kind']))


def _sample(expression,cycles):
    if not isinstance(expression,str) or not expression.strip():raise ValueError('expression_required')
    if type(cycles) is not int or not 0<=cycles<=8:raise ValueError('sample_delay_0_to8')
    return f'({expression})' if cycles==0 else f'$past(({expression}), {cycles})'


def render_operation(edit):
    """Return a field/value. Every operand and cycle bound is model supplied.

Windows are RETROSPECTIVE sampled windows, not silently rewritten prospective
## ranges. Request anchoring is a separate model-owned antecedent operation.
"""
    op=edit.get('op');common={'op','assertion','field'}
    if op=='replace_field':
        if set(edit)!=common|{'value'} or not isinstance(edit['value'],str):raise ValueError('replace_field_schema')
        return edit['field'],edit['value']
    if op=='set_delay':
        if set(edit)!=common|{'expression','cycles'}:raise ValueError('delay_schema')
        return edit['field'],_sample(edit['expression'],edit['cycles'])
    if op=='set_window':
        if set(edit)!=common|{'expression','min_cycles','max_cycles','quantifier'}:raise ValueError('window_schema')
        lo,hi=edit['min_cycles'],edit['max_cycles']
        if type(lo) is not int or type(hi) is not int or not 0<=lo<=hi<=8:raise ValueError('window_bounds')
        if edit['quantifier'] not in ('any','all'):raise ValueError('window_quantifier')
        join=' || ' if edit['quantifier']=='any' else ' && '
        return edit['field'],'('+join.join(_sample(edit['expression'],i) for i in range(lo,hi+1))+')'
    if op=='match_transaction':
        if set(edit)!=common|{'base_expression','request_id','response_id','cycles'}:raise ValueError('matching_schema')
        request=_sample(edit['request_id'],edit['cycles'])
        for key in ('base_expression','response_id'):
            if not isinstance(edit[key],str) or not edit[key].strip():raise ValueError('matching_expression')
        return edit['field'],f"({edit['base_expression']}) && (({edit['response_id']}) == ({request}))"
    if op=='except_when':
        if set(edit)!=common|{'base_expression','exception'}:raise ValueError('exception_schema')
        if not all(isinstance(edit[k],str) and edit[k].strip() for k in ('base_expression','exception')):raise ValueError('exception_expression')
        return edit['field'],f"({edit['base_expression']}) && !({edit['exception']})"
    raise ValueError('unknown_local_operation')


def apply_patch(current,response,findings,validate,stage='local',receipt=None,uncovered=()):
    """Ignore ONLY byte-identical no-ops without enlarging the edit domain."""
    if stage=='regenerate':
        if receipt is None or not receipt.valid_for(current,'compose'):raise ValueError('regeneration_requires_measured_composition_failure')
        if not isinstance(response,dict) or set(response)!={'assertions','reason'}:raise ValueError('regeneration_schema')
        return validate(copy.deepcopy(response['assertions'])),dict(noops=[],changed=['entire_set'],stage=stage)
    if stage not in ('local','compose'):raise ValueError('unknown_stage')
    if not isinstance(response,dict) or set(response)!={'edits','reason'} or not isinstance(response['reason'],str):raise ValueError('edit_schema')
    edits=response['edits']
    if not isinstance(edits,list) or not 1<=len(edits)<=4:raise ValueError('edit_count_1_to4')
    if stage=='compose' and (receipt is None or not receipt.valid_for(current,'local')):
        raise ValueError('composition_requires_measured_local_failure')
    result=copy.deepcopy(current);original={a['label']:a for a in current}
    allowed={(f['assertion'],f['field']) for f in findings};seen=set();noops=[];changed=[]
    for edit in edits:
        if not isinstance(edit,dict):raise ValueError('edit_object_required')
        if edit.get('op')=='add_assertion':
            if stage!='compose' or set(edit)!={'op','assertion'}:raise ValueError('add_requires_composition_stage')
            a=edit['assertion']
            if not isinstance(a,dict) or not set(a.get('obligations',[]))&set(uncovered):raise ValueError('addition_requires_uncovered_obligation')
            result.append(copy.deepcopy(a));changed.append(dict(op='add_assertion',label=a.get('label')))
            continue
        label=edit.get('assertion');field,value=render_operation(edit);key=(label,field)
        if label not in original or field not in FIELDS:raise ValueError('unknown_edit_target')
        if key in seen:raise ValueError('duplicate_field')
        seen.add(key)
        # Check against the ORIGINAL bytes, never semantic equivalence or
        # whitespace normalization. A second write to a field is still invalid.
        if value==original[label][field]:
            noops.append(dict(assertion=label,field=field));continue
        if stage!='local' or key not in allowed:raise ValueError('changed_field_not_localized')
        target=next(a for a in result if a['label']==label)
        target[field]=value;changed.append(dict(op=edit['op'],assertion=label,field=field))
    return validate(result),dict(noops=noops,changed=changed,stage=stage,semantic_change=bool(changed))


def gate(measurement,strategy,protected=(),current_targets=None,necessary_obligations=(),baseline=None,protected_transactions=()):
    """Separate confirmed defects, missing exposure, execution unknown and loss."""
    targets=set(measurement['targets']);detected=set(measurement['detected_ids'])
    triggered=set(measurement['triggered_ids']);unknown=list(measurement.get('critical_unknown',[]))
    if detected-triggered:unknown+=['detected_without_native_trigger:'+x for x in sorted(detected-triggered)]
    absent_history=set(protected)-targets
    absent_history|=set(protected_transactions)-targets
    if absent_history:unknown+=['protected_target_not_exposed:'+x for x in sorted(absent_history)]
    current=targets if current_targets is None else set(current_targets)
    if current-targets:unknown+=['current_target_not_exposed:'+x for x in sorted(current-targets)]
    if measurement.get('native_complete') is not True:unknown.append('native_not_complete')
    if measurement.get('reference_complete') is not True:unknown.append('reference_not_complete')
    fps=measurement.get('false_positives',[])
    required=targets if strategy in ('R2','R3') else current
    lost=(set(protected)&targets)-detected
    uncovered=required-detected;untriggered=required-triggered
    evidence=normalize_evidence(measurement.get('evidence',[]))
    covered_obligations={e.get('obligation') for e in evidence if e['status']=='confirmed'
                         and e['label']=='violation' and e['id'] in detected}
    unexposed_obligations=set(necessary_obligations)-{e.get('obligation') for e in evidence if e['status']=='confirmed' and e['label']=='violation'}
    missing_obligations=set(necessary_obligations)-covered_obligations
    baseline=baseline or {}
    old_detected=set(baseline.get('detected_ids',[]))
    transaction_detected=set(measurement.get('transaction_detected_ids',detected))
    old_transactions=set(baseline.get('transaction_detected_ids',old_detected))
    transaction_gained=(transaction_detected-old_transactions)&required
    transaction_lost=(set(protected_transactions)&targets)-transaction_detected
    old_fps={e['id'] for e in baseline.get('false_positives',[])}
    fp_ids={e['id'] for e in fps}
    gained=(detected-old_detected)&required
    fixed_fps=old_fps-fp_ids
    new_fps=fp_ids-old_fps
    # An unexposed obligation is not a native rejection or a claimed success.
    # Incremental progress is allowed; history-preserving arms require all old
    # detections and all previously legal samples to survive.
    progress=bool(gained or transaction_gained or fixed_fps)
    accepted=bool(required) and progress and not(unknown or new_fps)
    if strategy in ('R2','R3'):accepted=accepted and not lost and not transaction_lost
    complete=bool(targets) and not(unknown or fps or targets-detected or targets-triggered or missing_obligations)
    semantic_failure=not unknown and bool(fps or uncovered or untriggered or lost or transaction_lost)
    return dict(accepted=bool(accepted),complete=bool(complete),semantic_failure=bool(semantic_failure),
        critical_unknown=unknown,missed_ids=sorted(uncovered),untriggered_ids=sorted(untriggered),
        lost_ids=sorted(lost),false_positives=fps,regression=bool(not unknown and (lost or transaction_lost or new_fps)),
        gained_ids=sorted(gained),fixed_false_positive_ids=sorted(fixed_fps),new_false_positive_ids=sorted(new_fps),
        timely_gained_ids=sorted(gained),transaction_gained_ids=sorted(transaction_gained),
        historical_any_cycle_lost_ids=sorted(transaction_lost),timely_complete=bool(complete),
        any_cycle_complete=bool(targets) and not bool(unknown or fps or targets-transaction_detected or unexposed_obligations),
        covered_obligations=sorted(x for x in covered_obligations if x is not None),
        missing_obligations=sorted(missing_obligations),unexposed_obligations=sorted(unexposed_obligations),
        no_target_exposure=not bool(required))


@dataclass(frozen=True)
class FailureReceipt:
    stage:str
    active_sha256:str
    proposal_sha256:str
    measurement_sha256:str
    native_bindings:dict
    failed:bool

    @classmethod
    def from_measurement(cls,stage,active,proposal,measurement,decision):
        if stage not in ('local','compose'):raise ValueError('failure_receipt_stage')
        if digest(active)==digest(proposal):raise ValueError('unchanged_proposal_cannot_enable_fallback')
        if measurement.get('candidate_sha256')!=digest(proposal):raise ValueError('measurement_candidate_mismatch')
        if not decision['semantic_failure'] or decision['critical_unknown']:raise ValueError('no_confirmed_native_failure')
        if not measurement.get('native_bindings'):raise ValueError('native_evidence_binding_required')
        if measurement.get('native_complete') is not True or measurement.get('reference_complete') is not True:
            raise ValueError('unknown_cannot_enable_fallback')
        return cls(stage,digest(active),digest(proposal),digest(measurement),
                   copy.deepcopy(measurement['native_bindings']),True)

    def valid_for(self,active,prior_stage):
        return self.failed and self.stage==prior_stage and self.active_sha256==digest(active) and bool(self.native_bindings)


@dataclass(frozen=True)
class LocalDomainEmptyReceipt:
    """Proof about this edit interface, never about all possible SVA repairs."""
    active_sha256:str
    measurement_sha256:str
    missing_obligations:list
    confirmed_target_ids:list
    native_bindings:dict
    stage:str='local'
    kind:str='local_domain_empty'
    editable_fields:tuple=('antecedent','consequent','timing')
    immutable_fields:tuple=('label','obligations')

    def valid_for(self,active,prior_stage):
        declared={o for a in active for o in a['obligations']}
        return (prior_stage=='local' and self.active_sha256==digest(active)
                and bool(self.missing_obligations) and not declared.intersection(self.missing_obligations)
                and bool(self.confirmed_target_ids) and bool(self.native_bindings)
                and set(self.editable_fields)==FIELDS and self.immutable_fields==('label','obligations'))


@dataclass
class Controller:
    initial:list
    strategy:str
    necessary_obligations:list
    protected:set=field(default_factory=set)
    protected_transactions:set=field(default_factory=set)
    max_rounds:int=3
    localization_enabled:bool=True
    fallback_enabled:bool=True

    def __post_init__(self):
        if self.strategy not in STRATEGIES or not 1<=self.max_rounds<=3:raise ValueError('controller_configuration')
        self.active=copy.deepcopy(self.initial);self.protected=set(self.protected)
        self.protected_transactions=set(self.protected_transactions)
        self.stage='local' if self.strategy=='R3' else 'free'
        self.receipt=None;self.history=[];self.finished=False;self.rounds=0

    def parse(self,response,evidence,validate):
        if self.finished or self.rounds>=self.max_rounds:raise ValueError('controller_terminal_or_budget')
        if self.strategy!='R3':
            if not isinstance(response,dict) or set(response)!={'assertions','reason'} or not isinstance(response['reason'],str):raise ValueError('free_response_schema')
            return validate(copy.deepcopy(response['assertions'])),dict(stage='free',changed=['entire_set'],noops=[])
        findings=localize(self.active,evidence,self.localization_enabled)
        observed={e.get('obligation') for e in normalize_evidence(evidence)
                  if e['status']=='confirmed' and e['label']=='violation'}
        uncovered=observed-set(self.history[-1]['decision'].get('covered_obligations',[])) if self.history and 'decision' in self.history[-1] else observed
        return apply_patch(self.active,response,findings,validate,self.stage,self.receipt,uncovered)

    def consider_empty_domain(self,measurement):
        if self.strategy!='R3' or self.stage!='local' or not self.fallback_enabled:return None
        if measurement.get('candidate_sha256')!=digest(self.active):raise ValueError('domain_certificate_candidate_binding')
        if measurement.get('native_complete') is not True or measurement.get('reference_complete') is not True or measurement.get('critical_unknown') or not measurement.get('native_bindings'):return None
        declared={o for a in self.active for o in a['obligations']}
        targets=set(measurement['targets']);detected=set(measurement['detected_ids'])
        missing={}
        for ev in normalize_evidence(measurement.get('evidence',[])):
            if (ev['status']=='confirmed' and ev['label']=='violation' and ev.get('counted_target',True)
                and ev['id'] in targets-detected and ev.get('obligation') in self.necessary_obligations
                and ev['obligation'] not in declared):missing.setdefault(ev['obligation'],set()).add(ev['id'])
        if not missing:return None
        self.receipt=LocalDomainEmptyReceipt(digest(self.active),digest(measurement),sorted(missing),
            sorted({x for values in missing.values() for x in values}),copy.deepcopy(measurement['native_bindings']))
        self.stage='compose'
        record=dict(event='structural_local_domain_empty',rounds_consumed=0,model_calls=0,
            semantic_failure=False,regression=False,certificate=self.receipt.__dict__,
            claim='Only the current restricted local edit interface cannot create a missing obligation-bound component; no claim about unrestricted semantic repair.')
        self.history.append(record);return record

    def interface_failure(self,kind,detail):
        self.rounds+=1
        self.history.append(dict(round=self.rounds,stage=self.stage,event='interface_rejected',
            error=dict(type=kind,detail=detail),retained_sha256=digest(self.active)))
        self.finished=self.rounds>=self.max_rounds

    def observe(self,proposal,measurement,current_targets=None,edit_record=None,baseline=None):
        if self.finished or self.rounds>=self.max_rounds:raise ValueError('controller_terminal_or_budget')
        if measurement.get('candidate_sha256')!=digest(proposal):raise ValueError('candidate_measurement_binding')
        self.rounds+=1;before=copy.deepcopy(self.active)
        decision=gate(measurement,self.strategy,self.protected,current_targets,self.necessary_obligations,baseline,self.protected_transactions)
        entry=dict(round=self.rounds,stage=self.stage,event='native_measured',
            before_sha256=digest(before),proposal_sha256=digest(proposal),
            measurement_sha256=digest(measurement),decision=decision,edit_record=edit_record)
        if decision['accepted']:
            self.active=copy.deepcopy(proposal)
            self.protected|=set(measurement['detected_ids'])
            self.protected_transactions|=set(measurement.get('transaction_detected_ids',measurement['detected_ids']))
            self.stage='local' if self.strategy=='R3' else 'free';self.receipt=None
        if self.strategy=='R3' and self.fallback_enabled and decision['semantic_failure'] and not decision['accepted'] and self.stage in ('local','compose'):
            self.receipt=FailureReceipt.from_measurement(self.stage,self.active,proposal,measurement,decision)
            self.stage='compose' if self.stage=='local' else 'regenerate'
            entry['fallback_receipt']=self.receipt.__dict__
        entry['retained_sha256']=digest(self.active);entry['next_stage']=self.stage
        self.history.append(entry)
        self.finished=decision['complete'] or bool(decision['critical_unknown']) or self.rounds>=self.max_rounds
        return entry


def output_contract(stage):
    if stage in ('free','regenerate'):
        return dict(schema={'assertions':'complete validated candidate list','reason':'string'},
            operations='Choose all predicates and timing. Every property remains editable; native history gate decides acceptance.')
    if stage=='compose':
        return dict(schema={'edits':[{'op':'add_assertion','assertion':'complete assertion object'}],'reason':'string'},
            operations='Only add complementary assertions for observed uncovered obligations. Existing active components are preserved byte-for-byte. Inspect fallback_receipt: composition is authorized either by a natively measured failed local proposal, or by an explicit local_domain_empty certificate for this restricted editing interface. The latter is not an executed failed proposal. No label alone establishes coverage.')
    return dict(schema={'edits':[{'op':'replace_field','assertion':'existing label','field':'localized field','value':'model-chosen text'}],'reason':'string'},
        operations={
            'replace_field':['assertion','field','value'],
            'set_delay':['assertion','field','expression','cycles:0..8'],
            'set_window':['assertion','field','expression','min_cycles:0..8','max_cycles:0..8','quantifier:any|all'],
            'match_transaction':['assertion','field','base_expression','request_id','response_id','cycles:0..8'],
            'except_when':['assertion','field','base_expression','exception']},
        semantics='set_delay uses $past(expression,N). set_window is a RETROSPECTIVE sampled OR/AND window; separately anchor the trigger yourself. Matching compares response_id to sampled request_id. Exceptions strengthen applicability. Exact unchanged-field echoes are ignored, but changing any unlocalized field or writing a field twice rejects the patch. No automatic semantic repair.')


def build_request(case,controller,evidence,seed,round_index,model='deepseek/deepseek-v3-0324'):
    evidence=normalize_evidence(evidence)
    context=dict(case_id=case['id'],parent_bug=case.get('parent_bug',case['id']),
        provenance=case['provenance'],specification=case.get('specification',case.get('description')),
        signals=case['signals'],necessary_obligations=case['obligations'],
        rtl=case.get('rtl',{}),sampling=case.get('sampling','posedge clk; only native-executed constructs count'),
        current_assertions=controller.active,development_observations=evidence,
        output_contract=output_contract(controller.stage),round=round_index,
        task='Repair the current assertion set using only supplied specification and confirmed development observations. Return strict JSON. No independent evaluation inputs are supplied.',
        earlier_rounds=controller.history)
    if controller.strategy in ('R1','R2','R3'):
        context['bidirectional_feedback']=dict(
            timely_missed=[e['id'] for e in evidence if e['status']=='confirmed' and e['label']=='violation'
                    and not any(a.get('failure') is True for a in e['assertions'])],
            missed=[e['id'] for e in evidence if e['status']=='confirmed' and e['label']=='violation'
                    and e.get('detection_status') not in ('timely','late_only') and not any(a.get('failure') is True for a in e['assertions'])],
            late_only_detected=[e['id'] for e in evidence if e.get('detection_status')=='late_only'],
            timing_note='A late-only native alarm detects the same confirmed violating transaction but misses its first violating sample. Do not describe it as completely undetected. Both timing improvement and new transaction detection are measured separately.',
            false_alarm=[e['id'] for e in evidence if e['status']=='confirmed' and e['label']=='legal'
                         and any(a.get('failure') is True for a in e['assertions'])])
    if controller.strategy in ('R2','R3'):
        context['history_guard']=dict(protected_target_ids=sorted(controller.protected),
            protected_any_cycle_transaction_ids=sorted(controller.protected_transactions),
            rule='Replay all acquired history; reject lost confirmed detection, legal false alarms, untriggered targets and any unknown. Rejected proposals never replace active assertions.')
    if controller.strategy=='R3':
        context['localization']=localize(controller.active,evidence,controller.localization_enabled)
        context['fallback_receipt']=controller.receipt.__dict__ if controller.receipt else None
    return dict(model=model,seed=seed+round_index*1009,temperature=0.2,max_tokens=2048,
        messages=[dict(role='system',content='Return only the strict JSON object in output_contract. No Markdown fences. Do not introduce undeclared signals. Express every intended semantic change yourself.'),
                  dict(role='user',content=json.dumps(context,separators=(',',':')))])
