// Standalone cost curve from measured JSON, using the existing native Canvas runtime.
// Usage: node scripts/research_active_curve.cjs RUN_DIR
const fs = require('node:fs');
const path = require('node:path');
// Some workspace pnpm links are not visible to Node's resolver; use the already
// installed Windows binding directly without installing or changing packages.
if (process.platform === 'win32' && !process.env.NAPI_RS_NATIVE_LIBRARY_PATH) {
 const store=path.resolve(__dirname,'../node_modules/.pnpm');
 const pkg=fs.readdirSync(store).find(n=>n.startsWith('@napi-rs+canvas-win32-x64-msvc@'));
 if(pkg) process.env.NAPI_RS_NATIVE_LIBRARY_PATH=path.join(store,pkg,'node_modules/@napi-rs/canvas-win32-x64-msvc/skia.win32-x64-msvc.node');
}
const { createCanvas } = require('@napi-rs/canvas');
const dir = path.resolve(process.argv[2]);
const pairedMean=process.argv[3]==='--paired-mean';
const source=pairedMean?'paired_mean_cost_curve.json':'cost_curve.json';
const stem=pairedMean?'paired_mean_cost_curve':'cost_curve';
const rows = JSON.parse(fs.readFileSync(path.join(dir, source), 'utf8')).map(r=>pairedMean?
 {...r,actual_native_executions:r.actual_native_executions_per_unit,confirmed_gaps:r.mean_public_unexposed_gaps}:r);
const native = 'actual_native_executions' in rows[0];
const xfield = native ? 'actual_native_executions' : 'actual_simulations';
const canvas = createCanvas(1400, 840), ctx = canvas.getContext('2d');
const box = {x:130,y:150,w:1190,h:520};
const xmax = Math.max(...rows.map(r => r[xfield]));
const ymax = pairedMean?1.25:Math.max(1,Math.ceil(Math.max(...rows.map(r => r.confirmed_gaps)) * 1.15));
const X = v=>box.x+box.w*v/xmax, Y=v=>box.y+box.h-box.h*v/ymax;
ctx.fillStyle = '#fff';ctx.fillRect(0,0,1400,840);
ctx.fillStyle='#172033';ctx.font='bold 30px Arial';
ctx.fillText(pairedMean?'Complex FIFO: paired mean acquisition coverage':native ? 'Complex FIFO: native SVA search' : '11 historical candidate pairs: diagnostic search',130,62);
ctx.font='21px Arial';ctx.fillStyle='#526076';
ctx.fillText(pairedMean?'One parent, one candidate task, three paired seeds; public gaps excluded':native?'One parent; 3 paired seeds; public gaps excluded':'Six frozen parent cases; 3 paired seeds; procedural checker',130,101);
ctx.lineWidth=1.5;
for(let i=0;i<=5;i++){
 const v=ymax*i/5,y=Y(v);ctx.strokeStyle='#e0e5ec';ctx.beginPath();ctx.moveTo(box.x,y);ctx.lineTo(box.x+box.w,y);ctx.stroke();
 ctx.fillStyle='#334155';ctx.font='19px Arial';ctx.textAlign='right';ctx.fillText(Number(v.toFixed(pairedMean?2:1)).toString(),box.x-18,y+7);
}
for(let i=0;i<=4;i++){
 const v=xmax*i/4,x=X(v);ctx.fillStyle='#334155';ctx.textAlign='center';ctx.fillText(Math.round(v).toString(),x,box.y+box.h+35);
}
ctx.strokeStyle='#334155';ctx.beginPath();ctx.moveTo(box.x,box.y);ctx.lineTo(box.x,box.y+box.h);ctx.lineTo(box.x+box.w,box.y+box.h);ctx.stroke();
const colors={S0:'#3566b0',S1:'#e69327',S2:'#279c85',S3:'#a148a5'};
const dash={S0:[],S1:[12,6],S2:[4,5],S3:[15,5,3,5]};
for(const m of ['S0','S1','S2','S3']){
 const rs=rows.filter(r=>r.method===m).sort((a,b)=>a[xfield]-b[xfield]);
 ctx.strokeStyle=colors[m];ctx.lineWidth=4;ctx.setLineDash(dash[m]);ctx.beginPath();ctx.moveTo(X(0),Y(0));let prev=0;
 for(const r of rs){ctx.lineTo(X(r[xfield]),Y(prev));ctx.lineTo(X(r[xfield]),Y(r.confirmed_gaps));prev=r.confirmed_gaps;}
 ctx.stroke();ctx.setLineDash([]);
 for(const r of rs){ctx.fillStyle=colors[m];ctx.beginPath();ctx.arc(X(r[xfield]),Y(r.confirmed_gaps),4,0,Math.PI*2);ctx.fill();}
 const lx=850+['S0','S1','S2','S3'].indexOf(m)*116;ctx.strokeStyle=colors[m];ctx.setLineDash(dash[m]);ctx.beginPath();ctx.moveTo(lx,125);ctx.lineTo(lx+35,125);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#172033';ctx.textAlign='left';ctx.font='20px Arial';ctx.fillText(m,lx+43,132);
}
ctx.fillStyle='#172033';ctx.font='23px Arial';ctx.textAlign='center';
ctx.fillText(pairedMean?'Actual search native executions per paired task/seed unit':native?'Actual native executions (all paired seeds)':'Actual RTL simulations (all parents and paired seeds)',725,747);
ctx.save();ctx.translate(40,410);ctx.rotate(-Math.PI/2);ctx.fillText(pairedMean?'Mean public-unexposed gaps per paired unit':'Distinct confirmed candidate gaps',0,0);ctx.restore();
ctx.font='18px Arial';ctx.fillStyle='#64748b';ctx.textAlign='left';
ctx.fillText(pairedMean?'Same final gap in all groups. S3 ties S2; seeds are repeated measurements, not independent bugs.':'Unknowns and repeats consume cost. Candidate gaps are not independent bugs. No model calls.',130,800);
fs.writeFileSync(path.join(dir,stem+'.png'),canvas.toBuffer('image/png'));
fs.writeFileSync(path.join(dir,pairedMean?'paired_mean_plot_status.json':'plot_status.json'),JSON.stringify({status:'rendered',renderer:'existing @napi-rs/canvas',source,xfield:pairedMean?'actual_native_executions_per_unit':xfield,origin_zero:true,measured_data_only:true},null,2)+'\n');
console.log(path.join(dir,stem+'.png'));
