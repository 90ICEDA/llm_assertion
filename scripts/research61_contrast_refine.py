"""Real local refinement with source-bound decoded legal/violation pairs.

The table is calculated from existing development samples, not from a new
property. Predicate strings remain exclusively the real model's output.
"""
import argparse
import copy
import json
import shutil
from pathlib import Path
from unittest.mock import patch
import research60_compact_local as compact

base=compact.base;g=compact.g
SOURCE=g.ROOT/'deliverables/research60_local_compact_20261023_r02'
ORIGINAL_NOVELTY=g.prior.prior.previous.novelty
ORIGINAL_RUN=base.run
ORIGINAL_REQUEST=compact.request


def decoded_table():
    result=g.read(SOURCE/'v0/alignment/result.json')
    grouped={}
    for row in result['ledger']:
        sample=row['sample'];word=sample['instruction']
        key=(sample['transaction_id'],word,sample['instr_new'])
        entry=grouped.setdefault(key,dict(transaction=key[0],instruction_hex=f'0x{word:08x}',
            fields=dict(opcode=word&127,bit28=(word>>28)&1,bit31=(word>>31)&1,funct3=(word>>12)&7),
            instr_new=key[2],sample_ids=[],phases=[],observations=[]))
        if sample['sample_id'] not in entry['sample_ids']:entry['sample_ids'].append(sample['sample_id'])
        if sample['phase'] not in entry['phases']:entry['phases'].append(sample['phase'])
        obs=dict(configuration=row['configuration'],revision=row['revision'],expected_illegal=row['expected'],
            actual_illegal=row['observed'],sva_failed=any(a['failed'] for a in row['native']['assertions']))
        if obs not in entry['observations']:entry['observations'].append(obs)
    # Compact only identical observations across configurations. Preserve varying
    # legal/illegal output for E/M configurations instead of choosing one answer.
    for entry in grouped.values():
        observations={}
        for obs in entry['observations']:
            config=obs['configuration'];rest={k:v for k,v in obs.items() if k!='configuration'}
            item=observations.setdefault(json.dumps(rest,sort_keys=True),dict(**rest,configurations=[]))
            item['configurations'].append(config)
        entry['observations']=list(observations.values())
    return list(grouped.values())


def previous_rejections():
    candidate=g.read(SOURCE/'v0/model_call/candidate.json')
    return [dict(source=(SOURCE/'v0/model_call/candidate.json').as_posix(),signature=g.prior.prior.previous.op_signature(candidate))]


def novelty(candidate,known):return ORIGINAL_NOVELTY(candidate,known+previous_rejections())


def request(prep,feedback,seed):
    req=ORIGINAL_REQUEST(prep,None,seed)
    body=json.loads(req['messages'][1]['content'])
    body.pop('native_development_samples')
    body['decoded_development_pairs']=decoded_table()
    body['table_semantics']='Fields are bit-extracted from native instruction words. Expected outputs come from the independent ISA checker; actual outputs come from original RTL. Repeated identical observations are grouped without discarding any sample or configuration. These are development data, not independent test data.'
    body['actual_feedback']=feedback if feedback is not None else dict(
        actual_model_proposal=g.read(SOURCE/'v0/model_call/model_edit.json'),
        native_counts=g.read(SOURCE/'v0/alignment/result.json')['counts'],
        phase_counts=g.read(SOURCE/'v0/alignment/focus_gate.json')['phases'])
    body['task']='Repair the actual over-broad OP property. Explain which decoded fields distinguish the legal false alarms from the required illegal OP words, then express that same distinction in your predicate. Cover first and held samples, retain BRANCH unchanged. Do not use observed illegal_insn in the antecedent to hide failures. Do not enumerate sample words. Use the confirmed OP rule, not the unrelated reserved BRANCH funct3 rule. Output only OP additions/replacements using the declared interface; generate every operand yourself.'
    req['messages'][0]['content']='You are repairing a hardware assertion from real false-positive evidence. Return JSON matching the contract. Derive the OP applicability from the confirmed rule and decoded table; do not copy an already rejected predicate. A changed explanation without a corrected executable condition is rejected.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['options'].update(temperature=0.2,num_predict=1024)
    return req


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    candidate=g.read(SOURCE/'v0/model_call/candidate.json')
    assert g.prior.diagnostic.audit_native(SOURCE/'v0/alignment',candidate,base.P,'alignment')==240
    table=decoded_table();rows=g.read(SOURCE/'v0/alignment/result.json')['ledger']
    # Independently re-expand each table row to the original sampled observations.
    checks=[]
    for row in rows:
        sample=row['sample'];word=sample['instruction']
        matches=[e for e in table if sample['sample_id'] in e['sample_ids'] and e['transaction']==sample['transaction_id']]
        assert len(matches)==1;entry=matches[0]
        assert int(entry['instruction_hex'],16)==word and entry['instr_new']==sample['instr_new'] and sample['phase'] in entry['phases']
        bits=f'{word:032b}'
        assert entry['fields']==dict(opcode=int(bits[-7:],2),bit28=int(bits[3]),bit31=int(bits[0]),funct3=int(bits[-15:-12],2))
        observed=[o for o in entry['observations'] if o['revision']==row['revision'] and row['configuration'] in o['configurations']]
        assert len(observed)==1 and observed[0]['expected_illegal']==row['expected'] and observed[0]['actual_illegal']==row['observed']
        assert observed[0]['sva_failed']==any(a['failed'] for a in row['native']['assertions'])
        checks.append(row['evidence_id'])
    req=request(base.P,None,6001)
    body=json.loads(req['messages'][1]['content'])
    assert len(body['current_assertions']['assertions'])==1
    assert g.read(base.P/'qualification/local_positive/candidate.json')['assertions'][1]['antecedent'] not in json.dumps(req)
    assert not novelty(candidate,[])['accepted']
    g.dump(out/'request.preview.json',req);g.dump(out/'decoded_development_pairs.json',table)
    g.dump(out/'checks.json',dict(passed=True,native_rows_reconciled=len(checks),evidence_ids=checks,known_repeat_rejected=True))
    files=[SOURCE/'v0/alignment/result.json',SOURCE/'v0/model_call/model_edit.json',SOURCE/'v0/model_call/candidate.json',Path(__file__)]
    g.dump(out/'sources.json',{p.relative_to(g.ROOT).as_posix():g.old.digest(p) for p in files})
    print('PREPARED',len(table),'groups,',len(checks),'native rows reconciled',flush=True)


def run(out):
    def proxy(folder,iterations,timeout,context_validator):
        return ORIGINAL_RUN(folder,iterations=2,timeout=timeout,context_validator=context_validator)
    try:
        with patch.object(compact,'request',request),patch.object(base,'run',proxy),patch.object(g.prior.prior.previous,'novelty',novelty):
            compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'contrast_adapter_snapshot.py')
            g.dump(out/'decoded_development_pairs.json',decoded_table())
            g.dump(out/'extra_known_rejections.json',previous_rejections())
            protocol=g.read(out/'protocol.json');protocol.update(scope='research61_local_decoded_contrast',maximum_calls=2,
                changes='Real local Qwen refinement from measured legal false alarms and decoded development pairs; max2 calls, stop after full acceptance; inherited original9/151 gates unchanged. No new independent data.',
                cross_run_repeat_check='research60 Qwen failure signature is rejected before native execution.')
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true')
    a=p.parse_args();(prepare if a.prepare else run)(a.out.resolve())
