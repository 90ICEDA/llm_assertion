import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "temporal_type_analysis_data");
const outputPath = path.join(root, "outputs", threadId, "temporal_type_analysis.xlsx");

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

  if (opts.percentHeaders?.length) {
    for (const header of opts.percentHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        sheet.getRange(`${colLetter}2:${colLetter}${rowCount}`).numberFormat = "0.0%";
      }
    }
  }
}

function addReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("README");
  sheet.showGridLines = false;
  const rows = [
    ["artifact", "temporal_type_analysis"],
    ["note_1", "temporal_type 按 case 级人工映射分桶，避免同一设计意图在不同 prompt 下被误判。"],
    ["note_2", "antecedent_hit 使用 antecedent_hit_buggy。"],
    ["note_3", "vacuity 定义为 antecedent_hit_buggy=0；vacuous_fail 进一步要求 fail_on_buggy=0。"],
    ["note_4", "heldout_success 定义为 heldout_correct_pass=1 且 heldout_buggy_fail=1。"],
    ["note_5", "robust_success 额外要求 compile_ok/correct_pass/fail_on_buggy/antecedent_hit/heldout_success 全部满足，且没有 trace_overfit。"],
  ];
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
  sheet.getRange("A:A").format.columnWidth = 16;
  sheet.getRange("B:B").format.columnWidth = 80;
}

async function buildWorkbook() {
  const overall = await readCsv(path.join(dataDir, "temporal_type_overall.csv"));
  const byMethod = await readCsv(path.join(dataDir, "temporal_type_by_method.csv"));
  const byCaseMethod = await readCsv(path.join(dataDir, "temporal_type_case_method.csv"));
  const failureBreakdown = await readCsv(path.join(dataDir, "temporal_type_failure_breakdown.csv"));
  const examples = await readCsv(path.join(dataDir, "temporal_type_examples.csv"));

  const wb = Workbook.create();

  const percentHeaders = [
    "compile_ok_rate",
    "correct_pass_rate",
    "fail_on_buggy_rate",
    "antecedent_hit_rate",
    "vacuity_rate",
    "vacuous_fail_rate",
    "heldout_success_rate",
    "trace_overfit_rate",
    "robust_success_rate",
    "share_within_temporal_type_failure",
  ];

  const s1 = wb.worksheets.add("Overall_By_Type");
  applyBaseSheetStyle(s1, toMatrix(overall.headers, overall.rows), {
    freezeCols: 1,
    widths: {
      temporal_type: 20,
      case_count: 10,
      assertion_count: 12,
    },
    centerHeaders: overall.headers.filter((h) => h !== "temporal_type"),
    percentHeaders,
  });

  const s2 = wb.worksheets.add("By_Type_Method");
  applyBaseSheetStyle(s2, toMatrix(byMethod.headers, byMethod.rows), {
    freezeCols: 3,
    widths: {
      temporal_type: 20,
      method: 24,
      method_label: 28,
    },
    centerHeaders: byMethod.headers.filter((h) => !["temporal_type", "method", "method_label"].includes(h)),
    percentHeaders,
  });

  const caseHeaders = [
    "temporal_type",
    "case_id",
    "module",
    "bug_name",
    "bug_class",
    "method_label",
    "assertion_count",
    "compile_ok_rate",
    "correct_pass_rate",
    "fail_on_buggy_rate",
    "antecedent_hit_rate",
    "vacuity_rate",
    "heldout_success_rate",
    "trace_overfit_rate",
    "robust_success_count",
  ];
  const caseRows = byCaseMethod.rows.map((r) =>
    Object.fromEntries(caseHeaders.map((h) => [h, r[h] ?? ""]))
  );
  const s3 = wb.worksheets.add("Case_Method_View");
  applyBaseSheetStyle(s3, toMatrix(caseHeaders, caseRows), {
    freezeCols: 6,
    widths: {
      temporal_type: 20,
      case_id: 34,
      module: 18,
      bug_name: 28,
      bug_class: 22,
      method_label: 26,
    },
    centerHeaders: caseHeaders.filter((h) => !["temporal_type", "case_id", "module", "bug_name", "bug_class", "method_label"].includes(h)),
    percentHeaders,
  });

  const s4 = wb.worksheets.add("Failure_Breakdown");
  applyBaseSheetStyle(s4, toMatrix(failureBreakdown.headers, failureBreakdown.rows), {
    freezeCols: 2,
    widths: {
      temporal_type: 20,
      failure_type: 28,
      assertion_count: 12,
      share_within_temporal_type_failure: 22,
    },
    centerHeaders: ["assertion_count", "share_within_temporal_type_failure"],
    percentHeaders,
  });

  const exampleHeaders = [
    "temporal_type",
    "case_id",
    "method_label",
    "failure_type",
    "compile_ok",
    "correct_pass",
    "fail_on_buggy",
    "antecedent_hit",
    "vacuity",
    "heldout_success",
    "trace_overfit",
    "literal_hardcoding",
    "assertion_text",
    "failure_reason",
    "example_note",
  ];
  const exampleRows = examples.rows.map((r) =>
    Object.fromEntries(exampleHeaders.map((h) => [h, r[h] ?? ""]))
  );
  const s5 = wb.worksheets.add("Representative_Failures");
  applyBaseSheetStyle(s5, toMatrix(exampleHeaders, exampleRows), {
    freezeCols: 4,
    widths: {
      temporal_type: 20,
      case_id: 34,
      method_label: 26,
      failure_type: 24,
      assertion_text: 70,
      failure_reason: 50,
      example_note: 90,
    },
    centerHeaders: [
      "compile_ok",
      "correct_pass",
      "fail_on_buggy",
      "antecedent_hit",
      "vacuity",
      "heldout_success",
      "trace_overfit",
      "literal_hardcoding",
    ],
  });

  addReadmeSheet(wb);

  const artifact = await SpreadsheetFile.exportXlsx(wb);
  await artifact.save(outputPath);
  console.log(outputPath);
}

buildWorkbook().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
