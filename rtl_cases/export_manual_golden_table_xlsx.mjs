import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const rootDir = __dirname;
const manifestPath = path.join(rootDir, "case_manifest.json");
const outputPath = path.join(rootDir, "MANUAL_GOLDEN_SVA_TABLE.xlsx");

const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const cases = manifest.cases || [];

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("Manual Golden SVA");
sheet.showGridLines = false;

const headers = [
  "Case",
  "Bug Type",
  "Golden SVA",
  "Expected Behavior",
  "First Divergence Cycle",
  "Relevant Signals",
  "Temporal Type",
];

const rows = cases.map((item) => {
  const golden = item.golden_sva || {};
  return [
    item.name || "",
    item.bug_type || "",
    golden.sva || "",
    golden.expected_behavior || "",
    golden.first_divergence_cycle ?? "",
    Array.isArray(golden.relevant_signals) ? golden.relevant_signals.join(", ") : "",
    golden.temporal_type || "",
  ];
});

sheet.getRange(`A1:G${rows.length + 1}`).values = [headers, ...rows];

sheet.getRange("A1:G1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  horizontalAlignment: "Center",
  verticalAlignment: "Center",
  borders: { preset: "all", style: "thin", color: "#D9E2F3" },
};

sheet.getRange(`A2:G${rows.length + 1}`).format = {
  wrapText: true,
  verticalAlignment: "Top",
  borders: { preset: "all", style: "thin", color: "#D9D9D9" },
};

sheet.getRange(`E2:E${rows.length + 1}`).format = {
  horizontalAlignment: "Center",
  verticalAlignment: "Top",
  borders: { preset: "all", style: "thin", color: "#D9D9D9" },
};

sheet.getRange("A:A").format.columnWidthPx = 180;
sheet.getRange("B:B").format.columnWidthPx = 180;
sheet.getRange("C:C").format.columnWidthPx = 600;
sheet.getRange("D:D").format.columnWidthPx = 520;
sheet.getRange("E:E").format.columnWidthPx = 140;
sheet.getRange("F:F").format.columnWidthPx = 220;
sheet.getRange("G:G").format.columnWidthPx = 340;
sheet.getRange("1:1").format.rowHeightPx = 28;

sheet.freezePanes.freezeRows(1);

const table = sheet.tables.add(`A1:G${rows.length + 1}`, true, "ManualGoldenSVATable");
table.style = "TableStyleMedium2";

const inspect = await workbook.inspect({
  kind: "table",
  range: `Manual Golden SVA!A1:G${Math.min(rows.length + 1, 6)}`,
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 7,
  maxChars: 5000,
});
console.log(inspect.ndjson);

await workbook.render({
  sheetName: "Manual Golden SVA",
  range: `A1:G${Math.min(rows.length + 1, 8)}`,
  scale: 1,
  format: "png",
});

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log(`[DONE] Wrote ${outputPath}`);
