// Windows runner for the frozen feedback audit; preserves the Python source too.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const base = path.join(root, 'outputs', 'behavioral_preference_pilot_v1');
const out = path.join(root, 'deliverables', 'feedback_collision_reaudit_20261002');
fs.mkdirSync(out, {recursive:true});
const read = p => JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
const rel = p => path.relative(root,p).replaceAll('\\','/');
const hash = (...xs) => crypto.createHash('sha256').update(xs.join('\x1f')).digest('hex').slice(0,24);
let rows=[], failures=[];
for (const parent of fs.readdirSync(path.join(base,'behavioral_probes_v3'))) {
  const dir=path.join(base,'behavioral_probes_v3',parent);
  if (!fs.statSync(dir).isDirectory()) continue;
  try {
    const pr=read(path.join(dir,'parent_result.json'));
    const ids=pr.policies.disagreement_guided;
    const chosen=pr.candidate_sets.filter(x=>x.probe_policy==='disagreement_guided');
    const ev={};
    for(let slot=1;slot<=8;slot++) {
      const cid=`${parent}__v3_slot_${String(slot).padStart(2,'0')}`;
      const p=path.join(base,'sequential_generation_v3_pilot30',parent,`slot_${String(slot).padStart(2,'0')}`,'attempt_01','evidence.json');
      ev[cid]={data:read(p),path:p};
    }
    const caseRoot=['rtl_cases_real_scale210_independent_next','rtl_cases_real_scale210_independent','rtl_cases_real_active','rtl_cases_real_scale120','rtl_cases_real_iverilog_ready','rtl_cases_real'].find(n=>fs.existsSync(path.join(root,n,parent)));
    const caseDir=path.join(root,caseRoot||'rtl_cases_real_scale210_independent_next',parent);
    if(!caseRoot) failures.push({parent,error:'case directory missing'});
    const context=Object.fromEntries(['spec.md','mutation.diff','buggy.v','correct.v','golden.sva'].map(n=>[n,fs.existsSync(path.join(caseDir,n))?rel(path.join(caseDir,n)):null]));
    const results={};
    for(const c of chosen){
      results[c.candidate_id]={};
      for(const pid of ids){
        const p=path.join(dir,'runs',pid,c.candidate_id,'result.json');
        try {const d=read(p);results[c.candidate_id][pid]={fixed:d.rtl.correct.fail_hits,buggy:d.rtl.buggy.fail_hits,path:rel(p)};}
        catch(e){failures.push({parent,candidate:c.candidate_id,probe:pid,path:rel(p),error:String(e)});}
      }
    }
    for(let i=0;i<chosen.length;i++)for(let j=i+1;j<chosen.length;j++){
      let [a,b]=[chosen[i],chosen[j]].sort((x,y)=>x.candidate_id.localeCompare(y.candidate_id));
      if(JSON.stringify(a.fp_probe_ids)!==JSON.stringify(b.fp_probe_ids)||JSON.stringify(a.tp_mutant_ids)!==JSON.stringify(b.tp_mutant_ids))continue;
      let ea=ev[a.candidate_id],eb=ev[b.candidate_id],same=ea.data.sva===eb.data.sva;
      let diffs=[];
      for(const pid of ids){const x=results[a.candidate_id][pid],y=results[b.candidate_id][pid];if(x&&y&&(x.fixed!==y.fixed||x.buggy!==y.buggy))diffs.push({probe_id:pid,a_fixed:x.fixed,b_fixed:y.fixed,a_buggy:x.buggy,b_buggy:y.buggy,a_result:x.path,b_result:y.path});}
      let relation=same?'equivalent':'UNKNOWN',category=same&&ea.data.fixed_safe&&ea.data.target_detect&&ea.data.non_vacuous?'both acceptable':'unknown',confidence=same?'high':'low';
      let reason=same?'Identical SVA text; finite probes agree.':'Different SVA semantics require review against the repair obligation; binary feedback cannot settle quality.';
      const known=parent==='case510_cc_spill_register_flush_push_priority'&&[a.candidate_id.slice(-2),b.candidate_id.slice(-2)].sort().join(',')==='06,07';
      if(known){relation=a.candidate_id.endsWith('06')?'A_BETTER':'B_BETTER';category='quality difference';confidence='high';reason='Existing held-flush fixed-RTL replay proves slot 07 false-positive; slot 06 passes this case but is PARTIAL against the full obligation.';}
      rows.push({pair_id:hash('disagreement_guided',parent,a.candidate_id,b.candidate_id),parent_id:parent,candidate_A:a.candidate_id,candidate_B:b.candidate_id,assertion_A:ea.data.sva,assertion_B:eb.data.sva,semantic_difference:same?'identical SVA':`A: ${JSON.stringify(ea.data.ast)}; B: ${JSON.stringify(eb.data.ast)}`,feedback_signature:{policy:'disagreement_guided',fp_probe_ids:a.fp_probe_ids,tp_mutant_ids:a.tp_mutant_ids},quality_relation:relation,category,count_difference:diffs.length>0,count_difference_probes:diffs,count_interpretation:diffs.length?'Fail-hit frequency alone does not rank quality; repeated triggers of one violation are possible.':'No fail-hit difference on selected probes.',evidence:{candidate_A:rel(ea.path),candidate_B:rel(eb.path),case_context:context,held_flush_replay:known?'deliverables/blind_reaudit_20260921/witnesses/case510_held_flush/replay.md':null},reason,confidence});
    }
  }catch(e){failures.push({parent,error:String(e)});}
}
fs.writeFileSync(path.join(out,'pairs.jsonl'),rows.map(x=>JSON.stringify(x)).join('\n')+'\n');
fs.writeFileSync(path.join(out,'failures.json'),JSON.stringify(failures,null,2));
const count=k=>Object.fromEntries([...new Set(rows.map(x=>x[k]))].map(v=>[v,rows.filter(x=>x[k]===v).length]));
const summary={pairs:rows.length,count_difference_pairs:rows.filter(x=>x.count_difference).length,quality_relations:count('quality_relation'),categories:count('category'),failures:failures.length};
fs.writeFileSync(path.join(out,'summary.json'),JSON.stringify(summary,null,2));
console.log(JSON.stringify(summary));
