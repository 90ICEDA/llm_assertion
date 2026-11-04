// Read-only statistical supplement: paired task/seed means, no new simulation.
// Usage: node scripts/research_active_paired_curve.cjs RUN_DIR
const fs=require('node:fs'), path=require('node:path'), crypto=require('node:crypto');
const dir=path.resolve(process.argv[2]);
const read=n=>JSON.parse(fs.readFileSync(path.join(dir,n),'utf8'));
const write=(n,v)=>fs.writeFileSync(path.join(dir,n),JSON.stringify(v,null,2)+'\n');
const assert=require('node:assert/strict');
assert.equal(read('outcome.json').status,'completed');
const records=read('records.json'), methods=['S0','S1','S2','S3'];
const units=[...new Set(records.map(r=>JSON.stringify([r.pair,r.seed])))].sort();
assert.equal(units.length,3);assert.equal(new Set(records.map(r=>r.pair)).size,1);
const steps=[],first=[],costs=new Set([0]);
for(const u of units){
 const [task,seed]=JSON.parse(u);
 for(const method of methods){
  const rr=records.filter(r=>r.pair===task&&r.seed===seed&&r.method===method).sort((a,b)=>a.query-b.query);
  assert.equal(rr.length,4);assert.deepEqual(rr.map(r=>r.query),[0,1,2,3]);
  const seen=new Set();let actual=0;
  steps.push({task,seed,method,query_count:0,actual_native_executions:0,public_unexposed_gap_count:0,gap_keys:[]});
  for(const r of rr){
   assert(Number.isFinite(r.native_executions)&&r.native_executions>0);actual+=r.native_executions;costs.add(actual);
   for(const key of r.public_unexposed_keys){
    if(!seen.has(key))first.push({task,seed,method,gap_key:key,first_query:r.query+1,actual_native_executions:actual});
    seen.add(key);
   }
   steps.push({task,seed,method,query_count:r.query+1,actual_native_executions:actual,
    public_unexposed_gap_count:seen.size,gap_keys:[...seen].sort()});
  }
 }
}
// Independent crosscheck against the already reported per-gap discovery ledger.
const existing=read('first_discovery_cost.json');
assert.equal(existing.length,first.length);
for(const r of first){
 const old=existing.find(x=>x.seed===r.seed&&x.method===r.method&&x.key===r.gap_key);
 assert(old);assert.equal(old.actual_native_executions,r.actual_native_executions);assert.equal(old.first_query,r.first_query);
}
const curve=[];
for(const method of methods){
 for(const cost of [...costs].sort((a,b)=>a-b)){
  const members=units.map(u=>{
   const [task,seed]=JSON.parse(u);
   const rr=steps.filter(r=>r.task===task&&r.seed===seed&&r.method===method&&r.actual_native_executions<=cost);
   const r=rr.at(-1);assert(r);
   return {task,seed,public_unexposed_gaps:r.public_unexposed_gap_count,actual_executions_at_last_query:r.actual_native_executions};
  });
  curve.push({method,actual_native_executions_per_unit:cost,
   mean_public_unexposed_gaps:members.reduce((a,r)=>a+r.public_unexposed_gaps,0)/members.length,
   paired_unit_count:members.length,unit_observations:members});
 }
}
write('paired_mean_cost_curve.json',curve);write('paired_unit_cost_curve.json',steps);
write('paired_seed_first_discovery_cost.json',first);
fs.writeFileSync(path.join(dir,'paired_mean_cost_curve.csv'),
 'method,actual_native_executions_per_unit,mean_public_unexposed_gaps,paired_unit_count\n'+
 curve.map(r=>[r.method,r.actual_native_executions_per_unit,r.mean_public_unexposed_gaps,r.paired_unit_count].join(',')).join('\n')+'\n');
write('paired_mean_statistics.json',{
 statistic:'Arithmetic mean of within-task/seed distinct confirmed public-unexposed candidate gap counts at equal measured native execution cost.',
 pairing_unit:'(candidate task bounded__valid, seed)',parent_count:1,candidate_task_count:1,paired_seed_count:3,
 contrast_to_original:'Original cost_curve.json unions gap keys over seeds and plots total cost across all seeds. This supplement keeps each seed/task as a repeated measurement and averages their within-unit counts; seeds are not independent bugs.',
 x_cost:'Search executions per unit only. Public 32 executions and two build smoke executions are common overhead, reported separately in cost.json; no invented costs for unobserved discoveries.',
 evidence_scope:'One archived candidate task on one FIFO with known artificial faults. Descriptive paired timing, no significance or cross-parent generalization claim.',
 input_sha256:crypto.createHash('sha256').update(fs.readFileSync(path.join(dir,'records.json'))).digest('hex'),
 new_native_executions:0,model_calls:0,first_discovery_ledger_crosscheck:true
});
const md=['<!-- paired-mean-supplement -->','',
 '[Paired mean coverage curve](paired_mean_cost_curve.png) · [curve data](paired_mean_cost_curve.json) · [per-unit data](paired_unit_cost_curve.json)', '',
 'The original pooled curve unions the same gap across all seeds and uses their total execution cost. This supplementary curve averages each (candidate task, seed) unit at the same actual search execution cost per unit. There is one candidate task and one FIFO parent, repeated with three seeds; these are not three independent bugs. Shared public/build costs remain separate in cost.json.', '',
 '|Seed|S0 first discovery executions|S1|S2|S3|','|---|---:|---:|---:|---:|'];
for(const u of units){const [task,seed]=JSON.parse(u);md.push('|'+seed+'|'+methods.map(m=>{
 const r=first.filter(r=>r.task===task&&r.seed===seed&&r.method===m);assert.equal(r.length,1);return r[0].actual_native_executions;
}).join('|')+'|');}
md.push('|Mean|'+methods.map(m=>(first.filter(r=>r.method===m).reduce((a,r)=>a+r.actual_native_executions,0)/3).toFixed(2)).join('|')+'|', '',
 'S3 finds the same gap earlier than S0 in two seeds and ties in one; the same comparison holds against S1. S3 ties S2 in all three seeds. At 16 executions per unit, mean coverage is 1/3 for S0 and S1 and 1 for S2 and S3. Every strategy reaches one gap per unit by 64 executions; this is an acquisition timing difference, not an added final gap or superiority over S2.', '',
 'This supplement uses the completed records only, crosschecked against the existing first-discovery ledger. No new simulation, policy change, seed selection or model call was made.');
const reportPath=path.join(dir,'REPORT.md');const report=fs.readFileSync(reportPath,'utf8').split('<!-- paired-mean-supplement -->')[0].trimEnd();
fs.writeFileSync(reportPath,report+'\n\n'+md.join('\n')+'\n');
console.log(JSON.stringify({paired_units:units.length,curve_points:curve.length,first_discoveries:first.length,validated:true}));
