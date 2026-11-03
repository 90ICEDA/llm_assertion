"""Common replay index over actual saved runs; no new observations are invented.

Records are provenance entries, not independent discoveries. Preserve each
experiment's semantic gap deduplication and do not add counters across engines.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research_integration_20261014_r01'


def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def rel(p):return p.relative_to(ROOT).as_posix()


def main():
    records=[]
    def add(folder, experiment, parent, split, engine, verdict, references, **extra):
        existing={k:rel(folder/v) for k,v in references.items() if (folder/v).is_file()}
        records.append(dict(schema='replay-index-v1',evidence_id=hashlib.sha256(rel(folder).encode()).hexdigest(),
            experiment=experiment,parent=parent,split=split,engine=engine,execution_status=verdict,
            raw_directory=rel(folder),references=existing,
            discovery_count=None,independence='See frozen split and semantic gap protocol; unique path is not independent evidence.',**extra))
    fifo=ROOT/'deliverables/research_fifo_20261014_r01'
    for r in read(fifo/'results.json'):
        folder=fifo/r['artifact_directory']
        add(folder,'complex_fifo','axis_fifo_artificial_boundary',r['split'],'Icarus RTL simulation',r['execution_status'],
            dict(input='intent_schedule.json',trace='trace.json',transactions_and_obligations='evidence.json',rtl='axis_fifo.v',testbench='tb.sv',waveform='wave.vcd',compile='compile.json',execute='execute.json'),
            stimulus_legality=r['legality'],obligation_verdict=r['obligation_verdict'],candidate_provenance='engineering controls only',mutation=r['mutation'])
    for name in ('research_search_20261014_r01','research_gate_20261014_r01'):
        base=ROOT/'deliverables'/name
        for p in sorted(base.glob('runs/**/result.json')):
            # Engine run folders contain definition and trace. Other summary
            # result files are excluded rather than counted as executions.
            if not (p.parent/'definition.json').exists():continue
            r=read(p);d=read(p.parent/'definition.json');sub=rel(p.parent)
            split='independent_test_conditional' if '/independent/' in sub else 'development'
            add(p.parent,name,d['key'],split,'Icarus procedural assertion checker',r['status'],
                dict(input='input.json',trace='trace.json',obligations='independent_reference.json',adjudication='adjudication.json',candidates='candidates.json',definition='definition.json',testbench='tb.sv',waveform='wave.vcd',result='result.json'),
                native_sva=False,formal_proof=False,trigger_status='See per-candidate result/trace; never infer from execution status.')
    native=ROOT/'deliverables/research_native_20261014_r01'
    for block,split in [('closed_loop/v0_development','development'),('compact_continuation/development','development'),('compact_continuation/independent_test','independent_diagnostic_rejected_proposal')]:
        for p in sorted((native/block).glob('*/result.json')):
            r=read(p)
            add(p.parent,'native_fifo','axis_fifo_artificial_boundary',split,'Verilator native SVA',r['execution_status'],
                dict(trace='trace.json',obligations='oracle.json',result='result.json',testbench='tb.sv',waveform='wave.vcd',compile='compile.json',execute='execute.json'),
                property_status=r['property_status'],compile_status=r['compile_status'],tool_support_status=r['tool_support_status'],
                trigger_status='unconfirmed: model diagnostic trigger mismatches property antecedent',formal_proof=False)
    ibex=ROOT/'deliverables/research_ibex_20261014_r01'
    for r in read(ibex/'summary.json')['results']:
        add(ibex/r['revision']/r['cohort'],'ibex_replay','ibex_54','historical_development','Icarus original RTL testbench',
            'expected_behavior_reproduced' if r['expected_behavior_reproduced'] else 'unknown',
            dict(rtl='ibex_compressed_decoder.sv',testbench='tb.sv',compile='compile.json',execute='execute.json',execution_log='execute.stdout'),
            native_sva=False,revision=r['revision'],cohort=r['cohort'])
    OUT.mkdir(exist_ok=True)
    with (OUT/'evidence_index.jsonl').open('w',encoding='utf-8') as f:
        for r in records:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    summary=dict(records=len(records),all_references_exist=all((ROOT/p).is_file() for r in records for p in r['references'].values()),
        schema='reference-only index; no cross-experiment discovery summation',
        by_experiment={e:sum(r['experiment']==e for r in records) for e in sorted({r['experiment'] for r in records})})
    (OUT/'evidence_index_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
