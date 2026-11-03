import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "vacuity_analysis_data");
const outputDir = path.join(root, "outputs", threadId);
const outputPath = path.join(outputDir, "vacuity_failure_table.xlsx");

const bucketColors = {
  vacuous_miss: "#FFF2CC",
  non_vacuous_miss: "#D9EAD3",
  too_weak: "#FCE5CD",
  trace_overfit: "#D9E2F3",
  semantic_wrong: "#F4CCCC",
  unsupported_analysis: "#EDEDED",
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

  if (opts.percentHeaders?.length) {
    for (const header of opts.percentHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const raw = matrix[r - 1][idx];
          if (raw !== "") {
            sheet.getRange(`${colLetter}${r}`).values = [[Number(raw)]];
          }
        }
        sheet.getRange(`${colLetter}2:${colLetter}${rowCount}`).format.numberFormat = "0.0%";
        sheet.getRange(`${colLetter}2:${colLetter}${rowCount}`).format.horizontalAlignment =
          "Right";
      }
    }
  }

  if (opts.bucketHeaders?.length) {
    for (const header of opts.bucketHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const val = String(matrix[r - 1][idx] ?? "");
          const color = bucketColors[val];
          if (color) {
            sheet.getRange(`${colLetter}${r}`).format.fill = color;
          }
        }
      }
    }
  }
}

function addReadmeSheet(workbook, summary) {
  const sheet = workbook.worksheets.add("README");
  sheet.showGridLines = false;
  const rows = [
    ["artifact", "vacuity_failure_table"],
    ["fail_assertion_count", String(summary.fail_assertion_count)],
    ["fail_case_count", String(summary.fail_case_count)],
    ["buggy_antecedent_zero_count", String(summary.buggy_antecedent_zero_count)],
    ["classification", "unsupported_analysis = compile/analysis不可用"],
    ["classification", "semantic_wrong = 语义不合理"],
    ["classification", "trace_overfit = seen trace literal / hardcoding"],
    ["classification", "vacuous_miss = buggy antecedent_hit = 0"],
    ["classification", "too_weak = antecedent_hit_buggy = 1 且 bug_not_detected_on_buggy"],
    ["classification", "non_vacuous_miss = 其他 antecedent_hit_buggy = 1 的 miss"],
    ["note", "correct_side_issue 单独保留 too_strong_on_correct，不和 buggy-side bucket 混在一起"],
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
}

function buildSummaryMatrix(summary, methodRows) {
  const bucketCounts = summary.paper_bucket_counts;
  const rows = [
    ["metric", "value"],
    ["fail_assertion_count", summary.fail_assertion_count],
    ["fail_case_count", summary.fail_case_count],
    ["buggy_antecedent_zero_count", summary.buggy_antecedent_zero_count],
    ["buggy_antecedent_zero_case_count", summary.buggy_antecedent_zero_case_count],
    ["", ""],
    ["paper_bucket", "count"],
    ["vacuous_miss", bucketCounts.vacuous_miss],
    ["non_vacuous_miss", bucketCounts.non_vacuous_miss],
    ["too_weak", bucketCounts.too_weak],
    ["trace_overfit", bucketCounts.trace_overfit],
    ["semantic_wrong", bucketCounts.semantic_wrong],
    ["unsupported_analysis", bucketCounts.unsupported_analysis],
    ["", ""],
    ["method", "vacuous_share"],
    ...methodRows.map((r) => [r.method_label, r.vacuous_share]),
  ];
  return rows;
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const summary = JSON.parse(await fs.readFile(path.join(dataDir, "vacuity_summary.json"), "utf8"));
  const methodSummary = await readCsv(path.join(dataDir, "vacuity_method_summary.csv"));
  const caseSummary = await readCsv(path.join(dataDir, "vacuity_case_summary.csv"));
  const failureRows = await readCsv(path.join(dataDir, "vacuity_failure_rows.csv"));
  const antecedentZero = await readCsv(path.join(dataDir, "antecedent_zero_summary.csv"));
  const repDiag = await readCsv(path.join(dataDir, "representative_failures_diagnostic_priority.csv"));
  const bucketCounts = await readCsv(path.join(dataDir, "vacuity_bucket_counts_by_method.csv"));

  const wb = Workbook.create();

  const s0 = wb.worksheets.add("Summary");
  const summaryMatrix = buildSummaryMatrix(summary, methodSummary.rows);
  applyBaseSheetStyle(s0, summaryMatrix, {
    widths: { metric: 30, value: 16 },
    bucketHeaders: [],
  });
  for (let r = 8; r <= 13; r++) {
    const bucket = String(summaryMatrix[r - 1][0] ?? "");
    const color = bucketColors[bucket];
    if (color) {
      s0.getRange(`A${r}:B${r}`).format.fill = color;
    }
  }
  for (let r = 16; r <= 19; r++) {
    s0.getRange(`B${r}`).values = [[Number(summaryMatrix[r - 1][1])]];
    s0.getRange(`B${r}`).format.numberFormat = "0.0%";
  }

  const s1 = wb.worksheets.add("Method_Summary");
  applyBaseSheetStyle(s1, toMatrix(methodSummary.headers, methodSummary.rows), {
    widths: { method_label: 28, vacuous_share: 12 },
    centerHeaders: [
      "fail_assertion_count",
      "vacuous_miss_count",
      "non_vacuous_miss_count",
      "too_weak_count",
      "trace_overfit_count",
      "semantic_wrong_count",
      "unsupported_analysis_count",
      "buggy_antecedent_zero_count",
      "fail_case_count",
    ],
    percentHeaders: ["vacuous_share"],
  });

  const s2 = wb.worksheets.add("Bucket_By_Method");
  applyBaseSheetStyle(s2, toMatrix(bucketCounts.headers, bucketCounts.rows), {
    widths: { method_label: 28, paper_bucket: 22 },
    centerHeaders: ["assertion_count"],
    bucketHeaders: ["paper_bucket"],
  });

  const s3 = wb.worksheets.add("Case_Summary");
  applyBaseSheetStyle(s3, toMatrix(caseSummary.headers, caseSummary.rows), {
    freezeCols: 4,
    widths: {
      case_id: 28,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      vacuous_share: 12,
    },
    centerHeaders: [
      "fail_assertion_count",
      "vacuous_miss_count",
      "non_vacuous_miss_count",
      "too_weak_count",
      "trace_overfit_count",
      "semantic_wrong_count",
      "unsupported_analysis_count",
      "buggy_antecedent_zero_count",
      "vacuous_dominant",
    ],
    percentHeaders: ["vacuous_share"],
  });

  const s4 = wb.worksheets.add("Failure_Rows");
  applyBaseSheetStyle(s4, toMatrix(failureRows.headers, failureRows.rows), {
    freezeCols: 6,
    widths: {
      case_id: 28,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      paper_bucket: 20,
      buggy_miss_detail: 24,
      correct_side_issue: 20,
      antecedent_text: 36,
      consequent_text: 28,
      assertion_text: 40,
      normalized_assertion: 40,
      failure_reason: 40,
      representative_explanation: 46,
    },
    centerHeaders: [
      "buggy_antecedent_zero",
      "compile_ok",
      "analysis_supported",
      "correct_pass",
      "fail_on_buggy",
      "antecedent_hit_correct",
      "antecedent_hit_buggy",
      "non_vacuous_correct",
      "non_vacuous_buggy",
      "trace_overfit",
      "literal_hardcoding",
    ],
    bucketHeaders: ["paper_bucket"],
  });

  const s5 = wb.worksheets.add("Antecedent_Zero");
  applyBaseSheetStyle(s5, toMatrix(antecedentZero.headers, antecedentZero.rows), {
    freezeCols: 3,
    widths: {
      case_id: 28,
      method_label: 28,
      example_antecedent: 34,
      example_assertion: 40,
    },
    centerHeaders: ["assertion_count"],
  });

  const s6 = wb.worksheets.add("Representative_Examples");
  applyBaseSheetStyle(s6, toMatrix(repDiag.headers, repDiag.rows), {
    freezeCols: 6,
    widths: {
      case_id: 28,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      paper_bucket: 20,
      buggy_miss_detail: 24,
      correct_side_issue: 20,
      antecedent_text: 34,
      consequent_text: 26,
      assertion_text: 40,
      failure_reason: 40,
      representative_explanation: 46,
    },
    bucketHeaders: ["paper_bucket"],
  });

  addReadmeSheet(wb, summary);

  const output = await SpreadsheetFile.exportXlsx(wb);
  await output.save(outputPath);

  const preview = await wb.render({
    sheetName: "Summary",
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(outputDir, "vacuity_failure_table_preview.png"),
    new Uint8Array(await preview.arrayBuffer()),
  );

  console.log(outputPath);
}

await main();
