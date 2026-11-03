// Join timestamped replays to all 162 count-different collision pairs.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const dir=path.join(root,'deliverables/feedback_collision_reaudit_20261002');
const load=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const rows=fs.readFileSync(path.join(dir,'adjudicated_pairs.jsonl'),'utf8').trim().split('\n').map(JSON.parse).filter(x=>x.count_difference);
const index=load(path.join(dir,'vpi_time_replay_index.json'));
const lookup=new Map(index.map(x=>[x.source_result,x]));
const cache=new Map();
function replay(source){const i=lookup.get(source);if(!i)return null;if(!cache.has(i.replay))cache.set(i.replay,load(path.join(root,i.replay)));return cache.get(i.replay);}
function relation(aa,bb){
  const a=new Set(aa),b=new Set(bb),common=aa.filter(t=>b.has(t)),aonly=aa.filter(t=>!b.has(t)),bonly=bb.filter(t=>!a.has(t));
  const nearShared=t=>common.some(c=>Math.abs(c-t)===10000);
  let kind='same_failure_times';
  if(aonly.length&&bonly.length)kind=common.length?'overlapping_but_each_has_unique_failure_times':'disjoint_failure_times';
  else if(aonly.length)kind='B_times_subset_A';else if(bonly.length)kind='A_times_subset_B';
  return {relation:kind,a_times_ps:aa,b_times_ps:bb,common_times_ps:common,a_only_times_ps:aonly,b_only_times_ps:bonly,
    a_only_adjacent_to_shared_10ns:aonly.filter(nearShared).length,
    b_only_adjacent_to_shared_10ns:bonly.filter(nearShared).length,
    consecutive_A_10ns_pairs:aa.filter((t,i)=>i>0&&t-aa[i-1]===10000).length,
    consecutive_B_10ns_pairs:bb.filter((t,i)=>i>0&&t-bb[i-1]===10000).length};
}
let out=[],errors=[];
for(const p of rows){
  const probes=[];
  for(const item of p.evidence.count_difference_probe_results){
    const a=replay(item.a_result),b=replay(item.b_result);
    if(!a||!b){errors.push({pair_id:p.pair_id,probe_id:item.probe_id,error:'replay missing'});continue;}
    const valid=['correct','buggy'].every(k=>a.runs[k].metrics_match&&b.runs[k].metrics_match);
    if(!valid)errors.push({pair_id:p.pair_id,probe_id:item.probe_id,error:'replay metric mismatch'});
    probes.push({probe_id:item.probe_id,valid,replay_A:a.replay_path,replay_B:b.replay_path,
      fixed:relation(a.runs.correct.failure_times_ps,b.runs.correct.failure_times_ps),
      buggy:relation(a.runs.buggy.failure_times_ps,b.runs.buggy.failure_times_ps),
      fixed_antecedent_A_ps:a.runs.correct.antecedent_times_ps,fixed_antecedent_B_ps:b.runs.correct.antecedent_times_ps,
      buggy_antecedent_A_ps:a.runs.buggy.antecedent_times_ps,buggy_antecedent_B_ps:b.runs.buggy.antecedent_times_ps});
  }
  const tally=design=>Object.fromEntries([...new Set(probes.filter(x=>x.valid).map(x=>x[design].relation))].map(k=>[k,probes.filter(x=>x.valid&&x[design].relation===k).length]));
  const shifted=probes.some(x=>['disjoint_failure_times','overlapping_but_each_has_unique_failure_times'].includes(x.fixed.relation)||
    ['disjoint_failure_times','overlapping_but_each_has_unique_failure_times'].includes(x.buggy.relation));
  const temporalPattern=shifted?'different_failure_clock_positions_observed':'shared_failure_times_plus_extra_samples_only';
  out.push({pair_id:p.pair_id,parent_id:p.parent_id,candidate_A:p.candidate_A,candidate_B:p.candidate_B,
    quality_relation:p.quality_relation,quality_category:p.category,
    attempted_probes:probes.length,compared_probes:probes.filter(x=>x.valid).length,
    rejected_probe_replays:probes.filter(x=>!x.valid).length,all_metrics_reproduced:probes.every(x=>x.valid),
    fixed_time_relations:tally('fixed'),buggy_time_relations:tally('buggy'),temporal_pattern:temporalPattern,
    interpretation:'Failure clock positions come from read-only VPI monitoring of the original compiled probe. Shared and extra sampled times are reported separately. Clock adjacency is not proof of the same transaction or root cause; relative repair quality remains tied to RTL/obligation evidence.',
    same_violation_identity:'UNKNOWN',probes});
}
fs.writeFileSync(path.join(dir,'count_timeline_162.jsonl'),out.map(x=>JSON.stringify(x)).join('\n')+'\n');
fs.writeFileSync(path.join(dir,'count_timeline_failures.json'),JSON.stringify(errors,null,2));
function csv(rows,columns){const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';return [columns.map(q).join(','),...rows.map(x=>columns.map(k=>q(x[k])).join(','))].join('\n')+'\n';}
const compact=out.map(x=>({pair_id:x.pair_id,parent_id:x.parent_id,candidate_A:x.candidate_A,candidate_B:x.candidate_B,
  quality_relation:x.quality_relation,quality_category:x.quality_category,temporal_pattern:x.temporal_pattern,
  compared_probes:x.compared_probes,fixed_time_relations:JSON.stringify(x.fixed_time_relations),
  buggy_time_relations:JSON.stringify(x.buggy_time_relations),same_violation_identity:x.same_violation_identity,
  detail_path:'deliverables/feedback_collision_reaudit_20261002/count_timeline_162.jsonl'}));
fs.writeFileSync(path.join(dir,'count_timeline_162.csv'),csv(compact,Object.keys(compact[0])));
const summary={pairs:out.length,probe_comparisons:out.reduce((n,x)=>n+x.compared_probes,0),
  attempted_probe_comparisons:out.reduce((n,x)=>n+x.attempted_probes,0),
  pairs_with_any_valid_comparison:out.filter(x=>x.compared_probes>0).length,
  all_metrics_reproduced:out.filter(x=>x.all_metrics_reproduced).length,failed_comparisons:errors.length,
  same_violation_identity_unknown:out.filter(x=>x.same_violation_identity==='UNKNOWN').length,
  different_failure_clock_positions_pairs:out.filter(x=>x.temporal_pattern==='different_failure_clock_positions_observed').length,
  shared_times_plus_extra_samples_pairs:out.filter(x=>x.temporal_pattern==='shared_failure_times_plus_extra_samples_only').length};
fs.writeFileSync(path.join(dir,'count_timeline_summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
