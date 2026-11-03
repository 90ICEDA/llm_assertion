"""Read-only qualification reanalysis after attribution/drain scope review."""
import json
from research15_search_runtime import ROOT,MODES,write_json
from research15_search_experiment import adjudicate

if __name__=='__main__':
    folder=ROOT/'deliverables/research15_search_20261015_r01/engineering_qualification'
    candidate=json.loads((folder/'candidate.json').read_text())
    rows=json.loads((folder/'stimulus.json').read_text())
    runs={m:dict(folder=str(folder/m),native=json.loads((folder/m/'result.json').read_text())) for m in MODES}
    result=adjudicate(rows,runs,candidate,'engineering_qualification',persist=False)
    result.update(read_only=True,new_native_executions=0,
        correction='Original qualification used an earlier attribution adapter. This reanalysis uses per-reset-epoch first violation and does not call an alarm mapped to another obligation a silent miss.',
        old_artifacts_modified=False)
    write_json(folder/'read_only_reaudit.json',result)
    print(json.dumps(dict(status=result['status'],reset=[x for x in result['mapping'] if x['obligation']=='reset_cancellation'],unknown=result['errors']),indent=2))
