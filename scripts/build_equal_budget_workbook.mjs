import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/AssertionForge-main1";
const outDir = path.join(root, "deliverables/equal_budget_visible_selection_20260809");
const audit = JSON.parse(await fs.readFile(path.join(outDir, "heldout_invariance_audit.json"), "utf8"));

function parseCSV(text) {
  const rows = []; let row = [], field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (ch === '"') quoted = false;
      else field += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === ',') { row.push(field); field = ""; }
    else if (ch === '\n') { row.push(field.replace(/\r$/, "")); rows.push(row); row = []; field = ""; }
    else field += ch;
  }
  if (field.length || row.length) { row.push(field.replace(/\r$/, "")); rows.push(row); }
  const width = Math.max(...rows.map(r => r.length));
  const cv = v => {
    if (/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(v)) return Number(v);
    if (/^true$/i.test(v)) return true;
    if (/^false$/i.test(v)) return false;
    return v;
  };
  return rows.map((r, ri) => [...r, ...Array(width-r.length).fill("")].map(v => ri ? cv(v) : v));
}

const wb = Workbook.create();
const readme = wb.worksheets.add("README");
readme.showGridLines = false;
readme.getRange("A1:H1").merge();
readme.getRange("A1").values = [["Equal-budget Candidate Pools & Visible-only Selection"]];
readme.getRange("A1:H1").format = { fill: "#17365D", font: { bold: true, color: "#FFFFFF", size: 17 }, rowHeight: 30 };
readme.getRange("A3:B13").values = [
  ["Protocol item", "Value"], ["Primary unit", "40 canonical parents"],
  ["Sensitivity unit", "120 case variants"], ["Models", "Claude / GPT"],
  ["Budget per pool", 4], ["Pools", "raw4; temporal4; raw2+temporal2; four reps×1"],
  ["Visible policies", "first; random; hard filter; score; abstain; fallback"],
  ["Evaluation-only", "oracle upper bound"], ["Held-out invariance", "PASS"],
  ["Implicit fallback", "0"], ["Repair", "not run"],
];
readme.getRange("D3:H8").values = [
  ["Held-out isolation audit", "SHA-256", "", "", ""],
  ["Original", audit.original_visible_selection_sha256, "", "", ""],
  ["Held-out deleted", audit.heldout_deleted_selection_sha256, "", "", ""],
  ["Held-out shuffled", audit.heldout_shuffled_selection_sha256, "", "", ""],
  ["All identical", true, "", "", ""],
  ["Oracle included in hash", false, "", "", ""],
];
readme.getRange("A15:H15").merge(); readme.getRange("A15").values = [["Zero-pass behavior"]];
readme.getRange("A16:H20").merge(true); readme.getRange("A16:A20").values = [
  ["hard_filter and abstain: explicit abstain_no_hard_pass; no candidate is silently selected."],
  ["fallback: explicit_fallback_first and zero_pass_disposition=explicit_fallback."],
  ["first/random/score_ranking also return explicit abstain whenever the entire pool has zero hard-pass candidates."],
  ["oracle_upper_bound reads held-out only after selection and is excluded from the invariance hash."],
  ["All result sheets retain pool, policy, parent, candidate UID, feature vector, disposition, and held-out outcome."],
];

const imports = [
  ["Equal Budget", "equal_budget_comparison.csv"], ["Macro Summary", "equal_budget_macro_summary.csv"],
  ["Paired Comparisons", "equal_budget_paired_comparisons.csv"], ["Selected Parent", "parent_deduplicated_results.csv"],
  ["Selected All", "selected_candidate_details.csv"], ["Coverage Curve", "coverage_success_curve.csv"],
  ["Pool Manifest", "equal_budget_pool_manifest.csv"], ["Visible Features", "visible_only_candidate_features.csv"],
];
for (const [name, file] of imports) {
  const rows = parseCSV((await fs.readFile(path.join(outDir, file), "utf8")).replace(/^\uFEFF/, ""));
  const sheet = wb.worksheets.add(name);
  sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length).values = rows;
}

const names = ["README", ...imports.map(x => x[0])];
for (const name of names) {
  const s = wb.worksheets.getItem(name); const used = s.getUsedRange();
  s.showGridLines = false; s.freezePanes.freezeRows(name === "README" ? 3 : 1);
  if (name !== "README") {
    used.getRow(0).format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 32 };
    used.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
    used.format.verticalAlignment = "top"; used.format.wrapText = true; used.format.autofitColumns();
    for (let c=0; c<used.columnCount; c++) if (used.getColumn(c).format.columnWidth > 42) used.getColumn(c).format.columnWidth = 42;
  }
}
readme.getRange("A3:B3").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" } };
readme.getRange("D3:H3").format = { fill: "#1F4E78", font: { bold: true, color: "#FFFFFF" } };
readme.getRange("A15:H15").format = { fill: "#D9EAF7", font: { bold: true, color: "#17365D" } };
readme.getRange("A3:H20").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
readme.getRange("A16:H20").format.wrapText = true; readme.getRange("A16:H20").format.rowHeight = 28;
readme.getRange("A:A").format.columnWidth = 28; readme.getRange("B:B").format.columnWidth = 34;
readme.getRange("D:D").format.columnWidth = 24; readme.getRange("E:E").format.columnWidth = 68;

const xlsx = await SpreadsheetFile.exportXlsx(wb);
const outFile = path.join(outDir, "equal_budget_visible_selection.xlsx");
await xlsx.save(outFile);
const previewDir = path.join(outDir, "workbook_previews"); await fs.mkdir(previewDir, {recursive:true});
for (const [name, range] of Object.entries({"README":"A1:H20","Equal Budget":"A1:N25","Coverage Curve":"A1:J30"})) {
  const png = await wb.render({sheetName:name,range,scale:0.75,format:"png"});
  await fs.writeFile(path.join(previewDir, name.replaceAll(" ","_")+".png"), new Uint8Array(await png.arrayBuffer()));
}
await wb.inspect({kind:"sheet",include:"id,name",maxChars:6000});
console.log(outFile);
