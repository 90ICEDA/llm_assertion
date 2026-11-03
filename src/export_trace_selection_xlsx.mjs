import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "trace_selection_data");
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
    wrapText: true,
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

async function buildQualityWorkbook() {
  const workbook = Workbook.create();
  const selectedCases = JSON.parse(await fs.readFile(path.join(dataDir, "selected_cases.json"), "utf8"));
  const scored = await readCsv(path.join(dataDir, "trace_quality_scored_windows.csv"));
  const selected = await readCsv(path.join(dataDir, "trace_quality_selected_windows.csv"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "trace_quality_scored_table"],
    ["description", "All scored trace windows plus the selected high-quality and low-quality snippets."],
    ["sheet", "case_meta"],
    ["sheet", "selected_windows"],
    ["sheet", "scored_windows"],
  ], { freezeCols: 1, widths: { artifact: 18, description: 58, sheet: 26 } });

  const metaSheet = workbook.worksheets.add("case_meta");
  const metaHeaders = ["case_id", "bug_class", "temporal_kind", "selection_reason", "literal_lure_signals"];
  const metaRows = selectedCases.map((row) => ({
    ...row,
    literal_lure_signals: Array.isArray(row.literal_lure_signals) ? row.literal_lure_signals.join(", ") : "",
  }));
  applyBaseSheetStyle(metaSheet, toMatrix(metaHeaders, metaRows), {
    freezeCols: 1,
    widths: { case_id: 34, selection_reason: 50, literal_lure_signals: 26 },
  });

  const selectedSheet = workbook.worksheets.add("selected_windows");
  const selectedMatrix = toMatrix(selected.headers, selected.rows);
  applyBaseSheetStyle(selectedSheet, selectedMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selected_trace_quality: 18,
      selection_reason: 40,
      selection_notes: 44,
      selected_trace_text: 56,
      prompt_path: 44,
    },
  });

  const scoredSheet = workbook.worksheets.add("scored_windows");
  const scoredMatrix = toMatrix(scored.headers, scored.rows);
  applyBaseSheetStyle(scoredSheet, scoredMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selection_notes: 42,
      selected_trace_text: 56,
    },
  });
}

async function finalizeQualityWorkbook() {
  const workbook = Workbook.create();
  const selectedCases = JSON.parse(await fs.readFile(path.join(dataDir, "selected_cases.json"), "utf8"));
  const scored = await readCsv(path.join(dataDir, "trace_quality_scored_windows.csv"));
  const selected = await readCsv(path.join(dataDir, "trace_quality_selected_windows.csv"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "trace_quality_scored_table"],
    ["description", "All scored trace windows plus the selected high-quality and low-quality snippets."],
    ["sheet", "case_meta"],
    ["sheet", "selected_windows"],
    ["sheet", "scored_windows"],
  ], { freezeCols: 1, widths: { artifact: 18, description: 58, sheet: 26 } });

  const metaSheet = workbook.worksheets.add("case_meta");
  const metaHeaders = ["case_id", "bug_class", "temporal_kind", "selection_reason", "literal_lure_signals"];
  const metaRows = selectedCases.map((row) => ({
    ...row,
    literal_lure_signals: Array.isArray(row.literal_lure_signals) ? row.literal_lure_signals.join(", ") : "",
  }));
  applyBaseSheetStyle(metaSheet, toMatrix(metaHeaders, metaRows), {
    freezeCols: 1,
    widths: { case_id: 34, selection_reason: 50, literal_lure_signals: 26 },
  });

  const selectedSheet = workbook.worksheets.add("selected_windows");
  const selectedMatrix = toMatrix(selected.headers, selected.rows);
  applyBaseSheetStyle(selectedSheet, selectedMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selected_trace_quality: 18,
      selection_reason: 40,
      selection_notes: 44,
      selected_trace_text: 56,
      prompt_path: 44,
    },
  });

  const scoredSheet = workbook.worksheets.add("scored_windows");
  const scoredMatrix = toMatrix(scored.headers, scored.rows);
  applyBaseSheetStyle(scoredSheet, scoredMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selection_notes: 42,
      selected_trace_text: 56,
    },
  });

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "trace_quality_scored_table.xlsx"));
}

async function buildResultsWorkbook() {
  const workbook = Workbook.create();
  const summary = await readCsv(path.join(dataDir, "high_vs_low_quality_trace_summary.csv"));
  const comparison = await readCsv(path.join(dataDir, "high_vs_low_quality_case_comparison.csv"));
  const selected = await readCsv(path.join(dataDir, "trace_quality_selected_windows.csv"));
  const candidates = await readCsv(path.join(dataDir, "high_vs_low_quality_trace_results_raw.csv"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "high_vs_low_quality_trace_results"],
    ["description", "Candidate-level and case-level comparison between high-quality and low-quality trace snippets."],
    ["sheet", "aggregate_summary"],
    ["sheet", "case_comparison"],
    ["sheet", "selected_windows"],
    ["sheet", "candidate_results"],
  ], { freezeCols: 1, widths: { artifact: 18, description: 60, sheet: 26 } });

  const sumSheet = workbook.worksheets.add("aggregate_summary");
  const sumMatrix = toMatrix(summary.headers, summary.rows);
  applyBaseSheetStyle(sumSheet, sumMatrix, {
    freezeCols: 2,
    widths: { case_id: 34, selected_trace_quality: 18 },
  });

  const compSheet = workbook.worksheets.add("case_comparison");
  const compMatrix = toMatrix(comparison.headers, comparison.rows);
  applyBaseSheetStyle(compSheet, compMatrix, {
    freezeCols: 1,
    widths: { case_id: 34 },
  });

  const selectedSheet = workbook.worksheets.add("selected_windows");
  const selectedMatrix = toMatrix(selected.headers, selected.rows);
  applyBaseSheetStyle(selectedSheet, selectedMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      selected_trace_quality: 18,
      selection_notes: 44,
      selected_trace_text: 56,
    },
  });

  const candSheet = workbook.worksheets.add("candidate_results");
  const candMatrix = toMatrix(candidates.headers, candidates.rows);
  applyBaseSheetStyle(candSheet, candMatrix, {
    freezeCols: 3,
    widths: {
      case_id: 34,
      selected_trace_quality: 18,
      assertion_text: 46,
      semantic_reason: 28,
      selected_trace_text: 56,
      selection_notes: 40,
    },
  });
  [
    "compile_ok",
    "correct_pass",
    "buggy_fail",
    "antecedent_hit",
    "non_vacuous",
    "heldout_correct_pass",
    "heldout_buggy_fail",
    "heldout_antecedent_hit",
    "trace_overfit",
    "semantic_reasonable",
  ].forEach((header) => tintBooleanColumn(candSheet, candMatrix, header, "#D9EAD3", "#F4CCCC"));

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "high_vs_low_quality_trace_results.xlsx"));
}

async function main() {
  await finalizeQualityWorkbook();
  await buildResultsWorkbook();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
