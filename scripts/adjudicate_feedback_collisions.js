// Evidence-scoped semantic adjudication of the frozen 294 collision pairs.
// Read-only on source artifacts; writes a separate review so the first pass survives.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const base=path.join(root,'outputs/behavioral_preference_pilot_v1');
const out=path.join(root,'deliverables/feedback_collision_reaudit_20261002');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8').replace(/^\uFEFF/,''));
const obligations=read(path.join(out,'repair_obligations.json'));
const rel=p=>path.relative(root,p).replaceAll('\\','/');
const rows=fs.readFileSync(path.join(out,'pairs.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
const timelinePath=path.join(out,'count_timeline_162.jsonl');
const timelineRows=fs.existsSync(timelinePath)?fs.readFileSync(timelinePath,'utf8').trim().split('\n').map(JSON.parse):[];
const verifiedTimeline=new Set(timelineRows.filter(x=>x.all_metrics_reproduced&&x.compared_probes===x.attempted_probes).map(x=>x.pair_id));
const timelineLine=new Map(timelineRows.map((x,i)=>[x.pair_id,i+1]));
const caseRoots=['rtl_cases_real_scale210_independent_next','rtl_cases_real_scale210_independent','rtl_cases_real_active','rtl_cases_real_scale120','rtl_cases_real_iverilog_ready','rtl_cases_real'];
const caseContext={};const cand={};const incidents=[];
function rtlDelta(fixedPath,buggyPath){
  const aa=fs.readFileSync(fixedPath,'utf8').split(/\r?\n/),bb=fs.readFileSync(buggyPath,'utf8').split(/\r?\n/);
  const n=aa.length,m=bb.length;
  if(n*m>1000000)return {status:'too_large_for_line_diff',fixed_lines:n,buggy_lines:m};
  const dp=Array.from({length:n+1},()=>new Uint16Array(m+1));
  for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=aa[i]===bb[j]?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
  let i=0,j=0,removed=[],added=[];
  while(i<n&&j<m){if(aa[i]===bb[j]){i++;j++;}else if(dp[i+1][j]>=dp[i][j+1])removed.push({line:i+1,text:aa[i++]});else added.push({line:j+1,text:bb[j++]});}
  while(i<n)removed.push({line:i+1,text:aa[i++]});while(j<m)added.push({line:j+1,text:bb[j++]});
  return {status:'derived_from_fixed_and_buggy_RTL',removed_fixed_lines:removed,added_buggy_lines:added};
}
function context(parent){
  if(caseContext[parent])return caseContext[parent];
  const name=caseRoots.find(n=>fs.existsSync(path.join(root,n,parent)));
  const dir=path.join(root,name,parent);
  const sources=['spec.md','STIMULUS_NOTES.md','mutation.diff','case_metadata.json','golden.sva','buggy.v','correct.v'];
  const files=Object.fromEntries(sources.map(n=>[n,fs.existsSync(path.join(dir,n))?rel(path.join(dir,n)):null]));
  let obligation='';
  for(const n of ['spec.md','STIMULUS_NOTES.md'])if(files[n]){obligation=fs.readFileSync(path.join(dir,n),'utf8');break;}
  if(!obligation&&files['case_metadata.json']){
    const m=read(path.join(dir,'case_metadata.json'));
    obligation=JSON.stringify({bug_family:m.bug_family,temporal_type:m.temporal_type,golden_sva:m.golden_sva});
  }
  const delta=files['correct.v']&&files['buggy.v']?rtlDelta(path.join(dir,'correct.v'),path.join(dir,'buggy.v')):{status:'RTL_source_missing'};
  return caseContext[parent]={dir,files,obligation:obligation.slice(0,12000),delta};
}
function semantics(e){
  const x=e.ast||{};
  const trigger=(x.antecedent_polarity==='low'?'not ':'')+(x.antecedent_signal||'?');
  const delay=x.implication==='|=>'?'at the next sampled clock':'at the same sampled clock';
  const relation={high:'asserted/nonzero',low:'deasserted/zero',equal:'equal to trigger signal',not_equal:'unequal to trigger signal'}[x.relation]||x.relation;
  return `When ${trigger} holds, require ${x.consequent_signal} to be ${relation} ${delay}; reset and exact vector semantics follow the quoted SVA.`;
}
function canonical(e){
  const x=e.ast||{};
  let relation=x.relation;
  // At an overlapping consequent, a true !S antecedent fixes S to zero.
  // Equality with zero is exactly a low check; inequality is a high check,
  // including when the consequent is a vector.
  if(x.implication==='|->'&&x.antecedent_polarity==='low'){
    if(relation==='equal')relation='low';
    else if(relation==='not_equal')relation='high';
  }
  return [x.antecedent_signal,x.antecedent_polarity,x.implication,x.consequent_signal,relation].join('|');
}
function twoStateCounterexample(a,b){
  const names=[...new Set([a.ast.antecedent_signal,a.ast.consequent_signal,b.ast.antecedent_signal,b.ast.consequent_signal])];
  if(names.length>6)return null;
  const value=(state,name)=>state[name]||0;
  const verdict=(e,t0,t1)=>{
    const x=e.ast,ant=value(t0,x.antecedent_signal),enabled=x.antecedent_polarity==='low'?!ant:!!ant;
    if(!enabled)return true;
    const state=x.implication==='|=>' ?t1:t0;
    const c=value(state,x.consequent_signal),s=value(state,x.antecedent_signal);
    return {high:!!c,low:!c,equal:c===s,not_equal:c!==s}[x.relation];
  };
  for(let bits=0;bits<(1<<(2*names.length));bits++){
    const t0={},t1={};names.forEach((n,i)=>{t0[n]=(bits>>i)&1;t1[n]=(bits>>(i+names.length))&1;});
    const va=verdict(a,t0,t1),vb=verdict(b,t0,t1);
    if(va!==vb)return {scope:'unconstrained two-state signals at trigger and next sample; RTL legality unproved',
      current_sample:t0,next_sample:t1,A_passes:va,B_passes:vb};
  }
  return null;
}
function obligationMapping(e,o){
  const x=e.ast||{},triggerHit=(o.trigger_signals||[]).includes(x.antecedent_signal),checkHit=(o.check_signals||[]).includes(x.consequent_signal);
  const missingTrigger=(o.trigger_signals||[]).filter(s=>s!==x.antecedent_signal);
  const missingChecks=(o.check_signals||[]).filter(s=>s!==x.consequent_signal);
  let timing;
  const effectiveRelation=canonical(e).split('|').at(-1);
  const expectedLevel=o.required_level_on_named_phase?.[x.consequent_signal];
  const valueAlignment=expectedLevel?(effectiveRelation===expectedLevel?'matches_required_level':
    (effectiveRelation==='high'||effectiveRelation==='low')?'opposes_required_level':'relation_needs_context'):'complex_value_or_history_obligation';
  if(o.timing==='same cycle')timing=x.implication==='|->'?'same-cycle form':'next-cycle form differs from same-cycle obligation';
  else if(o.timing==='next cycle'||o.timing==='next sampled cycle'||o.timing==='following sample'||o.timing==='next state')timing=x.implication==='|=>'?'next-cycle form':'same-cycle form differs from next-state obligation';
  else timing=`one-step ${x.implication} form; obligation requires ${o.timing}`;
  const notes=[];
  let logicalStatus='not_proved';
  if(x.antecedent_signal===x.consequent_signal&&x.implication==='|->'){
    if(x.relation==='equal'||(x.relation==='high'&&x.antecedent_polarity==='high')||(x.relation==='low'&&x.antecedent_polarity==='low'))
      logicalStatus='tautological_on_trigger';
    if(x.relation==='not_equal'||(x.relation==='high'&&x.antecedent_polarity==='low')||(x.relation==='low'&&x.antecedent_polarity==='high'))
      logicalStatus='contradictory_on_trigger';
  }
  if(logicalStatus!=='not_proved')notes.push(`same-cycle self-comparison is ${logicalStatus}`);
  if(!triggerHit)notes.push(`trigger ${x.antecedent_signal} does not name the obligation's primary trigger signal`);
  if(missingTrigger.length)notes.push(`trigger omits required context: ${missingTrigger.join(', ')}`);
  if(!checkHit)notes.push(`checks ${x.consequent_signal} instead of required output/state`);
  if(missingChecks.length)notes.push(`does not check: ${missingChecks.join(', ')}`);
  if(expectedLevel)notes.push(`required ${x.consequent_signal}=${expectedLevel} in named phase; actual effective relation=${effectiveRelation} (${valueAlignment})`);
  notes.push(timing);
  notes.push(`essential obligation detail: ${o.essential_detail}`);
  return {actual_trigger:`${x.antecedent_polarity==='low'?'!':''}${x.antecedent_signal}`,
    actual_check:`${x.consequent_signal} ${x.relation} at ${x.implication==='|=>'?'next':'same'} sample`,
    trigger_signal_matches:triggerHit,checked_signal_matches:checkHit,missing_trigger_signals:missingTrigger,
    missing_check_signals:missingChecks,timing_assessment:timing,notes,
    value_alignment:valueAlignment,
    logical_status:logicalStatus,
    coverage_status:missingTrigger.length||missingChecks.length||!triggerHit||!checkHit?'PARTIAL_OR_MISMATCH':'NEEDS_VALUE_AND_HISTORY_REVIEW'};
}
function candidate(id){
  if(cand[id])return cand[id];
  const parent=id.split('__v3_slot_')[0],slot=id.slice(-2),p=path.join(base,'sequential_generation_v3_pilot30',parent,`slot_${slot}`,'attempt_01','evidence.json');
  const e=read(p),dir=path.join(base,'behavioral_probes_v3',parent),pool=read(path.join(dir,'probe_pool.json')).probes;
  const fp=[],miss=[],count=[];
  for(const q of pool){const rp=path.join(dir,'runs',q.probe_id,id,'result.json');
    try{const d=read(rp);if(d.fp)fp.push({probe_id:q.probe_id,source_label:q.source_label,path:rel(rp),fail_hits:d.rtl.correct.fail_hits});
      if((q.source_label==='target'||q.source_label==='holdout')&&!d.tp)miss.push({probe_id:q.probe_id,source_label:q.source_label,path:rel(rp)});
      count.push({probe_id:q.probe_id,fixed:d.rtl.correct.fail_hits,buggy:d.rtl.buggy.fail_hits,ant_fixed:d.rtl.correct.antecedent_hits,ant_buggy:d.rtl.buggy.antecedent_hits});
    }catch(err){incidents.push({candidate:id,probe:q.probe_id,path:rel(rp),error:String(err)});}
  }
  const primary={fixed_safe:e.fixed_safe,target_detect:e.target_detect,non_vacuous:e.non_vacuous,compile:e.icarus_compile_ok,
    fixed_fail_hits:e.runs?.correct?.fail_hits,buggy_fail_hits:e.runs?.buggy?.fail_hits,
    fixed_ant_hits:e.runs?.correct?.ant_hits,buggy_ant_hits:e.runs?.buggy?.ant_hits};
  const faults=[];
  if(!e.icarus_compile_ok)faults.push('compile failure');
  if(!e.fixed_safe)faults.push('fixed RTL false positive on original testbench');
  if(!e.target_detect)faults.push('target bug missed on original testbench');
  if(!e.non_vacuous)faults.push('antecedent not reached on original testbench');
  if(fp.length)faults.push(`fixed RTL false positive on ${fp.length} of 64 probes`);
  return cand[id]={id,sva:e.sva,ast:e.ast,semantic_meaning:semantics(e),source:rel(p),primary,fp,miss,count,faults};
}
function countReview(row,a,b){
  const probes=row.count_difference_probes||[];
  if(!probes.length)return {status:'same observed fail-hit counts',reason:'No multiplicity difference on the selected probes.',probe_count:0};
  let fixed=0,buggy=0,both=0;
  for(const p of probes){const f=p.a_fixed!==p.b_fixed,g=p.a_buggy!==p.b_buggy;if(f)fixed++;if(g)buggy++;if(f&&g)both++;}
  return {status:'event multiplicity differs; root-cause identity UNKNOWN',probe_count:probes.length,
    fixed_probe_count:fixed,buggy_probe_count:buggy,both_probe_count:both,
    reason:'Each linked checker reports aggregate fail_hits only; it records neither failing cycle nor violated transaction identity. Equal FP/TP IDs plus unequal counts prove multiplicity, but cannot establish whether one violation repeated or distinct failures occurred.'};
}
let outRows=[];
for(const row of rows){
  const a=candidate(row.candidate_A),b=candidate(row.candidate_B),ctx=context(row.parent_id);
  const delta=[];
  for(const [key,label] of [['antecedent_signal','trigger signal'],['antecedent_polarity','trigger polarity'],['implication','cycle alignment'],['consequent_signal','checked signal'],['relation','required value/relation']])
    if(a.ast?.[key]!==b.ast?.[key])delta.push(`${label}: A=${a.ast?.[key]}, B=${b.ast?.[key]}`);
  const sameSva=a.sva===b.sva,booleanEquivalent=canonical(a)===canonical(b);
  const formulaWitness=booleanEquivalent?null:twoStateCounterexample(a,b);
  const knownFixedWitness=row.parent_id==='case510_cc_spill_register_flush_push_priority'&&[a.id.slice(-2),b.id.slice(-2)].sort().join(',')==='06,07';
  const semanticEquivalence=sameSva?'EQUIVALENT_BY_IDENTICAL_TEXT':booleanEquivalent?'EQUIVALENT_BY_BOOLEAN_REWRITE':
    verifiedTimeline.has(row.pair_id)?'NOT_EQUIVALENT_ON_VERIFIED_PROBE':knownFixedWitness?'NOT_EQUIVALENT_ON_FIXED_REPLAY':'UNKNOWN';
  let category='unknown',quality='UNKNOWN',confidence='low',why='Existing finite evidence does not resolve comparative repair quality.';
  const af=a.faults.length>0,bf=b.faults.length>0;
  // A repair-relevant false positive or primary target miss is a concrete defect.
  if(af&&bf){category='both wrong';quality=booleanEquivalent?'EQUIVALENT_ASSERTION':'UNKNOWN';confidence=booleanEquivalent?'high':'medium';why=booleanEquivalent?'The assertions normalize to the same Boolean property under the shared clock/reset; both have a witnessed defect.':'Each candidate has a directly recorded primary or legal-probe defect. The evidence does not rank two defective assertions.';}
  else if(af&&!bf){category='quality difference';quality='B_BETTER_OBSERVED';confidence='medium';why='A has a witnessed defect; B has none in the available tests. This is an evidence-scoped preference, not proof of complete repair coverage.';}
  else if(!af&&bf){category='quality difference';quality='A_BETTER_OBSERVED';confidence='medium';why='B has a witnessed defect; A has none in the available tests. This is an evidence-scoped preference, not proof of complete repair coverage.';}
  else if(!af&&!bf){category='unknown';quality='UNKNOWN';confidence='low';why='Both pass the available checks, but those checks do not establish coverage of every repair obligation.';}
  if(row.parent_id==='case505_axis_stat_counter_frame_pulse_early'&&[a.id.slice(-2),b.id.slice(-2)].sort().join(',')==='06,07'){
    category='both wrong';quality='UNKNOWN';confidence='high';
    why='The repair obligation requires a status-valid pulse one cycle after the mandated absent cycle and preservation of captured length. A checks only the absent cycle; B compares stat_valid_o with the next-cycle frame_done_i and omits the later pulse and length.';
  }
  if(row.parent_id==='case510_cc_spill_register_flush_push_priority'&&[a.id.slice(-2),b.id.slice(-2)].sort().join(',')==='06,07'){
    category='quality difference';quality=a.id.endsWith('06')?'A_BETTER_OBSERVED':'B_BETTER_OBSERVED';confidence='high';
    why='Existing held-flush replay proves slot 07 false positive on fixed RTL. Slot 06 passes this trace, though it remains PARTIAL against the full obligation.';
  }
  outRows.push({pair_id:row.pair_id,parent_id:row.parent_id,candidate_A:a.id,candidate_B:b.id,
    assertion_A:a.sva,assertion_B:b.sva,
    semantic_A:a.semantic_meaning,semantic_B:b.semantic_meaning,
    semantic_difference:sameSva?'Identical SVA text.':delta.length?delta.join('; '):'AST fields equal; inspect quoted SVA for syntax-level differences.',
    semantic_equivalence:semanticEquivalence,
    unconstrained_formula_counterexample:formulaWitness,
    repair_obligation_excerpt:ctx.obligation.slice(0,1800),
    structured_repair_obligation:obligations[row.parent_id],
    candidate_A_obligation_mapping:obligationMapping(a,obligations[row.parent_id]),
    candidate_B_obligation_mapping:obligationMapping(b,obligations[row.parent_id]),
    rtl_change_summary:ctx.delta,
    feedback_signature:row.feedback_signature,quality_relation:quality,category,reason:why,confidence,
    candidate_A_faults:a.faults,candidate_B_faults:b.faults,
    candidate_A_primary:a.primary,candidate_B_primary:b.primary,
    candidate_A_full_probe_summary:{fixed_false_positive_probes:a.fp.length,target_or_holdout_miss_probes:a.miss.length},
    candidate_B_full_probe_summary:{fixed_false_positive_probes:b.fp.length,target_or_holdout_miss_probes:b.miss.length},
    count_difference:row.count_difference,count_analysis:countReview(row,a,b),
    evidence:{candidate_A:a.source,candidate_B:b.source,case_files:ctx.files,
      verified_timeline:timelineLine.has(row.pair_id)?{path:'deliverables/feedback_collision_reaudit_20261002/count_timeline_162.jsonl',line:timelineLine.get(row.pair_id)}:null,
      candidate_A_fixed_false_positive_witnesses:a.fp,candidate_B_fixed_false_positive_witnesses:b.fp,
      candidate_A_target_holdout_misses:a.miss,candidate_B_target_holdout_misses:b.miss,
      count_difference_probe_results:row.count_difference_probes,
      held_flush_replay:row.evidence.held_flush_replay}});
}
fs.writeFileSync(path.join(out,'adjudicated_pairs.jsonl'),outRows.map(x=>JSON.stringify(x)).join('\n')+'\n');
fs.writeFileSync(path.join(out,'adjudication_incidents.json'),JSON.stringify(incidents,null,2));
function csv(rows,columns){const q=v=>'"'+String(v??'').replaceAll('"','""')+'"';return [columns.map(q).join(','),...rows.map(r=>columns.map(k=>q(r[k])).join(','))].join('\n')+'\n';}
const index=outRows.map(x=>({pair_id:x.pair_id,parent_id:x.parent_id,candidate_A:x.candidate_A,candidate_B:x.candidate_B,
  feedback_signature:JSON.stringify(x.feedback_signature),quality_relation:x.quality_relation,category:x.category,
  semantic_difference:x.semantic_difference,semantic_equivalence:x.semantic_equivalence,
  repair_trigger:x.structured_repair_obligation.trigger,repair_check:x.structured_repair_obligation.check,
  A_obligation_mapping:x.candidate_A_obligation_mapping.notes.join('; '),
  B_obligation_mapping:x.candidate_B_obligation_mapping.notes.join('; '),
  count_difference:x.count_difference,count_mechanism:x.count_analysis.status,
  evidence:`${x.evidence.candidate_A} | ${x.evidence.candidate_B}`,confidence:x.confidence}));
fs.writeFileSync(path.join(out,'pair_index.csv'),csv(index,Object.keys(index[0])));
const countRows=outRows.filter(x=>x.count_difference).map(x=>({pair_id:x.pair_id,parent_id:x.parent_id,
  candidate_A:x.candidate_A,candidate_B:x.candidate_B,quality_category:x.category,
  differing_probes:x.count_analysis.probe_count,fixed_differing_probes:x.count_analysis.fixed_probe_count,
  buggy_differing_probes:x.count_analysis.buggy_probe_count,mechanism:x.count_analysis.status,
  explanation:x.count_analysis.reason}));
fs.writeFileSync(path.join(out,'count_difference_162.csv'),csv(countRows,Object.keys(countRows[0])));
const cnt=k=>Object.fromEntries([...new Set(outRows.map(x=>x[k]))].map(v=>[v,outRows.filter(x=>x[k]===v).length]));
const summary={pairs:outRows.length,count_difference_pairs:outRows.filter(x=>x.count_difference).length,
  categories:cnt('category'),relations:cnt('quality_relation'),semantic_equivalence:cnt('semantic_equivalence'),
  count_mechanism_unknown:outRows.filter(x=>x.count_difference&&x.count_analysis.status.includes('UNKNOWN')).length,
  unreadable_artifacts:incidents.length};
fs.writeFileSync(path.join(out,'adjudication_summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
