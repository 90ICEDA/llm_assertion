import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "trace_overfit_data");
const outputPath = path.join(root, "outputs", threadId, "trace_overfit_report.xlsx");

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

function classFill(value) {
  const map = {
    literal_overfit: "#FCE4D6",
    structural_overfit: "#E2F0D9",
    vacuous_overfit: "#FFF2CC",
    not_flagged: "#F4F4F4",
  };
  return map[String(value ?? "").trim()] || null;
}

function boolFill(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "true") return "#D9EAD3";
  if (normalized === "false") return "#F4F4F4";
  return null;
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
    if (width && width > 30) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 30;
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

  if (opts.centerHeaders?.length) {
    for (const header of opts.centerHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        sheet.getRange(`${colLetter}2:${colLetter}${rowCount}`).format.horizontalAlignment =
          "Center";
      }
    }
  }

  if (opts.classHeaders?.length) {
    for (const header of opts.classHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const color = classFill(matrix[r - 1][idx]);
          if (color) {
            sheet.getRange(`${colLetter}${r}`).format.fill = color;
          }
        }
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
          if (color) {
            sheet.getRange(`${colLetter}${r}`).format.fill = color;
          }
        }
      }
    }
  }
}

function addReadmeSheet(workbook, title, bullets) {
  const sheet = workbook.worksheets.add("README");
  sheet.showGridLines = false;
  const rows = [["artifact", title], ...bullets.map((text, idx) => [`note_${idx + 1}`, text])];
  sheet.getRange(`A1:B${rows.length}`).values = rows;
  sheet.getRange("A1:B1").format = {
    fill: "#D9EAD3",
    font: { bold: true },
    borders: { preset: "all", style: "thin", color: "#B7C9A8" },
  };
  sheet.getRange(`A2:B${rows.length}`).format.borders = {
    preset: "all",
    style: "thin",
    color: "#E6E6E6",
  };
  sheet.getRange(`A1:B${rows.length}`).format.autofitColumns();
  sheet.getRange(`A1:B${rows.length}`).format.autofitRows();
}

async function main() {
  const methodSummary = await readCsv(path.join(dataDir, "trace_overfit_method_summary.csv"));
  const classSummary = await readCsv(path.join(dataDir, "trace_overfit_class_summary.csv"));
  const patternSummary = await readCsv(path.join(dataDir, "trace_overfit_literal_pattern_summary.csv"));
  const exampleIndex = await readCsv(path.join(dataDir, "trace_overfit_example_index.csv"));
  const fullTable = await readCsv(path.join(dataDir, "trace_overfit_assertion_table.csv"));

  const wb = Workbook.create();

  const s1 = wb.worksheets.add("Method_Summary");
  applyBaseSheetStyle(s1, toMatrix(methodSummary.headers, methodSummary.rows), {
    widths: { method: 22, method_label: 28 },
    centerHeaders: methodSummary.headers.filter((h) => !["method", "method_label"].includes(h)),
  });

  const s2 = wb.worksheets.add("Class_Summary");
  applyBaseSheetStyle(s2, toMatrix(classSummary.headers, classSummary.rows), {
    widths: { method: 22, method_label: 28, overfit_class: 18 },
    centerHeaders: classSummary.headers.filter(
      (h) => !["method", "method_label", "overfit_class"].includes(h),
    ),
    classHeaders: ["overfit_class"],
  });

  const s3 = wb.worksheets.add("Literal_Patterns");
  applyBaseSheetStyle(s3, toMatrix(patternSummary.headers, patternSummary.rows), {
    widths: { overfit_class: 18, method: 22, method_label: 28 },
    centerHeaders: patternSummary.headers.filter(
      (h) => !["overfit_class", "method", "method_label"].includes(h),
    ),
    classHeaders: ["overfit_class"],
  });

  const s4 = wb.worksheets.add("Example_Index");
  applyBaseSheetStyle(s4, toMatrix(exampleIndex.headers, exampleIndex.rows), {
    freezeCols: 6,
    widths: {
      case_id: 34,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      assertion_text: 42,
      overfit_basis: 24,
      overfit_reason: 42,
      failure_reason: 32,
    },
    classHeaders: ["overfit_class"],
    booleanHeaders: [
      "seen_plausible",
      "seen_success_strict",
      "heldout_success_strict",
      "trace_overfit",
      "literal_hardcoding",
      "specific_address_value",
      "specific_counter_value",
      "specific_state_encoding",
      "specific_fifo_depth",
      "specific_onehot_encoding",
      "specific_cycle_number",
      "seen_only_constant",
      "explicit_literal_evidence",
    ],
  });

  const s5 = wb.worksheets.add("Assertion_Report");
  applyBaseSheetStyle(s5, toMatrix(fullTable.headers, fullTable.rows), {
    freezeCols: 8,
    widths: {
      case_id: 34,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      assertion_text: 44,
      normalized_assertion: 44,
      antecedent_text: 32,
      consequent_text: 32,
      constant_tokens: 22,
      overfit_basis: 24,
      overfit_reason: 44,
      failure_reason: 32,
    },
    classHeaders: ["overfit_class"],
    booleanHeaders: [
      "compile_ok",
      "analysis_supported",
      "template_supported",
      "correct_pass",
      "fail_on_buggy",
      "heldout_correct_pass",
      "heldout_buggy_fail",
      "heldout_antecedent_hit",
      "seen_plausible",
      "seen_success_strict",
      "heldout_success_strict",
      "trace_overfit",
      "literal_hardcoding",
      "specific_address_value",
      "specific_counter_value",
      "specific_state_encoding",
      "specific_fifo_depth",
      "specific_onehot_encoding",
      "specific_cycle_number",
      "seen_only_constant",
      "explicit_literal_evidence",
    ],
  });

  addReadmeSheet(wb, "trace_overfit_report", [
    "对象仅包含 raw trace 与 trace summary 两种方法的 clean assertions。",
    "report 同时保留 seen_success_strict（correct_pass=1 且 fail_on_buggy=1）与更宽的 seen_plausible（correct_pass=1）标记。",
    "vacuous_overfit：seen_plausible 但 held-out antecedent 不触发。",
    "literal_overfit：存在显式常数/seen-trace 字面量证据，且 held-out 上失效。",
    "structural_overfit：没有明显字面量硬编码，但 held-out 上暴露出局部结构适配问题。",
  ]);

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const out = await SpreadsheetFile.exportXlsx(wb);
  await out.save(outputPath);
  console.log(outputPath);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
