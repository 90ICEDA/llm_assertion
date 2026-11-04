"""Post-hoc, read-only audit of frozen augmentation and actual independent runs.

Never imports an executor, constructs test inputs, calls a model, or mutates
sealed artifacts. Refuses to aggregate before all 80 versions and independent
execution have completed. Shared native labels are checked against raw logs.
"""
import argparse
import difflib
import hashlib
import html
import json
from pathlib import Path
import re
import time

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'


def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def signature_diff(before,after):
    """Label-independent alarm identities; caller retains the fault boundary."""
    old={tuple(x) for x in before};new={tuple(x) for x in after}
    ordered=lambda values:[list(x) for x in sorted(values,key=lambda x:json.dumps(x,ensure_ascii=False,separators=(',',':')))]
    return dict(added=ordered(new-old),removed=ordered(old-new),retained=ordered(old&new))
def readiness(campaign):
    freeze=campaign/'frozen_versions.json';outcome=campaign/'independent'/'outcome.json'
    return dict(freeze_exists=freeze.exists(),independent_outcome_exists=outcome.exists(),
      all_80_frozen=freeze.exists() and read(freeze).get('expected')==80 and read(freeze).get('all_trajectories_closed') is True and len(read(freeze).get('entries',[]))==80,
      independent_completed=outcome.exists() and read(outcome).get('status')=='completed')


def marks(log):
    result={'ASSERT_FAIL':set(),'TRIGGER':set()}
    if log.exists():
        for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
            found=re.match(r'^(ASSERT_FAIL|TRIGGER)\s+(\S+)\s+cycle=(-?\d+)',line)
            if found:result[found[1]].add((found[2],int(found[3])))
    return result


def port_values(text):
    line=next((s for s in text.splitlines() if ' dut(' in s or ' dut (' in s),'')
    ports={}
    for match in re.finditer(r'\.(\w+)\(',line):
        depth=1;end=match.end()
        while end<len(line) and depth:
            depth+=(line[end]=='(')-(line[end]==')');end+=1
        if depth==0:ports[match[1]]=line[match.end():end-1]
    return ports


def mutation_sites(measurement):
    """Actual edits relative to paired correct RTL; bench uses port identities."""
    result=set();witnesses=[]
    jobs=measurement.get('executions',[])
    for bad in jobs:
        if bad['variant']=='correct':continue
        good=next((j for j in jobs if j['query_id']==bad['query_id'] and j['variant']=='correct'),None)
        if good is None:continue
        a=Path(good['folder']);b=Path(bad['folder']);sites=set();compatibility=[]
        ga=a.parent/(good['variant']+'_rtl');gb=b.parent/(bad['variant']+'_rtl')
        if ga.exists() and gb.exists():
            for path in ga.iterdir():
                other=gb/path.name
                if not path.is_file() or not other.exists():continue
                lines=path.read_text().splitlines();changed=other.read_text().splitlines()
                for op,i,j,_,_ in difflib.SequenceMatcher(a=lines,b=changed,autojunk=False).get_opcodes():
                    if op!='equal':sites.update('rtl:'+path.name+':'+str(x+1) for x in range(i,max(j,i+1)))
        if (a/'tb.sv').exists() and (b/'tb.sv').exists():
            pa=port_values((a/'tb.sv').read_text());pb=port_values((b/'tb.sv').read_text())
            for p in set(pa)|set(pb):
                if pa.get(p)==pb.get(p):continue
                if measurement.get('historical_fix_confirmed') and bad['variant']=='primary' and (p not in pa or p not in pb):
                    compatibility.append(p)
                else:sites.add('bench:dut_port:'+p)
        result.update(sites);witnesses.append(dict(correct=str(a),mutant=str(b),sites=sorted(sites),
          historical_interface_compatibility_ports=compatibility,
          note='A port absent from the original historical module requires an interface-adapting bench. Its presence change is recorded separately from deliberate connection-expression mutations.'))
    return dict(sites=sorted(result),witnesses=witnesses)


def independent_projection(raw,mapping,index,candidate,logmarks,check,prefix):
    targets=set();timely=set();triggered=set();any_alarm=set();first={};alarm_cycle={};fp=[];fp_signatures=set();evidence_ob={};exposed_queries=set()
    candidate_labels={k:v for k,v in mapping.items() if v['candidate']==index}
    for ev in raw['evidence']:
        relevant=[]
        for observation in ev.get('assertions',[]):
            label=observation['assertion']
            if label not in candidate_labels:continue
            mapped=candidate_labels[label];a=next(a for a in candidate if a['label']==mapped['original_label'])
            native=logmarks[(ev['query_id'],ev['variant'])]
            alarm=(label,ev['cycle']) in native['ASSERT_FAIL']
            trigger=(label,ev['cycle']-(a['timing']=='next_sample')) in native['TRIGGER']
            check(alarm==observation['failure'] and trigger==observation['trigger'],prefix+'/native_marker_binding',dict(label=label,cycle=ev['cycle']))
            relevant.append(dict(failure=alarm,trigger=trigger,obligations=a['obligations']))
        if ev['status']!='confirmed':continue
        eid=ev.get('evidence_id',ev['id'])
        if ev['label']=='violation':
            exposed_queries.add(ev['query_id'])
            if ev.get('counted_target'):
                targets.add(eid);first[eid]=ev['cycle'];evidence_ob[eid]=ev['obligation']
                if any(a['failure'] for a in relevant):timely.add(eid)
                if any(a['trigger'] for a in relevant):triggered.add(eid)
            if any(a['failure'] and ev['obligation'] in a['obligations'] for a in relevant):
                any_alarm.add(eid);alarm_cycle[eid]=min(alarm_cycle.get(eid,ev['cycle']),ev['cycle'])
        elif ev['label']=='legal' and any(a['failure'] for a in relevant):
            fp.append(eid);fp_signatures.add((ev['query_id'],ev['variant'],ev['cycle'],ev['obligation']))
    unknown=[]
    for item in raw.get('critical_unknown',[]):
        label=item.get('assertion')
        if label in mapping and mapping[label]['candidate']!=index:continue
        unknown.append(item)
    unknown_queries={u['query'] for u in unknown if u.get('query')}
    for job in raw['executions']:
        if job['result'].get('compile_status')!='passed' or job['result'].get('execution_status')!='completed' or job['reference']['unknown']:unknown_queries.add(job['query_id'])
    any_alarm &= targets
    return dict(targets=targets,timely=timely,triggered=triggered,any_alarm=any_alarm,fp=fp,fp_signatures=fp_signatures,unknown=unknown,unknown_queries=unknown_queries,
      exposed_queries=exposed_queries,evidence_ob=evidence_ob,delay={e:alarm_cycle[e]-first[e] for e in any_alarm})


def audit(campaign,out,registration,guided,ibex_dev,ibex_primary):
    ready=readiness(campaign)
    if not ready['all_80_frozen'] or not ready['independent_completed']:raise RuntimeError('not_ready_no_test_access:'+json.dumps(ready))
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False);bindings={};failures=[];counts={}
    def load(path):
        path=Path(path);bindings[str(path.resolve())]=sha(path);return read(path)
    def check(ok,kind,detail=None):
        counts[kind]=counts.get(kind,0)+1
        if not ok:failures.append(dict(check=kind,detail=detail))
    freeze_path=campaign/'frozen_versions.json';freeze=load(freeze_path);reg=load(registration);ind=campaign/'independent';plan=load(ind/'plan.json');seal=load(ind/'plan_seal.json');records=load(ind/'results.json')
    check(sha(registration)==freeze['registration_sha256'],'registration_binding')
    check(sha(freeze_path)==seal['manifest_sha256'] and sha(ind/'plan.json')==seal['plan_sha256'],'plan_seal')
    check(freeze_path.stat().st_mtime_ns<=(ind/'plan.json').stat().st_mtime_ns,'artifact_freeze_precedes_test_plan')
    registered={e['id']:e for e in reg['entries']};entries={e['id']:e for e in freeze['entries']}
    check(set(registered)==set(entries) and len(entries)==80,'complete_registered_population')
    check(len({e['folder'] for e in entries.values()})==80,'unique_trajectory_folders')
    outcomes={};candidates={}
    for entry in freeze['entries']:
        terminal=load(ROOT/entry['outcome_path']);candidate=load(ROOT/entry['path']);identity=entry['id']
        outcomes[identity]=terminal;candidates[identity]=candidate
        check(sha(ROOT/entry['outcome_path'])==entry['outcome_sha256'] and sha(ROOT/entry['path'])==entry['sha256'],'frozen_artifact_binding',identity)
        check(digest(candidate)==entry['candidate_sha256']==terminal['frozen_sha256'],'candidate_binding',identity)
        check(all(entry.get(k)==v and (k=='id' or terminal.get(k)==v) for k,v in registered[identity].items()),'trajectory_identity',identity)
    for path,value in freeze['source_bindings'].items():check(sha(path)==value,'registered_source_integrity',path)
    for control in freeze['controls']:candidates[control['id']]=control['candidate']
    metrics_by_id={};native_mark_checks=0;test_sites={};projection_count=0
    for case_id,definition in plan.items():
        split=definition['split_audit'];check(not set(split['development_sites'])&set(split['test_sites']),'declared_reserved_site_disjoint',case_id)
        binding=load(ind/case_id/'version_mapping.json');keys=binding['keys'];mapping=binding['mapping'];combined=binding['combined']
        case_candidates={digest(c):c for name,c in candidates.items() if (entries.get(name) or next((x for x in freeze['controls'] if x['id']==name),{})).get('case_id')==case_id}
        check(set(keys)==set(case_candidates),'shared_version_population',case_id)
        for a in combined:
            mapped=mapping[a['label']];original=next(x for x in case_candidates[keys[mapped['candidate']]] if x['label']==mapped['original_label'])
            check({**a,'label':original['label']}==original,'shared_label_property_identity',dict(case=case_id,label=a['label']))
        qids={q['id'] for q in definition['queries']}
        for fault in definition['faults']:
            raw=load(ind/case_id/fault/'measurement.json');qualification=load(ind/case_id/fault/'fault_qualification.json')
            protocol=load(ind/case_id/fault/'protocol.json');necessary=set(protocol['case']['obligations'])
            check(protocol['candidate']==combined,'physical_candidate_bundle_binding',dict(case=case_id,fault=fault))
            rawmarks={}
            for job in raw['executions']:
                log=Path(job['folder'])/'execute.log';rawmarks[(job['query_id'],job['variant'])]=marks(log)
                check(log.exists() or job['result']['execution_status']!='completed','completed_job_has_raw_log',str(log))
                if log.exists():bindings[str(log.resolve())]=sha(log)
                bench=Path(job['folder'])/'tb.sv'
                if bench.exists():
                    bindings[str(bench.resolve())]=sha(bench);text=bench.read_text()
                    for a in combined:
                        expected=f"{a['label']}: assert property (@(posedge clk) disable iff({protocol['case']['disable']}) ({a['antecedent']}) {'|=>' if a['timing']=='next_sample' else '|->'} ({a['consequent']}))"
                        check(expected in text,'physical_sva_text_binding',dict(bench=str(bench),label=a['label']))
            valid=bool(raw['targets']) and raw['native_complete'] and not [u for u in raw['critical_unknown'] if not u.get('assertion')]
            check(valid==qualification['valid_reachable_fault'],'independent_fault_qualification',dict(case=case_id,fault=fault))
            if fault!='primary':test_sites[(case_id,fault)]=mutation_sites(raw)
            for i,key in enumerate(keys):
                candidate=case_candidates[key];p=independent_projection(raw,mapping,i,candidate,rawmarks,check,case_id+'/'+fault)
                saved=load(ind/case_id/fault/f'projection{i}.json');projection_count+=1
                for field,expected in [('targets',p['targets']),('detected_ids',p['timely']),('triggered_ids',p['triggered']),('transaction_detected_ids',p['any_alarm'])]:check(set(saved[field])==expected,'projection_'+field,dict(case=case_id,fault=fault,index=i))
                check(len(saved['false_positives'])==len(p['fp']) and len(saved['critical_unknown'])==len(p['unknown']),'projection_fp_unknown',dict(case=case_id,fault=fault,index=i))
                for row in [r for r in records if r['case_id']==case_id and r['fault']==fault and r['candidate_sha256']==key]:
                    identity=row['id'];no_exposure=qids-p['exposed_queries']-p['unknown_queries']
                    check(set(row['no_exposure_queries'])==no_exposure and set(row['unknown_queries'])==p['unknown_queries'],'no_exposure_unknown_separation',identity+'/'+fault)
                    timely_pass=bool(p['targets']) and p['targets']<=p['timely'] and not p['fp'] and not p['unknown'] and qids==p['exposed_queries']
                    any_pass=bool(p['targets']) and p['targets']<=p['any_alarm'] and not p['fp'] and not p['unknown'] and qids==p['exposed_queries']
                    check(row['full_planned_scope_pass']==timely_pass and row['full_planned_transaction_scope_pass']==any_pass,'full_scope_no_false_pass',identity+'/'+fault)
                    check(set(row['transaction_detected_ids'])==p['any_alarm'] and set(row['transaction_missed_ids'])==p['targets']-p['any_alarm'],'record_any_cycle_binding',identity+'/'+fault)
                    exposed_ob=set(p['evidence_ob'].values());miss_ob={p['evidence_ob'][e] for e in p['targets']-p['any_alarm']};protected=exposed_ob-miss_ob
                    check(set(row['necessary_obligations'])==necessary and set(row['fully_transaction_protected_exposed_obligations'])==protected and abs(row['necessary_obligation_transaction_protection_rate']-len(protected)/len(necessary))<1e-12,
                      'complete_necessary_obligation_denominator',identity+'/'+fault)
                    alarms=signature_diff([],[(fault,*s) for s in p['fp_signatures']])['added']
                    metrics_by_id[(identity,fault)]=dict(row,independently_recomputed=True,legal_alarm_signatures=alarms,
                      legal_alarm_signature_fields=['fault','query_id','variant','cycle','obligation'])
    # Verify actual mutation locations using saved correct/mutant source pairs.
    dev_sites={};feedback=load(guided)
    for case_id,items in feedback['cases'].items():
        for item in items:dev_sites[(case_id,item['fault_id'])]=mutation_sites(load(item['measurement']))
    for item in load(ibex_dev):
        m=load(item['measurement']) if isinstance(item['measurement'],str) else item['measurement'];dev_sites[('ibex_flush',item['fault'])]=mutation_sites(m)
    dev_sites[('ibex_flush','primary')]=mutation_sites(load(ibex_primary))
    site_rows=[]
    for (case_id,fault),test in test_sites.items():
        development=set().union(*(set(s['sites']) for (cid,_),s in dev_sites.items() if cid==case_id))
        overlap=sorted(set(test['sites'])&development)
        site_rows.append(dict(case_id=case_id,fault=fault,test=test,development_sites=sorted(development),actual_site_overlap=overlap,
          scope='RTL file/line relative to paired correct source; harness faults identified by DUT port. This does not claim disjoint broad mutation-operator families.'))
        check(bool(test['sites']) and not overlap,'actual_reserved_location_disjoint',dict(case=case_id,fault=fault,overlap=overlap))
    paired=[]
    for case_id in plan:
        for seed in (19407,19419):
            ids={c:f'augmentation/{case_id}/{seed}/{c}' for c in ('without','with')}
            for fault in plan[case_id]['faults']:
                a=metrics_by_id[(ids['without'],fault)];b=metrics_by_id[(ids['with'],fault)]
                check(a['target_ids']==b['target_ids'],'paired_identical_independent_targets',dict(case=case_id,seed=seed,fault=fault))
                old=set(a['transaction_detected_ids']);new=set(b['transaction_detected_ids']);oldtime=set(a['detected_ids']);newtime=set(b['detected_ids'])
                fp_diff=signature_diff(a['legal_alarm_signatures'],b['legal_alarm_signatures'])
                eligible=all(outcomes[identity].get('causal_comparison_eligible') is True for identity in ids.values())
                clean=eligible and all(r['native_complete'] and r['reference_complete'] and r['valid_reachable_fault'] for r in (a,b))
                paired.append(dict(case_id=case_id,parent_bug=a['parent_bug'],historical_fix_confirmed=a['historical_fix_confirmed'],seed=seed,fault=fault,
                  scope='development_primary_new_inputs' if fault=='primary' else 'reserved_unseen_fault',causal_pair_eligible=eligible,clean_reference_pair=clean,
                  without=a,with_augmentation=b,gained_ids=sorted(new-old),lost_ids=sorted(old-new),gained=len(new-old),lost=len(old-new),
                  timely_gained=len(newtime-oldtime),timely_lost=len(oldtime-newtime),fp_delta=b['false_positive_records']-a['false_positive_records'],
                  added_fp_signatures=fp_diff['added'],removed_fp_signatures=fp_diff['removed'],retained_fp_signatures=fp_diff['retained'],
                  added_fp=len(fp_diff['added']),removed_fp=len(fp_diff['removed']),
                  equal_fp_count_object_replacement=a['false_positive_records']==b['false_positive_records'] and bool(fp_diff['added']) and bool(fp_diff['removed']),
                  without_runtime_model_calls=outcomes[ids['without']].get('actual_model_calls',0),with_runtime_model_calls=outcomes[ids['with']].get('actual_model_calls',0),
                  note='Gains and losses are set differences; equal total detections do not exclude regression. Primary is not new-fault generalization.'))
    parents=[]
    for case_id in plan:
        for seed in (19407,19419):
            rr=[p for p in paired if p['case_id']==case_id and p['seed']==seed and p['scope']=='reserved_unseen_fault']
            gain=sum(p['gained'] for p in rr);loss=sum(p['lost'] for p in rr);clean=all(p['clean_reference_pair'] for p in rr)
            obligation_metrics={}
            for condition,field in [('without','without'),('with','with_augmentation')]:
                needed=set().union(*(set(p[field]['necessary_obligations']) for p in rr))
                exposed=set().union(*(set(p[field]['exposed_obligations']) for p in rr))
                missed=set().union(*(set(p[field]['exposed_obligations'])-set(p[field]['fully_transaction_protected_exposed_obligations']) for p in rr))
                obligation_metrics[condition]=dict(necessary=sorted(needed),exposed=sorted(exposed),protected_any_cycle=sorted(exposed-missed),
                  necessary_protection_rate=len(exposed-missed)/len(needed),scope='Union of reserved-fault targets; an obligation is protected only if none of its observed transactions is missed across those faults. Unknown prevents a clean pair conclusion.')
            parents.append(dict(case_id=case_id,parent_bug=rr[0]['parent_bug'],historical_fix_confirmed=rr[0]['historical_fix_confirmed'],seed=seed,
              reserved_faults=len(rr),valid_faults=sum(p['without']['valid_reachable_fault'] for p in rr),clean_reference_pair=clean,
              any_cycle_gained=gain,any_cycle_lost=loss,without_detected=sum(p['without']['transaction_detected'] for p in rr),with_detected=sum(p['with_augmentation']['transaction_detected'] for p in rr),
              without_missed=sum(p['without']['transaction_misses'] for p in rr),with_missed=sum(p['with_augmentation']['transaction_misses'] for p in rr),
              without_fp_records=sum(p['without']['false_positive_records'] for p in rr),with_fp_records=sum(p['with_augmentation']['false_positive_records'] for p in rr),
              added_fp_signatures=[s for p in rr for s in p['added_fp_signatures']],removed_fp_signatures=[s for p in rr for s in p['removed_fp_signatures']],
              added_fp=sum(p['added_fp'] for p in rr),removed_fp=sum(p['removed_fp'] for p in rr),
              without_no_exposure_queries=sum(len(p['without']['no_exposure_queries']) for p in rr),with_no_exposure_queries=sum(len(p['with_augmentation']['no_exposure_queries']) for p in rr),
              without_unknown_queries=sum(len(p['without']['unknown_queries']) for p in rr),with_unknown_queries=sum(len(p['with_augmentation']['unknown_queries']) for p in rr),
              necessary_obligation_metrics=obligation_metrics,
              any_cycle_benefit_without_detection_regression=clean and gain>0 and loss==0 and all(not p['added_fp_signatures'] for p in rr),
              strict_unseen_benefit=clean and gain>0 and loss==0 and all(not p['added_fp_signatures'] and p['timely_lost']==0 for p in rr),
              timing_regression=any(p['timely_lost']>0 for p in rr),
              any_regression=loss>0 or any(p['added_fp_signatures'] for p in rr),
              without_full_reserved_pass=all(p['without']['full_planned_transaction_scope_pass'] for p in rr),with_full_reserved_pass=all(p['with_augmentation']['full_planned_transaction_scope_pass'] for p in rr)))
    parent_rollup=[]
    for parent in sorted({p['parent_bug'] for p in parents}):
        rr=[p for p in parents if p['parent_bug']==parent]
        parent_rollup.append(dict(parent_bug=parent,historical_fix_confirmed=rr[0]['historical_fix_confirmed'],paired_seeds=len(rr),
          clean_seeds=sum(p['clean_reference_pair'] for p in rr),benefit_seeds=sum(p['strict_unseen_benefit'] for p in rr),regression_seeds=sum(p['any_regression'] for p in rr),
          benefit_consistent_across_seeds=all(p['strict_unseen_benefit'] for p in rr),regression_in_any_seed=any(p['any_regression'] for p in rr)))
    for path,value in bindings.items():check(sha(path)==value,'audit_input_unchanged',path)
    summary=dict(status='passed' if not failures else 'audit_findings',projection_count=projection_count,checks=sum(counts.values()),failures=len(failures),
      parent_rollup=parent_rollup,paired_parent_seeds=len(parents),clean_parent_seeds=sum(p['clean_reference_pair'] for p in parents),
      strict_unseen_benefit_parent_seeds=sum(p['strict_unseen_benefit'] for p in parents),regression_parent_seeds=sum(p['any_regression'] for p in parents),
      new_native_queries=0,new_model_calls=0,wall_seconds=time.monotonic()-started,
      audit_script_sha256=sha(__file__),false_positive_comparison='Set differences of (fault, query_id, variant, cycle, obligation), ignoring assertion labels. Equal FP counts may hide replaced legal objects. No-new-FP benefit requires the added set to be empty.',
      interpretation='Only reserved-fault clean paired results support augmentation benefit. Unknown trajectories remain in denominators. Seeds are paired repetitions, not independent parent Bugs. Timely and any-cycle detection are separate; no-exposure is never a pass.')
    dump(out/'summary.json',summary);dump(out/'failures.json',failures);dump(out/'check_counts.json',counts);dump(out/'source_bindings.json',bindings)
    dump(out/'augmentation_pairs.json',paired);dump(out/'parent_seed_table.json',parents);dump(out/'reserved_site_audit.json',site_rows)
    dump(out/'cross_fault_acceptance.json',list(metrics_by_id.values()))
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in (p['case_id'],p['seed'],p['clean_reference_pair'],p['without_detected'],p['with_detected'],p['any_cycle_gained'],p['any_cycle_lost'],p['without_fp_records'],p['with_fp_records'],p['without_no_exposure_queries'],p['with_no_exposure_queries'],p['without_unknown_queries'],p['with_unknown_queries'],p['strict_unseen_benefit']))+'</tr>' for p in parents)
    fp_table='<h2>合法报警对象的新增与移除</h2><p>集合键保留 fault、query_id、variant、cycle、obligation，忽略断言标签。数量相同不能证明没有退化；无新增误报收益要求 added 为空。</p><table><tr><th>设计</th><th>种子</th><th>新增合法报警对象</th><th>移除合法报警对象</th></tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (r['case_id'],r['seed'],r['added_fp'],r['removed_fp']))+'</tr>' for r in parents)+'</table>'
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>故障增强独立验收审计</title><style>body{font:15px system-ui;margin:35px;max-width:1500px}table{border-collapse:collapse}td,th{padding:7px;border:1px solid #bbb}</style><h1>故障增强独立验收审计</h1><p>仅使用全部80条轨迹冻结后实际执行的独立验收结果；不新增查询、模型调用或故障实例。下表仅含预留位置的新故障，primary新输入另见配对明细。</p><p>审计状态：'+html.escape(summary['status'])+'；共享投影 '+str(projection_count)+'；检查 '+str(summary['checks'])+'；问题 '+str(len(failures))+'。</p><table><tr><th>设计</th><th>种子</th><th>配对可判定</th><th>未增强检出</th><th>增强检出</th><th>新增检出</th><th>丢失检出</th><th>未增强FP</th><th>增强FP</th><th>未增强无暴露</th><th>增强无暴露</th><th>未增强未知</th><th>增强未知</th><th>无退化独立收益</th></tr>'+table+'</table><p>检出目标为事务×义务。父 Bug 汇总与种子重复分开；检出总数相同也可能发生检出对象替换。无暴露与未知均不算通过。可判定配对还要求两条开发轨迹均具备因果比较条件。</p><p><a href="summary.json">父Bug汇总</a> · <a href="augmentation_pairs.json">配对检出集合</a> · <a href="cross_fault_acceptance.json">跨故障验收</a> · <a href="reserved_site_audit.json">实际变异位置审计</a> · <a href="failures.json">审计问题</a></p>',encoding='utf-8')
    with (out/'report.html').open('a',encoding='utf-8') as report:report.write(fp_table)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign',type=Path,default=D/'research194_campaign_execute_20261103_r01');p.add_argument('--out',type=Path)
    p.add_argument('--check-ready',action='store_true');p.add_argument('--registration',type=Path,default=D/'reguard_mechanisms_20261103_r02/acceptance_registration.json')
    p.add_argument('--guided',type=Path,default=D/'research194_fault_regrade_20261103_r01/obligation_guided_feedback.json')
    p.add_argument('--ibex-dev',type=Path,default=D/'research194_ibex_devfaults_20261103_r01/results.json')
    p.add_argument('--ibex-primary',type=Path,default=D/'research194_ibex_full_qualification_20261103_r01/initial/measurement.json')
    a=p.parse_args()
    if a.check_ready:print(json.dumps(readiness(a.campaign.resolve())))
    elif a.out:audit(a.campaign.resolve(),a.out.resolve(),a.registration,a.guided,a.ibex_dev,a.ibex_primary)
    else:p.error('--out required unless --check-ready')
