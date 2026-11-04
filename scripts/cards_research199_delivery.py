"""Development-only example selection, followed by independent result attachment."""
import argparse
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research198_cards import attach as attach_previous
from research198_paths import chains,structural_chains
import research198_cards


def select(prepared,execution,out):
    if read(execution/'outcome.json')['status']!='completed_all_versions_frozen':
        raise ValueError('all_versions_must_freeze')
    out.mkdir(parents=True,exist_ok=False)
    selected={}; paths=[]
    for e in sorted(read(prepared/'protocol.json')['entries'],key=lambda x:x['id']):
        folder=execution/e['id']/'refinement'
        rounds=read(folder/'rounds.json') if (folder/'rounds.json').exists() else []
        history=read(folder/'controller_history.json') if (folder/'controller_history.json').exists() else []
        strict=chains(history); structural=structural_chains(history)
        paths.append(dict(id=e['id'],strict=strict,structural=structural))
        for r in rounds:
            if r.get('stage')=='local' and r.get('status') in ('accepted','rejected'):
                selected.setdefault(e['case_id']+'/local_'+r['status'],dict(entry=e,round=r['round']))
            if e['cohort']=='online' and r.get('status')=='accepted':
                selected.setdefault('online/'+e['case_id'],dict(entry=e,round=r['round']))
            if r.get('stage') in ('compose','regenerate') and 'decision' in r:
                selected.setdefault(r['stage']+'_native',dict(entry=e,round=r['round']))
        if strict: selected.setdefault('strict_rejected_local_chain',dict(entry=e,round=strict[0]['rounds'][-1]))
        if structural: selected.setdefault('partial_local_structural_chain',dict(entry=e,round=structural[0]['rounds'][-1]))
    data=dict(selection_reads_independent_results=False,execution=str(execution.resolve()),cards=selected,paths=paths,
        source_bindings={str(Path(__file__).resolve()):file_hash(__file__),str(Path(research198_cards.__file__).resolve()):file_hash(research198_cards.__file__)},
        missing_categories=[x for x in ('strict_rejected_local_chain','partial_local_structural_chain','compose_native','regenerate_native') if x not in selected])
    dump(out/'selection.json',data);dump(out/'seal.json',dict(sha256=file_hash(out/'selection.json')))
    print(dict(selected=len(selected),missing=data['missing_categories']),flush=True)


def attach(out,acceptance):
    for path,h in read(out/'selection.json')['source_bindings'].items():
        if file_hash(path)!=h: raise ValueError('card renderer changed')
    attach_previous(out,acceptance)
    path=out/'cards.html'
    text=path.read_text(encoding='utf-8').replace('R198 cases','R199 cases').replace('R198 自动局部与回退案例','R199 因果隔离、在线修改与回退案例')
    path.write_text(text,encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['select','attach'])
    for key in ('prepared','execution','out','acceptance'):parser.add_argument('--'+key,type=Path)
    a=parser.parse_args()
    select(a.prepared,a.execution,a.out) if a.action=='select' else attach(a.out,a.acceptance)
