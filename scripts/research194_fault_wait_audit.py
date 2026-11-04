"""Wait on completion markers only, then run the read-only augmentation audit.

No independent plan, input, result, or freeze file is read before completion.
No experiment, model request, or native job is started or retried.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time


def marker(path):
    if not path.exists():return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError:return None


def run(campaign,out,interval=30):
    completion=campaign/'independent'/'outcome.json'
    print(json.dumps(dict(status='waiting_for_independent_completion',marker=str(completion),reads_before_completion='outcome and interruption markers only')),flush=True)
    while True:
        finished=marker(completion)
        if finished and finished.get('status')=='completed':
            print(json.dumps(dict(status='independent_completed_start_read_only_audit')),flush=True)
            command=[sys.executable,str(Path(__file__).with_name('research194_fault_augmentation_audit.py')),'--campaign',str(campaign),'--out',str(out)]
            result=subprocess.run(command,check=False)
            print(json.dumps(dict(status='read_only_audit_finished',returncode=result.returncode,out=str(out))),flush=True)
            return result.returncode
        interruption=marker(campaign/'interruption.json')
        if interruption:
            print(json.dumps(dict(status='campaign_interrupted_no_acceptance',reason=interruption,experiment_retry=False),ensure_ascii=False),flush=True)
            return 2
        terminal=marker(campaign/'outcome.json')
        if terminal and terminal.get('status')!='completed':
            print(json.dumps(dict(status='campaign_closed_without_completed_acceptance',reason=terminal,experiment_retry=False),ensure_ascii=False),flush=True)
            return 2
        time.sleep(interval)


if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,default=root/'deliverables/research194_campaign_execute_20261103_r01')
    p.add_argument('--out',type=Path,default=root/'deliverables/research194_fault_augmentation_audit_20261103_r01')
    a=p.parse_args();sys.exit(run(a.campaign.resolve(),a.out.resolve()))
