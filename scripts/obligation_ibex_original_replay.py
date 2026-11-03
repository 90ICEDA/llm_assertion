"""Refresh original historical tests in a new folder, preserving old runs."""
import json
import shutil
import obligation_continuation as cont
from obligation_continuation import x, PRIOR


def main():
    x.OUT=x.ROOT/'deliverables'/cont.NAME
    source=PRIOR/'historical_screening/ibex_54';out=x.OUT/'historical_original_replay';out.mkdir(exist_ok=False)
    records=[]
    for revision in ('before','after'):
        for cohort in ('benchmark','boundary'):
            folder=out/revision/cohort;folder.mkdir(parents=True)
            for name in ('ibex_defines.sv','ibex_compressed_decoder.sv'):shutil.copyfile(source/revision/name,folder/name)
            shutil.copyfile(source/(cohort+'_tb.sv'),folder/'tb.sv')
            compile=x.command(['iverilog','-g2012','-s','tb','-o','sim.out','ibex_defines.sv','ibex_compressed_decoder.sv','tb.sv'],folder,'compile')
            assert compile['status']=='ok'
            simulate=x.command(['vvp','sim.out'],folder,'simulate')
            text=(folder/'simulate.stdout').read_text();old=(source/'execution'/revision/cohort/'simulate.stdout').read_text()
            # VCD/absolute filenames may differ; preserve payload test output.
            normalize=lambda s:[z for z in s.splitlines() if not z.startswith('VCD info:')]
            same=normalize(text)==normalize(old)
            record=dict(revision=revision,cohort=cohort,compile=compile,simulate=simulate,prior_exact_test_stdout=same,
                failure_is_expected_design_assertion=revision=='before',source_hashes={name:x.sha(folder/name) for name in ('ibex_defines.sv','ibex_compressed_decoder.sv','tb.sv')})
            records.append(record)
            assert same,(revision,cohort)
            assert simulate['exit_code']==(1 if revision=='before' else 0)
            (folder/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd "$(dirname "$0")"\niverilog -g2012 -s tb -o replay.out ibex_defines.sv ibex_compressed_decoder.sv tb.sv\nvvp replay.out\n')
    x.dump(out/'summary.json',dict(records=records,passed_reproduction=True,before_expected_failure=True,
        original_benchmark_failures_before=5,original_benchmark_failures_after=0,boundary_failures_before=175,boundary_failures_after=0))
    print('IBEX original/boundary replay exact: before fails, after passes',flush=True)


if __name__=='__main__':main()
