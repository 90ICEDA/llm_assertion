import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "trace_abstraction_data");
const outputDir = path.join(root, "outputs", threadId);
const outputFile = path.join(outputDir, "trace_abstraction_results.xlsx");

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

function boolFill(value) {
  const v = String(value ?? "").trim().toLowerCase();
  if (v === "true") return "#D9EAD3";
  if (v === "false") return "#FCE4D6";
  return null;
}

function variantFill(value) {
  const key = String(value ?? "").trim();
  const map = {
    raw_trace: "#FDEBD0",
    normal_trace_summary: "#E8F6F3",
    abstracted_trace_summary: "#EAF2F8",
  };
  return map[key] || null;
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
  if (opts.freezeCols) sheet.freezePanes.freezeColumns(opts.freezeCols);
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
  if (opts.booleanHeaders?.length) {
    for (const header of opts.booleanHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const color = boolFill(matrix[r - 1][idx]);
          if (color) sheet.getRange(`${colLetter}${r}`).format.fill = color;
        }
      }
    }
  }
  if (opts.variantHeaders?.length) {
    for (const header of opts.variantHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const color = variantFill(matrix[r - 1][idx]);
          if (color) sheet.getRange(`${colLetter}${r}`).format.fill = color;
        }
      }
    }
  }
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const results = await readCsv(path.join(dataDir, "trace_abstraction_results_raw.csv"));
  const prompts = await readCsv(path.join(dataDir, "trace_abstraction_prompts.csv"));
  const overall = await readCsv(path.join(dataDir, "trace_abstraction_summary.csv"));
  const selectedCases = JSON.parse(await fs.readFile(path.join(dataDir, "selected_cases.json"), "utf8"));

  const wb = Workbook.create();

  const readme = wb.worksheets.add("README");
  applyBaseSheetStyle(readme, [
    ["artifact", "trace_abstraction_results"],
    ["description", "8-case trace abstraction prototype with raw trace, normal summary, and abstracted summary variants."],
    ["sheet", "summary_overall"],
    ["sheet", "selected_cases"],
    ["sheet", "prompts"],
    ["sheet", "candidate_results"],
  ], { widths: { artifact: 20, description: 68, sheet: 28 } });

  const overallSheet = wb.worksheets.add("summary_overall");
  const overallMatrix = toMatrix(overall.headers, overall.rows);
  applyBaseSheetStyle(overallSheet, overallMatrix, {
    widths: { case_id: 34, prompt_variant: 24, selection_tags: 28, selection_reason: 36 },
    variantHeaders: ["prompt_variant"],
  });

  const selectedSheet = wb.worksheets.add("selected_cases");
  const selectedHeaders = Object.keys(selectedCases[0] ?? {});
  const selectedRows = selectedCases.map((row) => row);
  const selectedMatrix = toMatrix(selectedHeaders, selectedRows);
  applyBaseSheetStyle(selectedSheet, selectedMatrix, {
    freezeCols: 1,
    widths: {
      case_id: 34,
      selection_tags: 30,
      selection_reason: 40,
      spec: 42,
      raw_trace_input: 42,
      normal_trace_summary: 42,
      abstracted_trace_summary: 42,
    },
  });

  const promptsSheet = wb.worksheets.add("prompts");
  const promptsMatrix = toMatrix(prompts.headers, prompts.rows);
  applyBaseSheetStyle(promptsSheet, promptsMatrix, {
    freezeCols: 2,
    widths: {
      case_id: 34,
      prompt_variant: 24,
      selection_tags: 28,
      selection_reason: 36,
      spec: 36,
      trace_input_text: 42,
      full_prompt_path: 40,
    },
    variantHeaders: ["prompt_variant"],
  });

  const resultSheet = wb.worksheets.add("candidate_results");
  const resultMatrix = toMatrix(results.headers, results.rows);
  applyBaseSheetStyle(resultSheet, resultMatrix, {
    freezeCols: 3,
    widths: {
      case_id: 34,
      prompt_variant: 24,
      assertion_text: 44,
      semantic_reason: 32,
      raw_generation_responses: 44,
    },
    booleanHeaders: [
      "compile_ok",
      "correct_pass",
      "buggy_fail",
      "antecedent_hit",
      "non_vacuous",
      "heldout_correct_pass",
      "heldout_buggy_fail",
      "trace_overfit",
      "semantic_reasonable",
      "heldout_antecedent_hit",
      "heldout_non_vacuous",
      "use_property_compile_mode",
    ],
    variantHeaders: ["prompt_variant"],
  });

  const out = await SpreadsheetFile.exportXlsx(wb);
  await out.save(outputFile);
  console.log(outputFile);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
