"""Close the verified, campaign-owned local service after local runs terminate."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--owner',type=Path,required=True)
    parser.add_argument('--finished',type=Path,nargs='+',required=True)
    args=parser.parse_args()
    owner=args.owner.resolve()
    for run in args.finished:
        assert json.loads((run/'outcome.json').read_text())['status']!='running'
    service=owner/'service'
    pid=json.loads((service/'process.json').read_text())['pid']
    proc=Path('/proc')/str(pid)
    log=service/'server.log'
    record=dict(pid=pid,source_service=str(service),finished=[str(p) for p in args.finished],
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    if not proc.exists():
        record['status']='owned_pid_already_absent'
    else:
        argv=(proc/'cmdline').read_bytes().split(b'\0')
        stdout=(proc/'fd/1').resolve()
        matches=(Path(os.fsdecode(argv[0])).name=='ollama' and b'serve' in argv and stdout==log.resolve())
        record.update(argv=[os.fsdecode(a) for a in argv if a],stdout=str(stdout),ownership_verified=matches)
        if not matches:
            record['status']='not_stopped_ownership_not_confirmed'
        else:
            os.kill(pid,signal.SIGTERM)
            for _ in range(50):
                if not proc.exists() or (proc/'stat').read_text().split()[2]=='Z':break
                time.sleep(.1)
            record['status']='sigterm_sent_to_verified_owned_server'
    before=hashlib.sha256(log.read_bytes()).hexdigest()
    time.sleep(1)
    record['log_sha256']=hashlib.sha256(log.read_bytes()).hexdigest()
    record['log_stable_during_check']=before==record['log_sha256']
    (owner/'service_shutdown.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record))
    if record['status'].startswith('not_stopped') or not record['log_stable_during_check']:raise SystemExit(1)


if __name__=='__main__':main()
