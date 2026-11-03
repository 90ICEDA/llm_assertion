import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = process.cwd();
const dir = path.join(root, "deliverables", "overfit_challenge_generalization_20260810");
const out = path.join(dir, "overfit_challenge_generalization_acceptance.xlsx");

function csvLine(s) { const a=[]; let x="",q=false; for(let i=0;i<s.length;i++){const c=s[i]; if(c==='"'){if(q&&s[i+1]==='"'){x+='"';i++;}else q=!q;} else if(c===','&&!q){a.push(x);x="";} else x+=c;} a.push(x); return a; }
async function csv(name){const t=(await fs.readFile(path.join(dir,name),"utf8")).replace(/^\uFEFF/,"").trim(); return t.split(/\r?\n/).map(csvLine);}
function col(n){let s=""; while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);} return s;}
function style(sheet,m){const last=col(m[0].length), rows=m.length; sheet.showGridLines=false; sheet.getRange(`A1:${last}${rows}`).values=m; sheet.getRange(`A1:${last}1`).format={fill:"#17365D",font:{bold:true,color:"#FFFFFF"},wrapText:true,horizontalAlignment:"Center"}; if(rows>1) sheet.getRange(`A2:${last}${rows}`).format={verticalAlignment:"Top",wrapText:true,borders:{preset:"all",style:"thin",color:"#E6E6E6"}}; sheet.freezePanes.freezeRows(1); sheet.getRange(`A1:${last}${rows}`).format.autofitColumns(); sheet.getRange(`A1:${last}${rows}`).format.autofitRows(); for(let i=1;i<=m[0].length;i++){const c=col(i); if((sheet.getRange(`${c}:${c}`).format.columnWidth||0)>36) sheet.getRange(`${c}:${c}`).format.columnWidth=36;} sheet.getRange(`A1:${last}${rows}`).format.borders={preset:"all",style:"thin",color:"#D9E2F3"};}

const wb = Workbook.create();
const sheets = [
  ["Coverage", "acceptance_coverage_and_gaps.csv"],
  ["Challenge Manifest", "overfit_challenge_manifest.csv"],
  ["Challenge Results", "overfit_challenge_results.csv"],
  ["Type Statistics", "overfit_type_statistics.csv"],
  ["Hard Pairs", "hard_preference_pairs.csv"],
  ["Pair Distribution", "hard_pair_distribution.csv"],
  ["Split Manifest", "split_manifest.csv"],
];
for (const [name,file] of sheets){const m=await csv(file); const s=wb.worksheets.add(name); style(s,m);}
const summary=JSON.parse(await fs.readFile(path.join(dir,"acceptance_summary.json"),"utf8"));
const audit=JSON.parse(await fs.readFile(path.join(dir,"automatic_leakage_audit.json"),"utf8"));
const sm=Object.entries(summary).map(([k,v])=>[k,Array.isArray(v)?v.join(" | "):String(v)]); sm.unshift(["metric","value"]); sm.push(["leakage_failure_count",String(audit.failure_count)]); const ss=wb.worksheets.add("Summary"); style(ss,sm);
await SpreadsheetFile.exportXlsx(wb).then(x=>x.save(out));
console.log(out);
