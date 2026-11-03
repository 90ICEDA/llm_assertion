"""Audit history provenance and the unsupported stat upstream-spec attribution."""
from pathlib import Path
import json
import shutil
import research15_history as e


def main():
    e.guard();out=e.OUT/'stat_spec';case=e.ROOT/'rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early'
    files=[case/'spec.md',case/'case_metadata.json',case/'correct.v',case/'buggy.v']
    for p in files:shutil.copy2(p,out/('local_'+p.name))
    upstream=out/'upstream_axis_stat_counter.v';local=e.ROOT/'external/verilog-axis/rtl/axis_stat_counter.v'
    up=upstream.read_text();meta=e.read(case/'case_metadata.json');signals=['frame_done_i','frame_len_i','stat_valid_o','stat_len_o']
    report=dict(parent_bug='case505_axis_stat_counter_frame_pulse_early',status='upstream_timing_and_overlap_not_confirmed',
        source_url=f"https://raw.githubusercontent.com/alexforencich/verilog-axis/{meta['source_commit']}/rtl/axis_stat_counter.v",
        source_commit=meta['source_commit'],official_download_sha256=e.sha(upstream),local_external_sha256=e.sha(local),
        official_equals_local_after_universal_newlines=up==local.read_text(),
        cited_upstream_contains_case_signals={s:s in up for s in signals},
        local_synthetic_contains_case_signals={s:s in (case/'correct.v').read_text() for s in signals},
        upstream_interface='AXI monitor handshake inputs monitor_axis_tvalid/tready/tlast plus trigger; serial statistics output m_axis_tdata/tvalid/tready; busy',
        local_interface='frame_done_i/frame_len_i input and stat_valid_o/stat_len_o output; no AXI handshake',
        upstream_line_references={k:[i for i,line in enumerate(up.splitlines(),1) if k in line] for k in ['module axis_stat_counter','monitor_axis_tvalid','m_axis_tready','input  wire                   trigger','if (trigger)','monitor_axis_tready && monitor_axis_tvalid']},
        local_spec=(case/'spec.md').read_text().strip(),
        local_metadata_claim=dict(mutation_kind=meta['mutation_kind'],status=meta['status']),
        conclusion='The cited historical upstream module does not expose the local two-sample interface. No mapping or upstream guarantee for local frame_done overlap/two-cycle semantics is established by this cited source. Local generated prose can define a conditional engineering experiment but cannot establish historical upstream behavior.',
        overlap='unknown for original historical provenance; do not count a stat whole-parent success',
        limitations='This audits the exact cited source, not every possible historical source or unpublished specification. No attempt to infer permission merely from absence of a ready port.',
        saved_local_inputs={str(p.relative_to(e.ROOT)):e.sha(p) for p in files})
    e.dump(out/'audit.json',report)
    summary=e.read(e.OUT/'summary.json');w=e.read(e.OUT/'repair_witnesses.json')
    examples=[]
    for ob in summary['covered_repair_obligations']:
        one=next(z for z in w if z['obligation']==ob and z['configuration']==0)
        samples=e.read(e.OUT/'samples.json');txn=[s for s in samples if s['transaction_id']==one['transaction_id']]
        before=e.read(e.OUT/'execution/before/independent_adjudication.json');after=e.read(e.OUT/'execution/after/independent_adjudication.json')
        examples.append(dict(obligation=ob,witness=one,transaction_samples=txn,
            before=[z for z in before if z['transaction_id']==one['transaction_id'] and z['configuration']==0],
            after=[z for z in after if z['transaction_id']==one['transaction_id'] and z['configuration']==0]))
    e.dump(e.OUT/'representative_witnesses.json',examples)
    e.dump(e.OUT/'audit.json',dict(source_freeze_verified=True,exact_original_patch_matches=e.read(e.OUT/'patch_validation/result.json')['exact_patch_applies'],original_module_admitted=summary['admitted_original_module'],sample_checks_per_revision=summary['results'][0]['checks'],native_failure_equals_independent_oracle=True,independent_parent_bugs=1,independent_repair_obligations=2,source_downloads_original=True,full_core=False,LLM=False,formal_proof=False,stat_upstream_spec_confirmed=False,limitations=['The current tests are new reproduction scenes, not independent evaluation of a learned/frozen LLM assertion set.','115 transaction stimuli, 458 samples and 3 parameterizations share one historical parent bug; 423 failures are not 423 independent findings.','The benchmark ALU encoding is normalized to low register indices in the new stimulus; original full-core HWE-Bench program is archived but not executed.','RV32E configured controls use low registers; exhaustive RV32E qualification is not established.']))
    p=e.OUT/'README.md';text=p.read_text();text+='\n## Source/specification audit and new-run commands\n\n`stat_spec/audit.json` verifies the exact cited verilog-axis source. It has an AXI monitor/statistics interface and none of the four local frame_done/stat_valid signals. Historical two-cycle/overlap semantics therefore remain unconfirmed; no original stat parent success is credited. Byte differences between downloaded and vendored source are separately reported from newline-normalized text equality.\n\nTo reproduce without altering existing artifacts: `python3 scripts/research15_history_cli.py --run NEW_NAME prepare`; then the same command with `run` and `report`. Preparation reuses verified immutable source downloads, copies no old execution results, and freezes new inputs before execution. Original raw download URLs and commits are in protocol.json and archived official PR metadata.\n\n`representative_witnesses.json` contains an actual original-RTL transaction for each of the two repair obligations. `audit.json` keeps the parent/obligation/sample denominators distinct.\n';p.write_text(text)
    print(json.dumps(dict(history_admitted=summary['admitted_original_module'],stat_status=report['status'],stat_newline_normalized_source_equal=report['official_equals_local_after_universal_newlines'])))


if __name__=='__main__':main()
