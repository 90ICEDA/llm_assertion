"""Summarize measured OP improvement, new false alarms and the HTTP failure."""
import argparse
import json
from collections import Counter
from pathlib import Path
import research56_fresh_op as g


def run(root,out):
    cohorts={};examples=[]
    for cohort in ('history','search'):
        r=g.read(root/f'v0/{cohort}/result.json');info=g.old.acceptance.inspect(r['ledger'])
        cohorts[cohort]=dict(counts=r['counts'],required_untriggered=len(r['required_untriggered']),
            per_obligation={ob:{k:len(v) for k,v in m.items()} for ob,m in r['mapping'].items()},
            false_positive_by_revision=dict(Counter(info['rows'][k]['revision'] for k in info['false_positives'])))
        for key in sorted(info['false_positives']):
            row=info['rows'][key];s=row['sample'];word=s['instruction']
            if row['revision']!='after':continue
            examples.append(dict(cohort=cohort,evidence_id=key,sample_id=s['sample_id'],transaction_id=s['transaction_id'],phase=s['phase'],
                instruction_hex=f'0x{word:08x}',opcode=word&127,funct3=(word>>12)&7,funct7=(word>>25)&127,
                bit28=(word>>28)&1,bit31=(word>>31)&1,configuration=row['configuration'],
                expected=row['expected'],observed=row['observed'],native=row['native'],
                note='Actual fixed-RTL false alarm on an independently classified sample.'))
            break
    guards=g.read(root/'v0/all_property_guard.json')
    requests=[]
    for version in ('v0','v1'):
        q=g.read(root/version/'model_call/request.json')
        requests.append(dict(version=version,message_utf8_bytes=sum(len(m['content'].encode()) for m in q['messages']),
            requested_output_tokens=q['max_tokens'],effective_seed=q['seed'],
            note='UTF8 byte length is not actual input token count or proof of service context overflow.'))
    g.dump(out/'failure_diagnosis.json',dict(cohorts=cohorts,actual_false_positive_examples=examples,
        all_property_guard_counts={c:dict(false_alarms=len(v['false_alarms']),unknown=len(v['unknown'])) for c,v in guards.items()},
        requests=requests,second_call=g.read(root/'v1/model_call/result.json'),
        http_root_cause='Unknown: safe transport recorded HTTP400 but no provider error body. Context size and request validation are hypotheses, not findings.'))
    print(json.dumps(dict(cohorts={c:v['counts'] for c,v in cohorts.items()},examples=examples,requests=requests)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.run.resolve(),a.out.resolve())
