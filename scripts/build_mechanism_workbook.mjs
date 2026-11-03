import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "D:/AssertionForge-main1";
const outDir = path.join(root, "deliverables/final46_mechanism_analysis_20260808");
const wb = Workbook.create();
const overview = wb.worksheets.add("README");
overview.showGridLines = false;
overview.getRange("A1:H1").merge();
overview.getRange("A1").values = [["Final46 Trace & RTL Context Mechanism Analysis"]];
overview.getRange("A1:H1").format = { fill: "#17365D", font: { bold: true, color: "#FFFFFF", size: 18 }, rowHeight: 30 };
overview.getRange("A3:B12").values = [
  ["Audit item", "Value"],
  ["Analysis unit", "parent bug"],
  ["Parent bugs", 46],
  ["Models", "GPT / Claude / Qwen"],
  ["Candidates per cell", 4],
  ["Trace mechanisms / rows", "17 / 9,384"],
  ["RTL mechanisms / rows", "9 / 4,968"],
  ["Duplicate keys", 0],
  ["Non-both-success review rows", 97],
  ["Manually reviewed rows", 97],
];
overview.getRange("D3:E8").values = [
  ["Raw–temporal quadrant", "Count"],
  ["Both success", 41],
  ["Raw success / temporal fail", 21],
  ["Temporal success / raw fail", 3],
  ["Both fail", 73],
  ["Total model×parent", 138],
];
overview.getRange("A14:H14").merge();
overview.getRange("A14").values = [["Reading guide"]];
overview.getRange("A15:H21").merge(true);
overview.getRange("A15:A21").values = [
  ["Primary metric: whether any of 4 candidates succeeds on each parent bug."],
  ["Paired comparisons: exact McNemar within each model; effect size is paired risk difference."],
  ["Trace baseline: raw_good_bad. RTL baseline: full_rtl."],
  ["Exploratory p-values are not multiplicity-corrected; interpret with direction and case evidence."],
  ["Manual Failures and Review Packet both cover all 97 non-both-success model×case rows."],
  ["See MECHANISM_ANALYSIS.md for the narrative conclusions and case-supported interpretation."],
  ["Generated 2026-08-09; matrix completeness and unique keys audited before export."],
];

const imports = [
  ["Trace Summary", "trace_control_summary.csv"],
  ["Trace Paired", "trace_control_paired_comparisons.csv"],
  ["Trace Cases", "trace_case_outcomes.csv"],
  ["RTL Summary", "rtl_context_summary.csv"],
  ["RTL Paired", "rtl_context_paired_comparisons.csv"],
  ["RTL Cases", "rtl_case_outcomes.csv"],
  ["Quadrants", "raw_temporal_quadrants.csv"],
  ["Manual Failures", "manual_failure_analysis.csv"],
  ["Review Packet", "failure_analysis_review_packet.csv"],
];

function parseCSV(text) {
  const rows = [];
  let row = [], field = "", quoted = false;
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
  const convert = value => {
    if (/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(value)) return Number(value);
    if (value === "True" || value === "true") return true;
    if (value === "False" || value === "false") return false;
    return value;
  };
  return rows.map((r, ri) => [...r, ...Array(width - r.length).fill("")].map(v => ri === 0 ? v : convert(v)));
}

for (const [sheetName, fileName] of imports) {
  const csv = await fs.readFile(path.join(outDir, fileName), "utf8");
  const rows = parseCSV(csv.replace(/^\uFEFF/, ""));
  const sheet = wb.worksheets.add(sheetName);
  sheet.getRangeByIndexes(0, 0, rows.length, rows[0].length).values = rows;
}

const headerFill = "#1F4E78";
const altFill = "#D9EAF7";
const sheetNames = ["README", ...imports.map(x => x[0])];
for (const sheetName of sheetNames) {
  const s = wb.worksheets.getItem(sheetName);
  const used = s.getUsedRange();
  if (!used) continue;
  s.showGridLines = false;
  s.freezePanes.freezeRows(s.name === "README" ? 3 : 1);
  if (s.name !== "README") {
    const header = used.getRow(0);
    header.format = { fill: headerFill, font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 32 };
    used.format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
    used.format.verticalAlignment = "top";
    used.format.autofitColumns();
    const colCount = used.columnCount;
    for (let c = 0; c < colCount; c++) {
      const col = used.getColumn(c);
      if (col.format.columnWidth > 42) col.format.columnWidth = 42;
    }
    used.format.wrapText = true;
    used.format.autofitRows();
  }
}

overview.getRange("A3:B3").format = { fill: headerFill, font: { bold: true, color: "#FFFFFF" } };
overview.getRange("D3:E3").format = { fill: headerFill, font: { bold: true, color: "#FFFFFF" } };
overview.getRange("A14:H14").format = { fill: altFill, font: { bold: true, color: "#17365D" } };
overview.getRange("A3:H21").format.borders = { preset: "all", style: "thin", color: "#D9E2F3" };
overview.getRange("A15:H21").format.wrapText = true;
overview.getRange("A15:H21").format.rowHeight = 28;
overview.getRange("A:A").format.columnWidth = 31;
overview.getRange("B:B").format.columnWidth = 24;
overview.getRange("D:D").format.columnWidth = 34;
overview.getRange("E:E").format.columnWidth = 15;

const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(path.join(outDir, "mechanism_analysis.xlsx"));
const previewDir = path.join(outDir, "workbook_previews");
await fs.mkdir(previewDir, { recursive: true });
const previewRanges = {
  "README": "A1:H21",
  "Trace Summary": "A1:I25",
  "RTL Summary": "A1:I25",
  "Quadrants": "A1:L25",
  "Manual Failures": "A1:Q10",
};
for (const [name, range] of Object.entries(previewRanges)) {
  const png = await wb.render({ sheetName: name, range, scale: 0.65, format: "png" });
  await fs.writeFile(path.join(previewDir, `${name.replaceAll(" ", "_")}.png`), new Uint8Array(await png.arrayBuffer()));
}
const inspection = await wb.inspect({ kind: "sheet", include: "id,name", maxChars: 6000 });
await fs.writeFile(path.join(outDir, "workbook_inspection.txt"), inspection.ndjson ?? String(inspection), "utf8");
console.log(path.join(outDir, "mechanism_analysis.xlsx"));
