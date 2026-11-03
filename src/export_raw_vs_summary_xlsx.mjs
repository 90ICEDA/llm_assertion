import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "raw_vs_summary_data");
const outputDir = path.join(root, "outputs", threadId);
const outputPath = path.join(outputDir, "raw_vs_summary.xlsx");

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
  const normalized = String(value ?? "").trim().toLowerCase();
  if (normalized === "true") return "#D9EAD3";
  if (normalized === "false") return "#F4F4F4";
  return null;
}

function deltaFill(value) {
  const num = Number(value);
  if (Number.isNaN(num)) return null;
  if (num > 0) return "#E2F0D9";
  if (num < 0) return "#FCE4D6";
  return "#F4F4F4";
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
    if (width && width > 32) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 32;
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

  if (opts.wrapHeaders?.length) {
    for (const header of opts.wrapHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        sheet.getRange(`${colLetter}2:${colLetter}${rowCount}`).format.wrapText = true;
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
}

function addReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("README");
  sheet.showGridLines = false;
  const rows = [
    ["artifact", "raw_vs_summary"],
    ["note_1", "只比较 spec + RTL + raw trace 与 spec + RTL + trace summary 两种方法。"],
    ["note_2", "overall_union 使用两个方法各自全部保留下来的 case；overlap_only 只保留两边都出现的 case。"],
    ["note_3", "heldout_success 定义为 heldout_correct_pass=1 且 heldout_buggy_fail=1。"],
    ["note_4", "summary_lost_temporal_info 表示 summary 的 antecedent_hit 或 fail_on_buggy 低于 raw。"],
    ["note_5", "case_conclusion 被强制压到四类：raw trace 更好 / trace summary 更好 / 两者都不好 / 两者表现相反。"],
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
  sheet.getRange("B:B").format.columnWidth = 82;
}

async function buildWorkbook() {
  const questions = await readCsv(path.join(dataDir, "raw_vs_summary_questions.csv"));
  const overall = await readCsv(path.join(dataDir, "raw_vs_summary_overall.csv"));
  const caseComp = await readCsv(path.join(dataDir, "raw_vs_summary_case_comparison.csv"));
  const conclusionCounts = await readCsv(path.join(dataDir, "raw_vs_summary_conclusion_counts.csv"));

  const wb = Workbook.create();
  const percentHeaders = overall.headers.filter((h) => h.endsWith("_rate"));

  const s1 = wb.worksheets.add("Question_Answers");
  applyBaseSheetStyle(s1, toMatrix(questions.headers, questions.rows), {
    freezeCols: 1,
    widths: { question: 40, short_answer: 36, evidence: 120 },
    wrapHeaders: ["question", "short_answer", "evidence"],
  });

  const s2 = wb.worksheets.add("Overall");
  applyBaseSheetStyle(s2, toMatrix(overall.headers, overall.rows), {
    freezeCols: 3,
    widths: { scope: 14, method: 24, method_label: 18 },
    centerHeaders: overall.headers.filter((h) => !["scope", "method", "method_label"].includes(h)),
    percentHeaders,
  });

  const caseHeaders = [
    "case_id",
    "bug_class",
    "raw_present",
    "summary_present",
    "raw_assertion_count",
    "summary_assertion_count",
    "raw_correct_pass_rate",
    "summary_correct_pass_rate",
    "delta_correct_pass_rate",
    "raw_fail_on_buggy_rate",
    "summary_fail_on_buggy_rate",
    "delta_fail_on_buggy_rate",
    "raw_antecedent_hit_rate",
    "summary_antecedent_hit_rate",
    "delta_antecedent_hit_rate",
    "raw_heldout_success_rate",
    "summary_heldout_success_rate",
    "delta_heldout_success_rate",
    "raw_trace_overfit_rate",
    "summary_trace_overfit_rate",
    "delta_trace_overfit_rate",
    "raw_literal_hardcoding_rate",
    "summary_literal_hardcoding_rate",
    "delta_literal_hardcoding_rate",
    "summary_lost_temporal_info",
    "summary_more_conservative",
    "summary_better_generalization",
    "case_conclusion",
    "case_note",
  ];
  const caseRows = caseComp.rows.map((r) =>
    Object.fromEntries(caseHeaders.map((h) => [h, r[h] ?? ""]))
  );
  const s3 = wb.worksheets.add("Case_Comparison");
  applyBaseSheetStyle(s3, toMatrix(caseHeaders, caseRows), {
    freezeCols: 6,
    widths: {
      case_id: 34,
      bug_class: 24,
      case_conclusion: 18,
      case_note: 110,
    },
    centerHeaders: caseHeaders.filter((h) => !["case_id", "bug_class", "case_conclusion", "case_note"].includes(h)),
    percentHeaders: caseHeaders.filter((h) => h.endsWith("_rate")),
    wrapHeaders: ["case_id", "case_conclusion", "case_note"],
    booleanHeaders: [
      "raw_present",
      "summary_present",
      "summary_lost_temporal_info",
      "summary_more_conservative",
      "summary_better_generalization",
    ],
    deltaHeaders: caseHeaders.filter((h) => h.startsWith("delta_")),
  });

  const detailHeaders = [
    "case_id",
    "module",
    "bug_name",
    "raw_top_failure_type",
    "raw_top_failure_reason",
    "raw_representative_assertion",
    "summary_top_failure_type",
    "summary_top_failure_reason",
    "summary_representative_assertion",
  ];
  const detailRows = caseComp.rows.map((r) =>
    Object.fromEntries(detailHeaders.map((h) => [h, r[h] ?? ""]))
  );
  const s4 = wb.worksheets.add("Case_Details");
  applyBaseSheetStyle(s4, toMatrix(detailHeaders, detailRows), {
    freezeCols: 3,
    widths: {
      case_id: 34,
      module: 18,
      bug_name: 26,
      raw_top_failure_reason: 44,
      raw_representative_assertion: 68,
      summary_top_failure_reason: 44,
      summary_representative_assertion: 68,
    },
  });

  const s5 = wb.worksheets.add("Conclusion_Counts");
  applyBaseSheetStyle(s5, toMatrix(conclusionCounts.headers, conclusionCounts.rows), {
    widths: { case_conclusion: 20, case_count: 12 },
    centerHeaders: ["case_count"],
  });

  addReadmeSheet(wb);

  const qPreview = await wb.render({
    sheetName: "Question_Answers",
    range: "A1:C6",
    scale: 2,
    format: "png",
    autoCrop: "all",
  });
  await fs.writeFile(
    path.join(outputDir, "raw_vs_summary_questions_preview.png"),
    new Uint8Array(await qPreview.arrayBuffer())
  );

  const casePreview = await wb.render({
    sheetName: "Case_Comparison",
    range: "A1:AD16",
    scale: 2,
    format: "png",
    autoCrop: "all",
  });
  await fs.writeFile(
    path.join(outputDir, "raw_vs_summary_case_preview.png"),
    new Uint8Array(await casePreview.arrayBuffer())
  );

  await fs.mkdir(outputDir, { recursive: true });
  const artifact = await SpreadsheetFile.exportXlsx(wb);
  await artifact.save(outputPath);
  console.log(outputPath);
}

buildWorkbook().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
