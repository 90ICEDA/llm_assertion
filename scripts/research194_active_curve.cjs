// Measured-data-only standalone plots; no package installation.
const fs=require('node:fs'),path=require('node:path');
if(process.platform==='win32'&&!process.env.NAPI_RS_NATIVE_LIBRARY_PATH){
 const store=path.resolve(__dirname,'../node_modules/.pnpm');
 const pkg=fs.readdirSync(store).find(n=>n.startsWith('@napi-rs+canvas-win32-x64-msvc@'));
 if(pkg)process.env.NAPI_RS_NATIVE_LIBRARY_PATH=path.join(store,pkg,'node_modules/@napi-rs/canvas-win32-x64-msvc/skia.win32-x64-msvc.node');
}
const {createCanvas}=require('@napi-rs/canvas');
const dir=path.resolve(process.argv[2]);
const summary=JSON.parse(fs.readFileSync(path.join(dir,'analysis.json'),'utf8'));
const contextMode=process.argv[3]==='--trace-context';
if(contextMode)summary.cost_curve=JSON.parse(fs.readFileSync(path.join(dir,'trace_context_cost_curve.json'),'utf8'));
const units=JSON.parse(fs.readFileSync(path.join(dir,contextMode?'trace_context_unit_curves.json':'paired_unit_curves.json'),'utf8'));
const colors={S0:'#3566b0',S1:'#d27b16',S2:'#178471',S3:'#963e9c'};
const dash={S0:[],S1:[12,6],S2:[4,5],S3:[15,5,3,5]};
function panel(ctx,b,rows,title){
 const ymax=Math.max(1,Math.ceil(Math.max(...rows.map(r=>r.y))*1.15)),xmax=4;
 const X=x=>b.x+x/xmax*b.w,Y=y=>b.y+b.h-y/ymax*b.h;
 ctx.fillStyle='#172033';ctx.textAlign='left';ctx.font='bold 22px Arial';ctx.fillText(title,b.x,b.y-22);
 ctx.font='16px Arial';ctx.lineWidth=1;
 for(let i=0;i<=4;i++){const v=ymax*i/4,y=Y(v);ctx.strokeStyle='#e0e5ec';ctx.beginPath();ctx.moveTo(b.x,y);ctx.lineTo(b.x+b.w,y);ctx.stroke();ctx.fillStyle='#334155';ctx.textAlign='right';ctx.fillText(Number(v.toFixed(2)).toString(),b.x-12,y+5);}
 for(const x of [0,2,4]){ctx.textAlign='center';ctx.fillStyle='#334155';ctx.fillText(x,X(x),b.y+b.h+26);}
 ctx.strokeStyle='#334155';ctx.beginPath();ctx.moveTo(b.x,b.y);ctx.lineTo(b.x,b.y+b.h);ctx.lineTo(b.x+b.w,b.y+b.h);ctx.stroke();
 for(const strategy of Object.keys(colors)){
  const rr=rows.filter(r=>r.strategy===strategy).sort((a,b)=>a.x-b.x);ctx.strokeStyle=colors[strategy];ctx.lineWidth=3;ctx.setLineDash(dash[strategy]);ctx.beginPath();ctx.moveTo(X(0),Y(0));let prev=0;
  for(const r of rr){ctx.lineTo(X(r.x),Y(prev));ctx.lineTo(X(r.x),Y(r.y));prev=r.y;}ctx.stroke();ctx.setLineDash([]);
  for(const r of rr){ctx.fillStyle=colors[strategy];ctx.beginPath();ctx.arc(X(r.x),Y(r.y),3,0,2*Math.PI);ctx.fill();}
 }
}
function base(h,title,subtitle){
 const canvas=createCanvas(1400,h),ctx=canvas.getContext('2d');ctx.fillStyle='#fff';ctx.fillRect(0,0,1400,h);ctx.fillStyle='#172033';ctx.font='bold 29px Arial';ctx.fillText(title,100,54);ctx.font='19px Arial';ctx.fillStyle='#526076';ctx.fillText(subtitle,100,90);
 let i=0;for(const s of Object.keys(colors)){const x=850+i++*120;ctx.strokeStyle=colors[s];ctx.lineWidth=4;ctx.setLineDash(dash[s]);ctx.beginPath();ctx.moveTo(x,122);ctx.lineTo(x+35,122);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#172033';ctx.fillText(s,x+43,129);}return{canvas,ctx};
}
let {canvas,ctx}=base(840,contextMode?'Trace-context distinct first-violation gaps':'Cross-design evidence: first-violation gap discovery','Four designs, two paired selection seeds; shared public evidence excluded');
panel(ctx,{x:130,y:180,w:1180,h:485},summary.cost_curve.map(r=>({strategy:r.strategy,x:r.actual_native_execution_cost_per_unit,y:r.mean_new_distinct_gaps_per_case_seed})),'Mean new first-violation gaps per (case, seed)');
ctx.font='22px Arial';ctx.fillStyle='#172033';ctx.textAlign='center';ctx.fillText('Actual search native executions per paired (case, seed) unit',720,745);
ctx.font='17px Arial';ctx.fillStyle='#64748b';ctx.textAlign='left';ctx.fillText('Includes late-detected targets; transaction-wide misses are reported separately. One query = two RTL executions.',100,800);
fs.writeFileSync(path.join(dir,contextMode?'trace_context_mean_cost_curve.png':'paired_mean_cost_curve.png'),canvas.toBuffer('image/png'));
({canvas,ctx}=base(1040,contextMode?'Trace-context first-violation gaps by design':'First-violation gaps by design','Two paired selection seeds per design; different y-axis scales shown explicitly'));
const cases=[...new Set(units.map(u=>u.case_id))];
cases.forEach((caseId,index)=>{
 const rows=[];for(const strategy of Object.keys(colors))for(const x of [0,2,4]){
  const paired=units.filter(u=>u.case_id===caseId&&u.strategy===strategy);
  rows.push({strategy,x,y:paired.reduce((v,u)=>v+[...u.points].reverse().find(p=>p.native_execution_cost<=x).new_gaps,0)/paired.length});
 }
 panel(ctx,{x:115+(index%2)*670,y:205+Math.floor(index/2)*370,w:550,h:260},rows,caseId);
});
ctx.font='22px Arial';ctx.fillStyle='#172033';ctx.textAlign='center';ctx.fillText('Actual search native executions per paired unit',720,950);
ctx.font='17px Arial';ctx.fillStyle='#64748b';ctx.textAlign='left';ctx.fillText('Y: mean first-violation gaps, including late detections. Unknowns and transaction-wide misses are separate.',100,1000);
fs.writeFileSync(path.join(dir,contextMode?'trace_context_per_design_cost_curves.png':'per_design_cost_curves.png'),canvas.toBuffer('image/png'));
fs.writeFileSync(path.join(dir,contextMode?'trace_context_plot_status.json':'plot_status.json'),JSON.stringify({renderer:'existing @napi-rs/canvas',measured_data_only:true,trace_context_deduplicated:contextMode},null,2)+'\n');
console.log(dir);
