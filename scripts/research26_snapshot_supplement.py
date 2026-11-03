"""Append two omitted dependency snapshots from a contemporaneous frozen copy."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil


root=Path(__file__).resolve().parents[1]
run=root/'deliverables/research26_closed_loop_20261020_r04'
source=root/'deliverables/research26_closed_loop_20261020_r03/source_snapshot'
out=run/'snapshot_supplement'
out.mkdir(exist_ok=False)
hashes=run/'source_snapshot/hashes.json'
shutil.copy2(hashes,out/'original_hashes.json')
mapping=json.loads(hashes.read_text())
added=[]
for name in ('research23_model.py','research24_model.py'):
    original=source/name
    assert original.read_bytes()==(root/'scripts'/name).read_bytes()
    target=run/'source_snapshot'/name
    assert not target.exists()
    shutil.copy2(original,target)
    mapping[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    added.append(dict(name=name,source=str(original),sha256=mapping[name]))
hashes.write_text(json.dumps(mapping,indent=2)+'\n')
record=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    reason='Remote replacement adapter imports the schema helper and local superclass module. Initial snapshot selection omitted these dependencies.',
    added=added,original_hashes='snapshot_supplement/original_hashes.json',
    scope='Copied unchanged modules from the earlier r03 run snapshot and verified byte equality with current source. No model request, response, RTL or SVA modified.')
(out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
shutil.copy2(__file__,out/'script.py')
print(json.dumps(record))
