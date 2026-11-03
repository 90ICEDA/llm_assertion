import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";
const dir=path.join(process.cwd(),"deliverables","overfit_challenge_generalization_v2_20260810");
const out=path.join(dir,"overfit_challenge_v2.xlsx");
function line(s){const a=[];let x="",q=false;for(let i=0;i<s.length;i++){const c=s[i];if(c==='"'){if(q&&s[i+1]==='"'){x+='"';i++;}else q=!q;}else if(c===','&&!q){a.push(x);x="";}else x+=c;}a.push(x);return a;}
async function csv(f){const t=(await fs.readFile(path.join(dir,f),"utf8")).replace(/^\uFEFF/,"").trim();return t.split(/\r?\n/).map(line);}
function col(n){let s="";while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
function style(ws,m){const lc=col(m[0].length),nr=m.length;ws.showGridLines=false;ws.getRange(`A1:${lc}${nr}`).values=m;ws.getRange(`A1:${lc}1`).format={fill:"#17365D",font:{bold:true,color:"#FFFFFF"},wrapText:true,horizontalAlignment:"Center",borders:{preset:"all",style:"thin",color:"#D9E2F3"}};if(nr>1)ws.getRange(`A2:${lc}${nr}`).format={verticalAlignment:"Top",wrapText:true,borders:{preset:"all",style:"thin",color:"#E6E6E6"}};ws.freezePanes.freezeRows(1);ws.getRange(`A1:${lc}${nr}`).format.autofitColumns();ws.getRange(`A1:${lc}${nr}`).format.autofitRows();for(let i=1;i<=m[0].length;i++){const c=col(i);if((ws.getRange(`${c}:${c}`).format.columnWidth||0)>34)ws.getRange(`${c}:${c}`).format.columnWidth=34;}}
const wb=Workbook.create();
const summary=JSON.parse(await fs.readFile(path.join(dir,"acceptance_summary.json"),"utf8"));
const sm=[["metric","value"],...Object.entries(summary).map(([k,v])=>[k,String(v)])];let ws=wb.worksheets.add("Summary");style(ws,sm);
for(const [n,f] of [["Manifest","overfit_challenge_manifest.csv"],["Results","overfit_challenge_results.csv"],["Type Statistics","overfit_type_statistics.csv"],["Hard Pairs","hard_preference_pairs.csv"],["Pair Distribution","hard_pair_distribution.csv"],["Split Manifest","split_manifest.csv"],["Leakage Audit","leakage_audit_details.csv"]]){const m=await csv(f);ws=wb.worksheets.add(n);style(ws,m);}
await SpreadsheetFile.exportXlsx(wb).then(x=>x.save(out));console.log(out);
