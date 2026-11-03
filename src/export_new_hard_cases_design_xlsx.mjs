import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "new_hard_cases_data");
const outputDir = path.join(root, "outputs", threadId);
const outputPath = path.join(outputDir, "新增20个hard_cases设计表.xlsx");

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
  const headers = splitCsvLine(lines[0].replace(/^\uFEFF/, ""));
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
    wrapText: true,
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
    if (width && width > 34) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 34;
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

function addReadmeSheet(workbook) {
  const sheet = workbook.worksheets.add("README");
  sheet.showGridLines = false;
  const rows = [
    ["artifact", "新增20个hard_cases设计表"],
    ["note_1", "本交付先完成 20 个新增 hard cases 的设计表；RTL/TB/wave 尚未落地实现。"],
    ["note_2", "四组各 5 个 case：A=trace 应该有帮助，B=trace 容易诱导数值 overfit，C=trace 容易导致 vacuity，D=summary 容易丢复杂关系。"],
    ["note_3", "correct_rtl / buggy_rtl 字段当前是 RTL sketch，而不是完整可综合源码。"],
    ["note_4", "golden_self_check_result 表示该 case 设计目标下的预期严格自检结果。"],
  ];
  sheet.getRange(`A1:B${rows.length}`).values = rows;
  sheet.getRange("A1:B1").format = {
    fill: "#D9EAD3",
    font: { bold: true },
    borders: { preset: "all", style: "thin", color: "#B7C9A8" },
  };
  sheet.getRange(`A2:B${rows.length}`).format = {
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#E6E6E6" },
  };
  sheet.getRange(`A1:B${rows.length}`).format.autofitColumns();
  sheet.getRange(`A1:B${rows.length}`).format.autofitRows();
  sheet.getRange("A:A").format.columnWidth = 16;
  sheet.getRange("B:B").format.columnWidth = 94;
}

async function buildWorkbook() {
  const master = await readCsv(path.join(dataDir, "hard_cases_design_master.csv"));
  const summary = await readCsv(path.join(dataDir, "hard_cases_group_summary.csv"));

  const wb = Workbook.create();

  const s1 = wb.worksheets.add("Master");
  applyBaseSheetStyle(s1, toMatrix(master.headers, master.rows), {
    freezeCols: 4,
    widths: {
      group_id: 8,
      group_theme: 24,
      case_id: 36,
      module: 22,
      spec: 58,
      correct_rtl: 50,
      buggy_rtl: 50,
      bug_description: 42,
      bug_class: 22,
      temporal_type: 28,
      expected_trace_effect: 24,
      seen_good_trace: 46,
      seen_bad_trace: 46,
      heldout_good_trace: 46,
      heldout_bad_trace: 46,
      golden_sva: 60,
      golden_self_check_result: 34,
      why_hard: 46,
    },
    centerHeaders: [
      "group_id",
      "overfit_lure_present",
      "bug_class",
      "expected_trace_effect",
    ],
    booleanHeaders: ["overfit_lure_present"],
  });

  const s2 = wb.worksheets.add("Group_Summary");
  applyBaseSheetStyle(s2, toMatrix(summary.headers, summary.rows), {
    widths: {
      group_id: 8,
      group_theme: 24,
      case_count: 12,
      bug_classes: 30,
      temporal_types: 86,
      expected_trace_effect: 24,
      overfit_lure_true_count: 18,
    },
    centerHeaders: ["group_id", "case_count", "expected_trace_effect", "overfit_lure_true_count"],
  });

  for (const groupId of ["A", "B", "C", "D"]) {
    const groupRows = master.rows.filter((row) => row.group_id === groupId);
    const sheet = wb.worksheets.add(`Group_${groupId}`);
    applyBaseSheetStyle(sheet, toMatrix(master.headers, groupRows), {
      freezeCols: 4,
      widths: {
        group_id: 8,
        group_theme: 24,
        case_id: 36,
        module: 22,
        spec: 58,
        correct_rtl: 50,
        buggy_rtl: 50,
        bug_description: 42,
        bug_class: 22,
        temporal_type: 28,
        expected_trace_effect: 24,
        seen_good_trace: 46,
        seen_bad_trace: 46,
        heldout_good_trace: 46,
        heldout_bad_trace: 46,
        golden_sva: 60,
        golden_self_check_result: 34,
        why_hard: 46,
      },
      centerHeaders: [
        "group_id",
        "overfit_lure_present",
        "bug_class",
        "expected_trace_effect",
      ],
      booleanHeaders: ["overfit_lure_present"],
    });
  }

  addReadmeSheet(wb);

  const preview = await wb.render({
    sheetName: "Master",
    range: "A1:J10",
    scale: 2,
    format: "png",
    autoCrop: "all",
  });
  await fs.writeFile(
    path.join(outputDir, "新增20个hard_cases设计表_preview.png"),
    new Uint8Array(await preview.arrayBuffer())
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
