"""Verify the saved historical patch against downloaded immutable revisions."""
import argparse
import json
import shutil
import run_repair_contract as e


def main(run):
    root=e.ROOT/'deliverables'/run/'historical_screening/ibex_54'
    out=root/'patch_validation';out.mkdir(exist_ok=False);(out/'rtl').mkdir()
    shutil.copy2(root/'before/ibex_compressed_decoder.sv',out/'rtl/ibex_compressed_decoder.sv')
    check=e.command(['git','apply','--check',str(root/'fix.patch')],out,'patch_check')
    applied=e.command(['git','apply',str(root/'fix.patch')],out,'patch_apply') if check['status']=='ok' else None
    same=applied is not None and applied['status']=='ok' and (out/'rtl/ibex_compressed_decoder.sv').read_bytes()==(root/'after/ibex_compressed_decoder.sv').read_bytes()
    e.dump(out/'result.json',dict(check=check,apply=applied,patched_module_bytes_equal_downloaded_after=same,
        scope='isolated copy only; no repository reset/checkout or historical source modification',
        source_commits=e.read(root/'source.json')))
    assert same
    print(json.dumps(dict(patch_applies=True,bytes_match_after=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
