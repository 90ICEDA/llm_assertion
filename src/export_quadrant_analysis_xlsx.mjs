import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "quadrant_analysis_data");
const outputDir = path.join(root, "outputs", threadId);

const files = {
  overall: path.join(outputDir, "四象限总表.xlsx"),
  byBugClass: path.join(outputDir, "四象限_by_bug_class.xlsx"),
  byCase: path.join(outputDir, "四象限_by_case.xlsx"),
};

const quadrantColors = {
  真成功: "#E2F0D9",
  太弱: "#FFF2CC",
  太强: "#FCE4D6",
  无效: "#EDEDED",
  无clean断言: "#F4F4F4",
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
    if (width && width > 26) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 26;
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

  if (opts.quadrantHeaders?.length) {
    for (const header of opts.quadrantHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const value = String(matrix[r - 1][idx] ?? "");
          const color = quadrantColors[value];
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

async function buildOverallWorkbook() {
  const overallMatrix = await readCsv(path.join(dataDir, "quadrant_overall_matrix.csv"));
  const overallLong = await readCsv(path.join(dataDir, "quadrant_overall_long.csv"));
  const assertionRows = await readCsv(path.join(dataDir, "quadrant_assertion_rows.csv"));
  const primaryCounts = await readCsv(path.join(dataDir, "quadrant_case_primary_method_counts.csv"));

  const wb = Workbook.create();
  const s1 = wb.worksheets.add("Summary");
  applyBaseSheetStyle(s1, toMatrix(overallMatrix.headers, overallMatrix.rows), {
    widths: { method_label: 28, total_assertions: 14 },
    centerHeaders: ["真成功", "太弱", "太强", "无效", "total_assertions"],
    percentHeaders: ["真成功_share", "太弱_share", "太强_share", "无效_share"],
  });

  const s2 = wb.worksheets.add("Overall_Long");
  applyBaseSheetStyle(s2, toMatrix(overallLong.headers, overallLong.rows), {
    widths: { method_label: 28, quadrant: 14 },
    centerHeaders: ["assertion_count", "case_count"],
  });

  const s3 = wb.worksheets.add("Case_Primary");
  applyBaseSheetStyle(s3, toMatrix(primaryCounts.headers, primaryCounts.rows), {
    widths: { method: 22, method_label: 28, primary_quadrant: 16 },
    quadrantHeaders: ["primary_quadrant"],
    centerHeaders: ["case_count"],
  });

  const s4 = wb.worksheets.add("Assertion_Rows");
  applyBaseSheetStyle(s4, toMatrix(assertionRows.headers, assertionRows.rows), {
    freezeCols: 6,
    widths: {
      case_id: 28,
      module: 24,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      quadrant: 12,
      assertion_text: 40,
      normalized_assertion: 40,
    },
    quadrantHeaders: ["quadrant"],
  });

  addReadmeSheet(wb, "四象限总表", [
    "统计对象是去重后的 clean assertion（assertion_clean_master_iv12.csv）。",
    "四象限定义：真成功=(1,1)，太弱=(1,0)，太强=(0,1)，无效=(0,0)。",
    "Case_Primary sheet 的主象限规则：真成功 > 太弱 > 太强 > 无效；若该 case-method 没有 clean assertion，则记为 无clean断言。",
  ]);
  return wb;
}

async function buildBugClassWorkbook() {
  const matrix = await readCsv(path.join(dataDir, "quadrant_by_bug_class_matrix.csv"));
  const long = await readCsv(path.join(dataDir, "quadrant_by_bug_class_long.csv"));

  const wb = Workbook.create();
  const s1 = wb.worksheets.add("By_Bug_Class");
  applyBaseSheetStyle(s1, toMatrix(matrix.headers, matrix.rows), {
    widths: { bug_class: 24, method_label: 28, total_assertions: 14 },
    centerHeaders: ["真成功", "太弱", "太强", "无效", "total_assertions"],
  });

  const s2 = wb.worksheets.add("Long_Form");
  applyBaseSheetStyle(s2, toMatrix(long.headers, long.rows), {
    widths: { bug_class: 24, method_label: 28, quadrant: 14 },
    quadrantHeaders: ["quadrant"],
    centerHeaders: ["assertion_count", "case_count"],
  });

  addReadmeSheet(wb, "四象限_by_bug_class", [
    "bug_class 默认优先展示 combination_same_cycle 和 temporal_cross_cycle。",
    "如果后续数据里出现其他 bug_class，会在本工作簿中单独列出，不会并入 existing buckets。",
  ]);
  return wb;
}

async function buildCaseWorkbook() {
  const summary = await readCsv(path.join(dataDir, "quadrant_case_summary.csv"));
  const detail = await readCsv(path.join(dataDir, "quadrant_case_method_full.csv"));

  const wb = Workbook.create();
  const s1 = wb.worksheets.add("Case_Summary");
  applyBaseSheetStyle(s1, toMatrix(summary.headers, summary.rows), {
    freezeCols: 4,
    widths: {
      case_id: 28,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      spec_only_primary_quadrant: 16,
      spec_plus_rtl_primary_quadrant: 16,
      spec_rtl_raw_trace_primary_quadrant: 16,
      spec_rtl_trace_summary_primary_quadrant: 18,
      spec_only_quadrants_seen: 18,
      spec_plus_rtl_quadrants_seen: 18,
      spec_rtl_raw_trace_quadrants_seen: 18,
      spec_rtl_trace_summary_quadrants_seen: 18,
    },
    quadrantHeaders: [
      "spec_only_primary_quadrant",
      "spec_plus_rtl_primary_quadrant",
      "spec_rtl_raw_trace_primary_quadrant",
      "spec_rtl_trace_summary_primary_quadrant",
    ],
  });

  const s2 = wb.worksheets.add("Case_Method_Detail");
  applyBaseSheetStyle(s2, toMatrix(detail.headers, detail.rows), {
    freezeCols: 6,
    widths: {
      case_id: 28,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      method_label: 28,
      primary_quadrant: 16,
      quadrants_seen: 20,
    },
    quadrantHeaders: ["primary_quadrant"],
    centerHeaders: [
      "clean_assertion_count",
      "mixed_quadrants",
      "真成功_count",
      "太弱_count",
      "太强_count",
      "无效_count",
    ],
  });

  addReadmeSheet(wb, "四象限_by_case", [
    "Case_Summary 每行一个 case，四种方法各给一个主象限。",
    "如果同一 case-method 同时出现多个象限，Case_Summary 仍给出主象限，但 quadrants_seen 会保留完整集合。",
    "Case_Method_Detail 提供每个 case-method 的四象限计数明细。",
  ]);
  return wb;
}

async function exportWorkbook(workbook, savePath) {
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(savePath);
}

async function renderSheet(workbook, sheetName, savePath) {
  const blob = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(savePath, new Uint8Array(await blob.arrayBuffer()));
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });

  const overallWb = await buildOverallWorkbook();
  const byBugClassWb = await buildBugClassWorkbook();
  const byCaseWb = await buildCaseWorkbook();

  await exportWorkbook(overallWb, files.overall);
  await exportWorkbook(byBugClassWb, files.byBugClass);
  await exportWorkbook(byCaseWb, files.byCase);

  await renderSheet(overallWb, "Summary", path.join(outputDir, "四象限总表_preview.png"));
  await renderSheet(byBugClassWb, "By_Bug_Class", path.join(outputDir, "四象限_by_bug_class_preview.png"));
  await renderSheet(byCaseWb, "Case_Summary", path.join(outputDir, "四象限_by_case_preview.png"));

  console.log(files.overall);
  console.log(files.byBugClass);
  console.log(files.byCase);
}

await main();
