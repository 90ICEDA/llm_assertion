"""Source-bound public case recruitment/readiness registry; no native execution."""
import argparse
import hashlib
import json
from pathlib import Path
import research194_cases as c
import research194_ibex as ibex


def run(out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    qualifications={
      'arbiter':['research194_cases_qualification_20261103_r02/arbiter/measurement.json'],
      'counter':['research194_cases_qualification_20261103_r02/counter/measurement.json'],
      'uart':['research194_cases_qualification_20261103_r02/uart/measurement.json','research194_cases_uart_multitx_20261103_r01/measurement.json'],
      'ibex_flush':['research194_ibex_full_qualification_20261103_r01/initial/measurement.json','research194_ibex_full_qualification_20261103_r01/local_control/measurement.json']}
    for case in ('arbiter','counter','uart','ibex_flush'):
        cfg=c.get_case(case);q=[]
        for rel in qualifications[case]:
            path=c.ROOT/'deliverables'/rel
            if not path.exists():q.append(dict(path=str(path),available=False));continue
            m=json.loads(path.read_text());q.append(dict(path=str(path),available=True,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
              native_complete=m['native_complete'],reference_complete=m['reference_complete'],targets=len(m['targets']),detected=len(m['detected_ids']),
              correct_legal=all(not j['reference']['unknown'] and all(z['passed'] for z in j['reference']['checks']) for j in m['executions'] if j['variant']=='correct'),
              actual_trigger_events=sum(len(j['result']['triggers']) for j in m['executions']),unknown=len(m['critical_unknown']),cost=m['cost']))
        rows.append(dict(id=case,parent_bug=cfg.get('parent_bug',case+'/artificial'),module=cfg['module'],
          historical_fix_confirmed=cfg['provenance']['historical_fix_confirmed'],provenance=cfg['provenance'],
          mechanism={'arbiter':'fixed priority; registered response; acknowledge hold; reset','counter':'exact next-cycle step; modular boundary; clear/load precedence; asynchronous reset',
                     'uart':'serial frame data transaction; divider timing; disable/reset cancellation; two distinct payloads; paused ticks',
                     'ibex_flush':'original exception/interrupt flush across instruction expansion; ready/valid stall; reset'}[case],
          obligations=cfg['obligations'],specification=cfg.get('specification',cfg.get('spec')),initial=cfg['initial'],candidate_pool=cfg['candidate_pool'],
          development_query_families=[x['family'] for x in c.query_pool(case,'development')],independent_queries_not_constructed=True,
          independent_reference=True,qualification=q,
          acceptance_conditions=['freeze candidates and source hashes before independent access','native execution completes and input trace aligns','paired correct RTL independently legal',
             'target violations adjudicated by independent monitor','no-exposure and unclassified alarms remain separate','final results grouped by parent and transaction, not failed cycles'],
          limitations=['Handwritten seed/qualification controls are not model improvements.','Qualification artifacts predate the final conservative mutant-legal reclassification; formal trials must use frozen final cases source.']+
            ([] if case=='ibex_flush' else ['No confirmed historical upstream Bug/fix pair; faults are explicitly artificial.'])))
    c.dump(out/'registry.json',dict(cases=rows,case_adapter_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),new_native_queries=0,new_model_calls=0))
    print(json.dumps(dict(cases=len(rows),historical=sum(r['historical_fix_confirmed'] for r in rows))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.out.resolve())
