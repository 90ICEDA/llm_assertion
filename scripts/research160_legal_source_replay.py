"""Correct only source handshaking; preserve research159 failed first replay."""
import argparse
from pathlib import Path
import shutil
from unittest.mock import patch
import research159_history_screen as old

ROOT=old.ROOT
PRIOR=ROOT/'deliverables/research159_history_prepare_20261028_r01'


def bench(kind,param,rows):
    text=old.axis_tb(kind,param,rows)
    text=text.replace('integer cycle=-1;','integer cycle=-1;integer source_index=0;bit source_accept=0;')
    for row in rows:
        oldline=f"@(negedge clk);cycle={row['cycle']};rst={row['rst']};s_axis_tvalid={row['sv']};s_axis_tdata={row['sd']};s_axis_tkeep={row['sk']};s_axis_tlast={row['sl']};m_axis_tready={row['mr']};pause_req={row['pause']};"
        keep="1'b0" if row['family']=='ignored_keep_zero' else "(source_index%2)==0" if row['family']=='ignored_keep_alternating' else "1'b1"
        enable=int(row['phase']>=3 and not(row['family']=='reset_cancel' and row['phase']>=9))
        newline=f"@(negedge clk);cycle={row['cycle']};rst={row['rst']};if(rst) source_index=0;s_axis_tvalid=!rst && {enable} && source_index<4;s_axis_tdata={row['trial']*32+1}+source_index;s_axis_tkeep={keep};s_axis_tlast=(source_index%2)==1;m_axis_tready={row['mr']};pause_req={row['pause']};"
        assert oldline in text;text=text.replace(oldline,newline)
    text=text.replace('@(posedge clk);$display("TRACE','@(posedge clk);source_accept=s_axis_tvalid && s_axis_tready && !rst;$display("TRACE')
    text=text.replace('pause_req,pause_ack);','pause_req,pause_ack);#1;if(source_accept) source_index=source_index+1;')
    return text


def prepare(out):
    old.verify(PRIOR);out.mkdir(parents=True,exist_ok=False)
    for case in ('axis_adapter_keep','axis_fifo_pause'):
        shutil.copytree(PRIOR/case,out/case)
        rows=old.read(out/case/'stimuli.json')
        for p in ([8,32] if case=='axis_adapter_keep' else [0,1]):
            (out/case/f'tb_{p}.sv').write_text(bench('adapter' if case=='axis_adapter_keep' else 'fifo',p,rows))
    for name in ('population_lock.json','source_manifest.json','scope.json'):shutil.copy2(PRIOR/name,out/name)
    old.dump(out/'source_driver_correction.json',dict(reason='Fixed-cycle source in research159 can withdraw/change unaccepted input under backpressure. Those observations are not admitted as legal witnesses.',
        driver='Advance source_index only on actual positive-edge valid&&ready; drive stable input on negative edges. Reset cancels pending source and DUT transactions.',
        common_stimulus='Compare every actual source valid/data/keep/last and external ready/pause/reset trace between revisions; unequal timing cannot qualify as same-stimulus witness.',
        changed_rtl=False,changed_obligations=False,changed_native_sva=False,
        preserved_first_run='deliverables/research159_history_native_20261028_r01',
        native_compiles=8,total_round_compile_cap=18,model_calls=0))
    old.dump(out/'code_bindings.json',{old.rel(p):old.sha(p) for p in (Path(__file__),Path(old.__file__),Path(old.native.__file__))})
    old.dump(out/'seal.json',{p.relative_to(out).as_posix():old.sha(p) for p in out.rglob('*') if p.is_file()})
    old.verify(out);print('PREPARED160 legal source only; 8 remaining executions',flush=True)


def run(prep,out):
    old.verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    for case,params in [('axis_adapter_keep',[8,32]),('axis_fifo_pause',[0,1])]:
        for p in params:
            for rev in ('before','after'):
                folder=out/case/f'p{p}'/rev;source=prep/case/rev/('axis_adapter.v' if case=='axis_adapter_keep' else 'axis_fifo.v')
                result=old.native.run_native((prep/case/f'tb_{p}.sv').read_text(),folder,extra_sources=[source])
                entry=dict(case=case,parameter=p,revision=rev,native=result,status='unknown')
                if result['execution_status']=='completed':
                    values=old.trace(folder);rows=old.read(prep/case/'stimuli.json');assert len(values)==len(rows)
                    # Controls frozen; actual handshaken source replaces only the invalid fixed-cycle source columns.
                    for v,r in zip(values,rows):
                        assert all(v[k]==r[k] for k in ('cycle','rst','mr','pause'))
                        r.update({k:v[k] for k in ('sv','sd','sk','sl')})
                    oracle=old.oracle_axis(values,rows,p if case=='axis_adapter_keep' else 8)
                    old.dump(folder/'actual_stimuli.json',rows);old.dump(folder/'trace.json',values);old.dump(folder/'oracle.json',oracle)
                    entry.update(status='violated' if oracle['failures'] else 'no_violation_in_scope',failed=len(oracle['failures']),legality_confirmed=oracle['legality_confirmed'])
                results.append(entry);old.dump(out/'progress.json',results)
                print('NATIVE160',case,p,rev,result['compile_status'],result['execution_status'],entry.get('failed'),entry.get('legality_confirmed'),flush=True)
    old.dump(out/'results.json',dict(results=results,model_calls=0,formal_calls=0));old.verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
