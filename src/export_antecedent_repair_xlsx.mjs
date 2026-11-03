import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "antecedent_repair_data");
const outputDir = path.join(root, "outputs", threadId);

function splitCsvLine(line) {
  const out = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      out.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  out.push(current);
  return out;
}

async function readCsv(csvPath) {
  const text = await fs.readFile(csvPath, "utf8");
  const lines = text.trim().split(/\r?\n/);
  const headers = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const vals = splitCsvLine(line);
    return Object.fromEntries(headers.map((h, i) => [h, vals[i] ?? ""]));
  });
  return { headers, rows };
}

function toMatrix(headers, rows) {
  return [headers, ...rows.map((r) => headers.map((h) => r[h] ?? ""))];
}

function numberToColumn(num) {
  let n = num;
  let col = "";
  while (n > 0) {
    const rem = (n - 1) % 26;
    col = String.fromCharCode(65 + rem) + col;
    n = Math.floor((n - 1) / 26);
  }
  return col || "A";
}

function applyBaseSheetStyle(sheet, matrix, opts = {}) {
  const rowCount = matrix.length;
  const colCount = matrix[0]?.length ?? 1;
  const lastCol = numberToColumn(colCount);
  sheet.showGridLines = false;
  sheet.getRange(`A1:${lastCol}${rowCount}`).values = matrix;
  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    horizontalAlignment: "Center",
    verticalAlignment: "Center",
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
  sheet.getRange(`A2:${lastCol}${rowCount}`).format = {
    verticalAlignment: "Top",
    borders: { preset: "all", style: "thin", color: "#E6E6E6" },
  };
  sheet.freezePanes.freezeRows(1);
  if (opts.freezeCols) {
    sheet.freezePanes.freezeColumns(opts.freezeCols);
  }
  sheet.getRange(`A1:${lastCol}${rowCount}`).format.autofitColumns();
  sheet.getRange(`A1:${lastCol}${rowCount}`).format.autofitRows();
  for (let c = 1; c <= colCount; c++) {
    const colLetter = numberToColumn(c);
    const width = sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth;
    if (width && width > 28) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 28;
    }
  }
  if (opts.widths) {
    for (const [header, width] of Object.entries(opts.widths)) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = width;
      }
    }
  }
}

function tintBooleanColumn(sheet, matrix, header, yesColor, noColor) {
  const colIdx = matrix[0].indexOf(header);
  if (colIdx < 0) return;
  const colLetter = numberToColumn(colIdx + 1);
  for (let r = 2; r <= matrix.length; r++) {
    const val = String(matrix[r - 1][colIdx] ?? "").toLowerCase();
    if (val === "true") {
      sheet.getRange(`${colLetter}${r}`).format.fill = yesColor;
    } else if (val === "false") {
      sheet.getRange(`${colLetter}${r}`).format.fill = noColor;
    }
  }
}

async function buildCasesWorkbook() {
  const workbook = Workbook.create();
  const summary = await readCsv(path.join(dataDir, "antecedent_repair_aggregate_summary.csv"));
  const cases = await readCsv(path.join(dataDir, "antecedent_repair_case_summary.csv"));
  const selected = await readCsv(path.join(dataDir, "antecedent_repair_selected_cases.csv"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "antecedent_repair_cases"],
    ["description", "Selected antecedent_not_triggered cases and trigger-diagnosis metadata."],
    ["sheet", "aggregate_summary"],
    ["sheet", "case_summary"],
    ["sheet", "selected_case_meta"],
  ], { freezeCols: 1, widths: { artifact: 18, description: 52, sheet: 28 } });

  const summarySheet = workbook.worksheets.add("aggregate_summary");
  applyBaseSheetStyle(summarySheet, toMatrix(summary.headers, summary.rows), {
    widths: { metric: 34, value: 14 },
  });

  const caseSheet = workbook.worksheets.add("case_summary");
  const caseMatrix = toMatrix(cases.headers, cases.rows);
  applyBaseSheetStyle(caseSheet, caseMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selection_reason: 28,
      trigger_condition_summary: 36,
      antecedent_failure_diagnosis: 30,
      original_assertion: 42,
      best_repaired_assertion: 42,
    },
  });
  [
    "original_correct_pass",
    "repaired_correct_pass",
    "correct_pass_preserved",
    "fail_on_buggy_improved",
    "antecedent_hit_improved",
    "false_positive_introduced",
    "heldout_failure_introduced",
  ].forEach((header) => tintBooleanColumn(caseSheet, caseMatrix, header, "#D9EAD3", "#F4CCCC"));

  const selectedSheet = workbook.worksheets.add("selected_case_meta");
  applyBaseSheetStyle(selectedSheet, toMatrix(selected.headers, selected.rows), {
    freezeCols: 1,
    widths: {
      case_id: 34,
      selection_reason: 30,
      trigger_condition_summary: 40,
      antecedent_failure_diagnosis: 32,
    },
  });

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "antecedent_repair_cases.xlsx"));
}

async function buildResultsWorkbook() {
  const workbook = Workbook.create();
  const summary = await readCsv(path.join(dataDir, "antecedent_repair_aggregate_summary.csv"));
  const caseSummary = await readCsv(path.join(dataDir, "antecedent_repair_case_summary.csv"));
  const candidates = await readCsv(path.join(dataDir, "antecedent_repair_candidate_results.csv"));
  const aggressive = await readCsv(path.join(dataDir, "antecedent_repair_aggressive_candidates.csv"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "antecedent_repair_results"],
    ["description", "Original vs antecedent-repaired evaluation and candidate-level outcomes."],
    ["sheet", "aggregate_summary"],
    ["sheet", "case_summary"],
    ["sheet", "candidate_results"],
    ["sheet", "aggressive_candidates"],
  ], { freezeCols: 1, widths: { artifact: 18, description: 52, sheet: 28 } });

  const sumSheet = workbook.worksheets.add("aggregate_summary");
  applyBaseSheetStyle(sumSheet, toMatrix(summary.headers, summary.rows), {
    widths: { metric: 36, value: 14 },
  });

  const caseSheet = workbook.worksheets.add("case_summary");
  const caseMatrix = toMatrix(caseSummary.headers, caseSummary.rows);
  applyBaseSheetStyle(caseSheet, caseMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      original_assertion: 40,
      best_repaired_assertion: 40,
      trigger_condition_summary: 34,
    },
  });
  [
    "original_correct_pass",
    "repaired_correct_pass",
    "correct_pass_preserved",
    "fail_on_buggy_improved",
    "antecedent_hit_improved",
    "false_positive_introduced",
    "heldout_failure_introduced",
  ].forEach((header) => tintBooleanColumn(caseSheet, caseMatrix, header, "#D9EAD3", "#F4CCCC"));

  const candSheet = workbook.worksheets.add("candidate_results");
  const candMatrix = toMatrix(candidates.headers, candidates.rows);
  applyBaseSheetStyle(candSheet, candMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      original_assertion: 36,
      repaired_antecedent: 32,
      repaired_assertion: 40,
      trigger_condition_summary: 34,
      antecedent_failure_diagnosis: 30,
    },
  });
  [
    "compile_ok",
    "correct_pass",
    "fail_on_buggy",
    "antecedent_hit",
    "heldout_correct_pass",
    "heldout_buggy_fail",
    "correct_pass_preserved",
    "fail_on_buggy_improved",
    "antecedent_hit_improved",
    "false_positive_introduced",
    "heldout_failure_introduced",
  ].forEach((header) => tintBooleanColumn(candSheet, candMatrix, header, "#D9EAD3", "#F4CCCC"));

  const aggSheet = workbook.worksheets.add("aggressive_candidates");
  const aggMatrix = toMatrix(aggressive.headers, aggressive.rows);
  applyBaseSheetStyle(aggSheet, aggMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      repaired_antecedent: 32,
    },
  });
  [
    "compile_ok",
    "correct_pass",
    "fail_on_buggy",
    "antecedent_hit",
    "heldout_correct_pass",
    "heldout_buggy_fail",
    "false_positive_introduced",
    "heldout_failure_introduced",
  ].forEach((header) => tintBooleanColumn(aggSheet, aggMatrix, header, "#D9EAD3", "#F4CCCC"));

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "antecedent_repair_results.xlsx"));
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  await buildCasesWorkbook();
  await buildResultsWorkbook();
  console.log(path.join(outputDir, "antecedent_repair_cases.xlsx"));
  console.log(path.join(outputDir, "antecedent_repair_results.xlsx"));
}

await main();
