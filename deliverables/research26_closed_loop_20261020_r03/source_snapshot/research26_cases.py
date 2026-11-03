"""Explicitly promote a published completed test batch to development."""
import copy
import hashlib
from pathlib import Path
import research17_model as base


def promoted_cases(run):
    run=Path(run).resolve()
    assert base.ROOT in run.parents
    assert base.read(run/'outcome.json').get('independent_executed') is True
    result=[]
    for path in sorted((run/'core_independent/core').glob('case_*/case.json')):
        item=copy.deepcopy(base.read(path));previous=item['id']
        item.update(id='promoted26:'+previous,split='development',
            source='published_test_promoted_after_observed_failure',
            provenance=dict(source_case=str(path),source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                previous_id=previous,row_changes=[],
                promotion='This completed test batch is development for the new repair. Its old frozen evaluation remains unchanged. It cannot be claimed as independent for the new candidate.'))
        result.append(item)
    assert len(result)==len(base.read(run/'core_independent/split.json')['cases'])
    return result
