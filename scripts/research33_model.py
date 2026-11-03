"""Counterexample contrast presentation and bounded duplicate-proposal screening.

No SVA answers are inserted. The model chooses every expression and timing.
Fingerprinting covers only token-identical operands modulo outer parentheses,
whitespace and metadata; it is NOT semantic equivalence checking.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import research17_loop as loop
from research32_model import Model as Previous, assemble
from research21_model import full_trace

dump=loop.dump


def tokens(expression):
    text=loop.model.native.unparen(expression)
    return re.findall(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\$?[A-Za-z_][A-Za-z_0-9]*|\d+|&&|\|\||==|!=|<=|>=|<<|>>|[^\s]",text)


def fingerprint(candidate):
    normalized=loop.model.native.normalize_candidate(candidate)
    return loop.sha([dict(antecedent=tokens(a['derived_antecedent']),
        consequent=tokens(a['consequent']),timing=a['derived_delay'],obligations=sorted(a['obligations']))
        for a in normalized['assertions']])


def screen(candidate,current,feedback,known_rejected=()):
    key=fingerprint(candidate)
    unresolved=bool(feedback.get('current_gap_ids'))
    if unresolved and key==fingerprint(current):
        return dict(accepted_for_native=False,kind='unchanged_known_missing_protection',fingerprint=key,
            reason='Exact Boolean token operands and timing match the already replayed current set; changing reason/outer parentheses cannot repair its confirmed missing evidence.',
            scope='Syntactic identity only; no global semantic equivalence claim.')
    if key in known_rejected:
        return dict(accepted_for_native=False,kind='repeated_previously_rejected_candidate',fingerprint=key,
            reason='This exact token-level set already failed the same development evidence. A new native run is not claimed.',scope='Same input/RTL evidence scope only.')
    return dict(accepted_for_native=True,kind='novel_candidate_requires_native_validation',fingerprint=key)


def contrast_cards(feedback,target):
    cards=[];seen=set()
    for entry in feedback.get('actual_native_evidence',[]):
        diagnostic=entry['diagnostic']
        for event in diagnostic.get('target_evidence',[]):
            if event['obligation']!=target or event.get('gap_observation')=='detected':continue
            if event.get('attribution')!='confirmed':continue
            evidence_id=event['evidence_id']
            if evidence_id in seen:continue
            seen.add(evidence_id)
            faulty,fp=full_trace(diagnostic['mutant']);fixed,cp=full_trace(diagnostic['fixed'])
            cycle=event['cycle'];b=faulty.get(cycle);f=fixed.get(cycle)
            if b is None or f is None:continue
            differing={s:dict(buggy=b.get(s),fixed=f.get(s)) for s in loop.model.SIGNALS if b.get(s)!=f.get(s)}
            unchanged={s:b[s] for s in loop.model.SIGNALS if s in b and b[s]==f.get(s)}
            cards.append(dict(evidence_id=evidence_id,scenario=entry['scenario'],cycle=cycle,
                target_evidence=copy.deepcopy(event),differing_sampled_signals=differing,
                equal_sampled_signals=unchanged,
                buggy_adjacent_samples=[faulty.get(c) for c in (cycle-1,cycle)],
                fixed_adjacent_samples=[fixed.get(c) for c in (cycle-1,cycle)],
                source=fp,correct_source=cp,
                interpretation='These are observed contrasts, not an inferred specification. The independent obligation verdict establishes the fault; derive a predicate that actually separates the legal and faulty cases.'))
    return sorted(cards,key=lambda x:(x['scenario'],x['cycle']))


class Model(Previous):
    def __init__(self,out,settings):
        super().__init__(out,settings)
        self.seen={}
        self.last_returned=None
        self.active_scope=None

    def transform_request(self,request,current,target,feedback,phase):
        request=super().transform_request(request,current,target,feedback,phase)
        old=json.loads(request['messages'][1]['content'])
        cards=contrast_cards(feedback,target)
        assert cards,'confirmed_development_contrasts_required'
        slots=[dict(id=a['id'],obligations=a['obligations']) for a in current['assertions'] if target in a['obligations']]
        schema=copy.deepcopy(old['output_schema'])
        schema['properties']['operation']['enum']=['replace_one']
        schema['properties']['assertion_id']['enum']=[a['id'] for a in slots]
        schema['properties']['assertions']['minItems']=1
        brief=dict(task='Regenerate one property for this obligation from the actual counterexamples. The previous proposals did not distinguish correct and faulty samples.',
            specification=old['boundary_repair']['specifications'],
            clock_and_reset=old['boundary_repair']['boundary_semantics'],
            contrasts=cards,
            native_conclusion='The recorded candidate triggered but did not reject these independently confirmed faulty samples. Compiling or paraphrasing the same predicate cannot fix this.',
            instruction='First identify which sampled values separate the legal and faulty traces and which values are equal. In reason briefly explain why your new consequent rejects the faulty trace while permitting the paired legal one. Generate your own complete Boolean operands and timing. Do not assume the required output in the antecedent.')
        body=dict(counterexample_first=brief,
            rtl_and_common_contract=old['rtl_and_common_contract'],
            retained_set=dict(sha256=loop.sha(current),eligible_slots=slots,
                other_properties='Retained byte-for-byte; full history checked natively.',
                old_predicate_text='Omitted to avoid repeating a known ineffective edit. Full old set remains in local artifacts and native replay.'),
            rejected_fingerprints=sorted(self.seen),
            actual_rejection=feedback.get('actual_rejection'),
            interface_diagnostic=feedback.get('transport_or_interface_diagnostic'),
            output_schema=schema,
            final_instruction='Do not equate equal payload values with compliance with the whole output obligation. Re-check the differing sampled values in counterexample_first, the required timing and reset cancellation. Return only the edit JSON. Unchanged and previously rejected token-level sets are refused before simulation; a novel expression still needs full native history validation.')
        request['messages']=[dict(role='system',content='Repair a confirmed hardware assertion coverage gap. Evidence and specification are authoritative; no successful predicate is supplied. Derive a fresh expression from the numeric contrasts instead of copying a prior edit. Return the exact JSON schema. The harness supplies clock/reset.'),
            dict(role='user',content=json.dumps(body))]
        return request

    def call(self,folder,current,target,feedback,phase):
        # Only a prior rejected candidate with a concrete decision is cached;
        # cache identity includes the unchanged accepted state and target IDs.
        scope=loop.sha(dict(current=fingerprint(current),targets=feedback.get('current_gap_ids')))
        if scope!=self.active_scope:
            self.seen={};self.last_returned=None;self.active_scope=scope
        if self.last_returned and feedback.get('actual_rejection',{}).get('accepted') is False:
            previous_scope,previous_key,source=self.last_returned
            if previous_scope==scope:self.seen[previous_key]=source
        result,candidate=super().call(folder,current,target,feedback,phase)
        if candidate is None:return result,None
        decision=screen(candidate,current,feedback,self.seen)
        dump(Path(folder)/'proposal_screen.json',decision)
        self.last_returned=(scope,decision['fingerprint'],str(folder))
        if not decision['accepted_for_native']:
            result.update(candidate_status='proposal_rejected_before_native',proposal_rejection=decision,
                native_compile_attempted=False,native_execution_attempted=False)
            dump(Path(folder)/'result.json',result)
            dump(self.out/'model_cost_running.json',self.calls)
            return result,None
        return result,candidate
