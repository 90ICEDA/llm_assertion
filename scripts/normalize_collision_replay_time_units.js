// The replay logger's %t uses the simulation's 1ps precision. Rename the
// initially mislabeled *_ns JSON keys to *_ps, retaining raw stdout unchanged.
const fs=require('fs'),path=require('path');
const root=path.resolve(__dirname,'..');
const dir=path.join(root,'deliverables/feedback_collision_reaudit_20261002');
let changed=0;
for(const folder of ['time_replays','time_replays_deferred']){
  const top=path.join(dir,folder);if(!fs.existsSync(top))continue;
  function walk(p){for(const ent of fs.readdirSync(p,{withFileTypes:true})){
    const q=path.join(p,ent.name);if(ent.isDirectory())walk(q);else if(ent.name==='replay.json'){
      const x=JSON.parse(fs.readFileSync(q,'utf8'));let edited=false;
      for(const run of Object.values(x.runs))for(const [a,b] of [['antecedent_times_ns','antecedent_times_ps'],['failure_times_ns','failure_times_ps']])
        if(Object.hasOwn(run,a)){run[b]=run[a];delete run[a];edited=true;}
      if(edited){fs.writeFileSync(q,JSON.stringify(x,null,2));changed++;}
    }
  }}walk(top);
}
console.log(JSON.stringify({normalized_replay_json:changed}));
