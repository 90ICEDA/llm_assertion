"""Complete pinned include closure; preserve first failed build and its code."""
import argparse
from pathlib import Path
from unittest.mock import patch
import research152_source_scope_recheck as old


def prepare(out):
    old.prepare(out)
    name='include/common_cells/deprecated/registers.svh'
    target=out/'sources/common_cells'/name;target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(old.git_blob(old.ROOT/'external/common_cells',old.CC,name))
    bindings=old.read(out/'source_bindings.json')
    f=old.ROOT/'external/common_cells'/name;bindings[old.rel(f)]=old.sha(f)
    bindings[old.rel(Path(__file__))]=old.sha(Path(__file__))
    old.dump(out/'source_bindings.json',bindings)
    old.dump(out/'build_dependency_correction.json',dict(reason='Original registers.svh includes deprecated/registers.svh from the same pinned commit.',
        dependency=name,commit=old.CC,sha256=old.sha(target),original_r01_result='compile failure, no execution; preserved',
        acceptance_and_stimuli_changed=False))
    old.dump(out/'sealed.json',{f.relative_to(out).as_posix():old.sha(f) for f in out.rglob('*') if f.is_file() and f.name!='sealed.json'})
    old.verify(out)


def run(prep,out):
    original=old.native.run_native
    def with_explicit_skip(source,directory,**kw):
        result=original(source,directory,**kw)
        if result['compile_status']!='passed':
            # A clearly marked skip note, never an execution command/result.
            (Path(directory)/'execute.log').write_text('NOT EXECUTED: compilation failed; see compile.log and result.json.\n')
        return result
    with patch.object(old.native,'run_native',with_explicit_skip):old.run(prep,out)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','run'));ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
