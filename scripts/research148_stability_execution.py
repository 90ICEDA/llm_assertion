"""Batch execution with common holdout inputs bound to each audited version.

Preserves research146 and research147 r01 local checks. No model run used that
entry point. Its native auditor additionally requires a per-version input file;
this wrapper binds the already frozen common input, never regenerating it.
"""
from research146_stability_batch import *
import research146_stability_batch as original

_independent=original.independent


def bind_shared_inputs(out,folder):
    assert (out/'global_freeze.json').exists()
    generation=read(out/'test_generation.json')
    assert generation['freeze_sha256']==digest(out/'global_freeze.json')
    assert generation['model_dispatch_finished']
    assert folder.parent==out/'tested_versions'
    assert folder.name in read(out/'global_freeze.json')['unique_test_versions']
    candidate=read(folder/'candidate.json')
    assert c.x.old.acceptance.sha(candidate)==folder.name
    source=out/'independent_cases.json';target=folder/'independent_cases.json'
    assert not target.exists()
    shutil.copy2(source,target)
    assert digest(source)==digest(target)
    dump(folder/'shared_inputs_binding.json',dict(source=rel(source),sha256=digest(source),
        candidate_sha256=folder.name,freeze_sha256=generation['freeze_sha256']))


def independent(prep,out,versions,deadline):
    audit=c.x.holdout.base.native_audit
    def bound_audit(folder,result):
        bind_shared_inputs(out,folder)
        return audit(folder,result)
    with patch.object(c.x.holdout.base,'native_audit',bound_audit):
        return _independent(prep,out,versions,deadline)


def run(prep,out,authorization):
    with patch.object(original,'independent',independent):
        return original.run(prep,out,authorization)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
