"""Evidence/proposal/projection linkage; association is not item-level causality."""
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash
from research194_refinement import digest
from research199_cost import profile

def run(prepared,execution,cost,out):
    p=read(Path(prepared)/'protocol.json');index=read(Path(cost)/'projection_index.json');rows=[]
    acceptance=Path(read(Path(cost)/'evaluation_outcome.json')['acceptance']);plans=read(acceptance/'plan.json')
    for e in p['entries']:
        folder=Path(execution)/e['id']/'refinement'
        if not (folder/'rounds.json').exists():continue
        acquisitions=read(folder/'acquisitions.json')
        for r in read(folder/'rounds.json'):
            if r.get('status')!='accepted':continue
            rd=folder/f"round{r['round']:02}";before=read(rd/'current_measurement.json');proposal=read(rd/'proposal.json')
            acquired=acquisitions[r['round']-1];newgap=set(acquired.get('new_gap_ids',[]))
            source_ids=sorted({g['evidence_id'] for g in acquired.get('gap_records',[]) if g['gap_id'] in newgap})
            effects=[];all_before=set();all_after=set();failed_before=set();failed_after=set();complete=True;fpadded=set()
            for fault in plans[e['case_id']]['faults']:
                pair=[]
                for h in (before['candidate_sha256'],digest(proposal)):
                    src=index[e['case_id']+'/'+h+'/'+fault]
                    if file_hash(src['path'])!=src['sha256']:raise ValueError('projection_changed')
                    pair.append(read(src['path']))
                a,b=pair;known=all(m['native_complete'] and m['reference_complete'] and not m['critical_unknown'] for m in pair)
                xa,pa=profile(a);xb,pb=profile(b)
                shared=bool(a['targets']) and set(a['targets'])==set(b['targets']);eligible=known and shared
                effects.append(dict(fault=fault,eligible=eligible,newly_protected_obligations=sorted(pb-pa) if eligible else [],
                    before_detected=len(a['transaction_detected_ids']),after_detected=len(b['transaction_detected_ids']),
                    before_target_count=len(a['targets']),after_target_count=len(b['targets'])))
                complete &= eligible;all_before|=xa;all_after|=xb;failed_before|=xa-pa;failed_after|=xb-pb
                fpadded|={(fault,v['id']) for v in b['false_positives']} - {(fault,v['id']) for v in a['false_positives']}
            new=sorted((all_after-failed_after)-(all_before-failed_before)) if complete else []
            rows.append(dict(id=e['id'],arm=e['arm'],round=r['round'],stage=r['stage'],source_query_ids=[q['id'] for q in acquired.get('queries',[])],
                source_new_gap_ids=sorted(newgap),source_new_evidence_ids=source_ids,
                evidence_linkage=str(rd/'evidence_linkage.json'),localization=str(rd/'localization.json'),model_edit=str(rd/'model_edit.json'),
                before_sha256=before['candidate_sha256'],after_sha256=digest(proposal),effects=effects,
                all_registered_faults_comparable=complete,globally_newly_protected_obligations=new,added_legal_alarm_ids=sorted(fpadded),
                clean_associated_online_chain=e['cohort']=='online' and bool(source_ids) and complete and bool(new) and not fpadded,
                interpretation='New confirmed evidence preceded an accepted edit with measured independent effects. No counterfactual evidence removal was run; this is not proof of an individual item causing the edit.'))
    dump(out,dict(rows=rows,clean_associated_online_chains=sum(r['clean_associated_online_chain'] for r in rows),model_calls=0,native_calls=0))
