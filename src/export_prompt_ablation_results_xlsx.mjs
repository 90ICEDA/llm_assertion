import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "prompt_ablation_data");
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

async function main() {
  const workbook = Workbook.create();
  const promptDesign = await readCsv(path.join(dataDir, "prompt_ablation_prompt_design.csv"));
  const promptSummary = await readCsv(path.join(dataDir, "prompt_ablation_summary_by_prompt.csv"));
  const casePrompt = await readCsv(path.join(dataDir, "prompt_ablation_case_prompt_summary.csv"));
  const candidates = await readCsv(path.join(dataDir, "prompt_ablation_results_raw.csv"));
  const runMeta = JSON.parse(await fs.readFile(path.join(dataDir, "prompt_ablation_run_meta.json"), "utf8"));

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "prompt_ablation_results"],
    ["description", "Prompt-ablation prototype on 8 abstracted-trace cases."],
    ["model_name", runMeta.model_name],
    ["candidates_per_prompt", String(runMeta.candidates_per_prompt)],
    ["sheet", "prompt_summary"],
    ["sheet", "case_prompt_summary"],
    ["sheet", "prompt_design"],
    ["sheet", "candidate_results"],
  ], { freezeCols: 1, widths: { artifact: 22, description: 52, sheet: 26 } });

  const sumSheet = workbook.worksheets.add("prompt_summary");
  const sumMatrix = toMatrix(promptSummary.headers, promptSummary.rows);
  applyBaseSheetStyle(sumSheet, sumMatrix, {
    freezeCols: 2,
    widths: {
      prompt_variant: 30,
      constraint_family: 18,
      constraint_focus: 40,
    },
  });

  const caseSheet = workbook.worksheets.add("case_prompt_summary");
  const caseMatrix = toMatrix(casePrompt.headers, casePrompt.rows);
  applyBaseSheetStyle(caseSheet, caseMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      prompt_variant: 30,
      best_assertion_text: 44,
    },
  });

  const designSheet = workbook.worksheets.add("prompt_design");
  const designMatrix = toMatrix(promptDesign.headers, promptDesign.rows);
  applyBaseSheetStyle(designSheet, designMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      prompt_variant: 30,
      constraint_focus: 38,
      selection_reason: 34,
      abstracted_trace_summary_original: 56,
      abstracted_trace_summary_sanitized: 56,
      extra_instruction: 44,
      prompt_path: 44,
    },
  });

  const candSheet = workbook.worksheets.add("candidate_results");
  const candMatrix = toMatrix(candidates.headers, candidates.rows);
  applyBaseSheetStyle(candSheet, candMatrix, {
    freezeCols: 3,
    widths: {
      case_id: 34,
      prompt_variant: 30,
      constraint_focus: 36,
      assertion_text: 46,
      semantic_reason: 28,
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
    "literal_hardcoding",
    "uses_temporal_feature",
    "strict_success",
    "heldout_success",
  ].forEach((header) => tintBooleanColumn(candSheet, candMatrix, header, "#D9EAD3", "#F4CCCC"));

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "prompt_ablation_results.xlsx"));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
