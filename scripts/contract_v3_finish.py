"""Finish queued v3 stages only after the complete global method freeze exists."""
import json,subprocess,time
from pathlib import Path
ROOT=Path('/mnt/d/AssertionForge-main1');OUT=ROOT/'deliverables/repair_contract_v3_20261010'
def main():
    start=time.perf_counter()
    while not (OUT/'method_freeze.json').exists():
        if time.perf_counter()-start>7200:raise TimeoutError('global method freeze not available; no hidden access performed')
        time.sleep(2)
    stages=[('hidden',['python3',str(ROOT/'scripts/run_contract_v3.py'),'hidden']),('report_initial',['python3',str(ROOT/'scripts/contract_v3_report.py')]),
            ('audit',['python3',str(ROOT/'scripts/contract_v3_audit.py')]),('report_final',['python3',str(ROOT/'scripts/contract_v3_report.py')])]
    for name,cmd in stages:
        t=time.perf_counter();before=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        with (OUT/(name+'.stdout')).open('w') as so,(OUT/(name+'.stderr')).open('w') as se:
            result=subprocess.run(cmd,cwd=ROOT,stdout=so,stderr=se)
        record={'argv':cmd,'cwd':str(ROOT),'started_utc':before,'finished_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'exit_code':result.returncode,'wall_seconds':time.perf_counter()-t}
        (OUT/(name+'.command.json')).write_text(json.dumps(record,indent=2)+'\n')
        print(name,result.returncode,round(record['wall_seconds'],2),flush=True)
        if result.returncode:raise SystemExit(result.returncode)
if __name__=='__main__':main()
