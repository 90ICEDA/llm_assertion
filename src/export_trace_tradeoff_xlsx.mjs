import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "trace_tradeoff_data");
const outputDir = path.join(root, "outputs", threadId);

const files = {
  byMetric: path.join(outputDir, "trace_tradeoff_by_metric.xlsx"),
  byBugClass: path.join(outputDir, "trace_tradeoff_by_bug_class.xlsx"),
};

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

function deltaFill(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return null;
  if (num > 0) return "#E2F0D9";
  if (num < 0) return "#FCE4D6";
  return "#F4F4F4";
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

  if (opts.deltaHeaders?.length) {
    for (const header of opts.deltaHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const color = deltaFill(matrix[r - 1][idx]);
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
  const matrix = rows;
  sheet.getRange(`A1:B${rows.length}`).values = matrix;
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

async function buildMetricWorkbook() {
  const overall = await readCsv(path.join(dataDir, "tradeoff_overall_metric_delta.csv"));
  const byMethod = await readCsv(path.join(dataDir, "tradeoff_overall_by_method.csv"));
  const byCase = await readCsv(path.join(dataDir, "tradeoff_case_delta.csv"));

  const wb = Workbook.create();

  const s1 = wb.worksheets.add("Overall_Delta");
  applyBaseSheetStyle(s1, toMatrix(overall.headers, overall.rows), {
    widths: {
      metric: 18,
      spec_only_count: 14,
      spec_plus_rtl_count: 16,
      spec_rtl_raw_trace_count: 20,
      spec_rtl_trace_summary_count: 24,
      delta_summary_minus_spec_plus_rtl: 22,
      delta_summary_minus_raw_trace: 20,
    },
    centerHeaders: overall.headers.filter((h) => h !== "metric"),
    deltaHeaders: ["delta_summary_minus_spec_plus_rtl", "delta_summary_minus_raw_trace"],
  });

  const s2 = wb.worksheets.add("Overall_By_Method");
  applyBaseSheetStyle(s2, toMatrix(byMethod.headers, byMethod.rows), {
    widths: {
      method: 22,
      method_label: 28,
    },
    centerHeaders: [
      "correct_pass",
      "fail_on_buggy",
      "antecedent_hit_buggy",
      "non_vacuous_buggy",
      "heldout_success",
      "trace_overfit",
      "literal_hardcoding",
    ],
  });

  const caseHeaders = [
    "case_id",
    "bug_class",
    "delta_correct_pass_vs_spec_plus_rtl",
    "delta_fail_on_buggy_vs_spec_plus_rtl",
    "delta_antecedent_hit_vs_spec_plus_rtl",
    "delta_non_vacuous_vs_spec_plus_rtl",
    "delta_heldout_success_vs_spec_plus_rtl",
    "delta_trace_overfit_vs_spec_plus_rtl",
    "summary_helped_bug_detection_but_hurt_correct",
    "summary_helped_correct_but_hurt_bug_detection",
    "summary_lost_useful_info_vs_spec_plus_rtl",
  ];
  const caseRows = byCase.rows.map((r) =>
    Object.fromEntries(caseHeaders.map((h) => [h, r[h] ?? ""]))
  );
  const s3 = wb.worksheets.add("Case_Signals");
  applyBaseSheetStyle(s3, toMatrix(caseHeaders, caseRows), {
    freezeCols: 2,
    widths: { case_id: 34, bug_class: 24 },
    centerHeaders: caseHeaders.filter((h) => !["case_id", "bug_class"].includes(h)),
    deltaHeaders: caseHeaders.filter((h) => h.startsWith("delta_")),
    booleanHeaders: [
      "summary_helped_bug_detection_but_hurt_correct",
      "summary_helped_correct_but_hurt_bug_detection",
      "summary_lost_useful_info_vs_spec_plus_rtl",
    ],
  });

  addReadmeSheet(wb, "trace_tradeoff_by_metric", [
    "对比主线是 spec + RTL 与 spec + RTL + trace summary。",
    "antecedent_hit 使用 antecedent_hit_buggy；non_vacuous 使用 non_vacuous_buggy。",
    "heldout_success 定义为 heldout_correct_pass=1 且 heldout_buggy_fail=1。",
    "Case_Signals 用于快速定位“提升 bug 检测但伤 correct”或“摘要丢失有用信息”的 case。",
  ]);

  return wb;
}

async function buildBugClassWorkbook() {
  const byMetric = await readCsv(path.join(dataDir, "tradeoff_by_bug_class_metric_delta.csv"));
  const byMethod = await readCsv(path.join(dataDir, "tradeoff_by_bug_class_method.csv"));
  const signals = await readCsv(path.join(dataDir, "tradeoff_bug_class_signals.csv"));
  const contributors = await readCsv(path.join(dataDir, "tradeoff_case_contributors.csv"));

  const wb = Workbook.create();

  const s1 = wb.worksheets.add("BugClass_Delta");
  applyBaseSheetStyle(s1, toMatrix(byMetric.headers, byMetric.rows), {
    widths: { bug_class: 24, metric: 18 },
    centerHeaders: byMetric.headers.filter((h) => !["bug_class", "metric"].includes(h)),
    deltaHeaders: ["delta_summary_minus_spec_plus_rtl", "delta_summary_minus_raw_trace"],
  });

  const s2 = wb.worksheets.add("BugClass_By_Method");
  applyBaseSheetStyle(s2, toMatrix(byMethod.headers, byMethod.rows), {
    widths: { bug_class: 24, method: 22, method_label: 28 },
    centerHeaders: [
      "correct_pass",
      "fail_on_buggy",
      "antecedent_hit_buggy",
      "non_vacuous_buggy",
      "heldout_success",
      "trace_overfit",
      "literal_hardcoding",
    ],
  });

  const s3 = wb.worksheets.add("Signal_Flags");
  applyBaseSheetStyle(s3, toMatrix(signals.headers, signals.rows), {
    widths: { bug_class: 24 },
    centerHeaders: signals.headers.filter((h) => h !== "bug_class"),
    deltaHeaders: [
      "correct_pass_delta",
      "fail_on_buggy_delta",
      "antecedent_hit_delta",
      "non_vacuous_delta",
      "heldout_success_delta",
      "trace_overfit_delta",
    ],
    booleanHeaders: [
      "correct_up_fail_down",
      "fail_up_correct_down",
      "trace_summary_more_conservative",
      "trace_summary_more_aggressive",
    ],
  });

  const s4 = wb.worksheets.add("Case_Contributors");
  applyBaseSheetStyle(s4, toMatrix(contributors.headers, contributors.rows), {
    widths: { bug_class: 24, metric: 18, direction: 12, case_id: 34 },
    centerHeaders: ["delta"],
    deltaHeaders: ["delta"],
  });

  addReadmeSheet(wb, "trace_tradeoff_by_bug_class", [
    "BugClass_Delta 给出 trace summary 相对 spec + RTL 的分项差值，也保留了相对 raw trace 的差值。",
    "Signal_Flags 直接标出“correct_pass 上升但 fail_on_buggy 下降”与其反向模式。",
    "Case_Contributors 列出每个 bug_class / metric 下推动增减的具体 case。",
  ]);

  return wb;
}

async function saveWorkbook(workbook, outPath) {
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outPath);
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const metricWb = await buildMetricWorkbook();
  await saveWorkbook(metricWb, files.byMetric);

  const bugClassWb = await buildBugClassWorkbook();
  await saveWorkbook(bugClassWb, files.byBugClass);

  console.log(files.byMetric);
  console.log(files.byBugClass);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
