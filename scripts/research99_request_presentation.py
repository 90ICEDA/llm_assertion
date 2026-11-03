"""Two lossless presentations of the same permitted development evidence.

No model call, predicate repair, private answers or independent tests are read.
C retains the old candidate representation. T projects editable fields and
factors paired native observations into a sample-bound table.
"""
import copy
import json
import re
import research94_prospective_gate_pilot as prior
from research98_bottleneck_diagnosis import paired_witness

FIELDS=('antecedent','consequent','timing','obligations')
SHARED=('sample','configuration','obligation')


def bind_pairs(visible,records):
    pairs=[]
    for example in visible['development_counterexamples']:
        cohort=example['cohort']
        if cohort not in visible['visible_counts'] or cohort not in records:
            raise ValueError('cohort_not_allowed')
        paired_witness(example,records[cohort])  # Exact full identity and output check.
        ledger=records[cohort]['ledger']
        row=next(r for r in ledger if r['evidence_id']==example['evidence_id'])
        mate=[r for r in ledger if all(r[k]==row[k] for k in SHARED) and r['revision']!=row['revision']]
        if len(mate)!=1:raise ValueError('revision_binding')
        rows=sorted([copy.deepcopy(row),copy.deepcopy(mate[0])],key=lambda r:r['revision'],reverse=True)
        if {r['revision'] for r in rows}!={'before','after'}:raise ValueError('revision_names')
        pairs.append(dict(selected_evidence_id=row['evidence_id'],kind=example['kind'],cohort=cohort,rows=rows))
    return pairs


def compact_pairs(pairs,bit_indices):
    tables=[]
    for pair in pairs:
        rows=pair['rows'];first=rows[0]
        if not all(all(r[k]==first[k] for k in SHARED) for r in rows):raise ValueError('shared_identity')
        sample=first['sample'];w=sample['instruction']
        tables.append(dict(selected_evidence_id=pair['selected_evidence_id'],kind=pair['kind'],cohort=pair['cohort'],
            **{k:copy.deepcopy(first[k]) for k in SHARED},
            decoded=dict(instruction_hex=f'0x{w:08x}',opcode_decimal=w&127,
                bit_values={str(b):(w>>b)&1 for b in bit_indices},
                phase_name='first' if sample['instr_new'] else 'held'),
            revisions=[{k:copy.deepcopy(v) for k,v in r.items() if k not in SHARED} for r in rows]))
    return tables


def expand_pairs(tables):
    result=[]
    for t in tables:
        w=t['sample']['instruction'];d=t['decoded']
        if d['instruction_hex']!=f'0x{w:08x}' or d['opcode_decimal']!=w&127:raise ValueError('bad_decode')
        if any(v!=((w>>int(k))&1) for k,v in d['bit_values'].items()):raise ValueError('bad_bit')
        if d['phase_name']!=('first' if t['sample']['instr_new'] else 'held'):raise ValueError('bad_phase')
        result.append(dict(selected_evidence_id=t['selected_evidence_id'],kind=t['kind'],cohort=t['cohort'],
            rows=[dict(**{k:copy.deepcopy(t[k]) for k in SHARED},**copy.deepcopy(r)) for r in t['revisions']]))
    return result


def request(current,visible,records,variant,iteration,diagnostic=None):
    if variant not in ('C','T'):raise ValueError('unknown_variant')
    req=prior.payload(current,visible,iteration)
    body=json.loads(req['messages'][1]['content'])
    # Shared label, schema description, selection and evidence information.
    body['current_candidate_status']='Failed candidate to repair; it is not the specification or an accepted solution. Do not preserve a predicate merely because it is present here.'
    body['output_contract']+=' Each assertion must contain EXACTLY antecedent,consequent,timing,obligations. Do not output property,id,delay or other metadata. Native acceptance is unchanged.'
    pairs=bind_pairs(visible,records)
    feedback={k:copy.deepcopy(v) for k,v in visible.items() if k!='development_counterexamples'}
    bits={body['actual_model_op_rule']['bit_index']}
    for assertion in body['current_op']:
        bits.update(int(s) for s in re.findall(r'instr\[(\d+)\]',assertion['antecedent']))
    if variant=='C':feedback['paired_development_records']=pairs
    else:
        body['current_op']=[{k:copy.deepcopy(a[k]) for k in FIELDS} for a in body['current_op']]
        table=compact_pairs(pairs,sorted(bits));assert expand_pairs(table)==pairs
        feedback['paired_sample_table']=table
    if diagnostic is not None:feedback['actual_rejection']=copy.deepcopy(diagnostic)
    body['actual_feedback']=feedback
    body['acceptance']='Unchanged native current9, search36 and history115 acceptance, required first/held triggers, zero legal false alarms, target misses or critical unknown. No independent-test result is supplied. Interface and whole-set preservation checks apply in both presentations.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['seed']=10007+iteration
    return req
