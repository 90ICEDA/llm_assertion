import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "golden_analysis_data");
const outputDir = path.join(root, "outputs", threadId);

const files = {
  full: path.join(outputDir, "golden_selfcheck_full.xlsx"),
  temporal: path.join(outputDir, "golden_by_temporal_type.xlsx"),
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

function boolFill(value) {
  const v = String(value ?? "").trim().toLowerCase();
  if (v === "true") return "#D9EAD3";
  if (v === "false") return "#FCE4D6";
  return null;
}

function temporalFill(value) {
  const key = String(value ?? "").trim();
  const map = {
    same_cycle: "#EAF2F8",
    next_cycle: "#E8F6F3",
    multi_cycle_delay: "#FDF2E9",
    throughout_hold: "#F5EEF8",
    until_ready: "#FDEDEC",
    eventually: "#FEF9E7",
    stability: "#EBF5FB",
    onehot: "#E8F8F5",
    counter_boundary: "#FCF3CF",
    fifo_boundary: "#FDEBD0",
    fsm_transition: "#EAECEE",
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
          if (color) sheet.getRange(`${colLetter}${r}`).format.fill = color;
        }
      }
    }
  }

  if (opts.temporalHeaders?.length) {
    for (const header of opts.temporalHeaders) {
      const idx = matrix[0].indexOf(header);
      if (idx >= 0) {
        const colLetter = numberToColumn(idx + 1);
        for (let r = 2; r <= rowCount; r++) {
          const color = temporalFill(matrix[r - 1][idx]);
          if (color) sheet.getRange(`${colLetter}${r}`).format.fill = color;
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

async function buildFullWorkbook() {
  const full = await readCsv(path.join(dataDir, "golden_selfcheck_full.csv"));
  const expl = await readCsv(path.join(dataDir, "golden_explanations.csv"));

  const wb = Workbook.create();
  const s1 = wb.worksheets.add("Golden_Full");
  applyBaseSheetStyle(s1, toMatrix(full.headers, full.rows), {
    freezeCols: 6,
    widths: {
      case_id: 34,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      bug_type: 30,
      temporal_type: 18,
      assertion_line: 44,
      antecedent_text: 32,
      consequent_text: 32,
      failure_reason: 28,
      natural_language_intent: 44,
      best_llm_methods: 24,
    },
    temporalHeaders: ["temporal_type"],
    booleanHeaders: [
      "compile_ok",
      "correct_pass",
      "fail_on_buggy",
      "antecedent_hit_correct",
      "antecedent_hit_buggy",
      "non_vacuous_correct",
      "non_vacuous_buggy",
      "heldout_correct_pass",
      "heldout_buggy_fail",
      "heldout_antecedent_hit",
      "strict_check_all_true",
      "llm_case_present",
      "any_llm_robust_success",
    ],
  });

  const s2 = wb.worksheets.add("Explanations");
  applyBaseSheetStyle(s2, toMatrix(expl.headers, expl.rows), {
    freezeCols: 4,
    widths: {
      case_id: 34,
      module: 22,
      bug_name: 28,
      bug_class: 22,
      temporal_type: 18,
      natural_language_intent: 52,
    },
    temporalHeaders: ["temporal_type"],
  });

  addReadmeSheet(wb, "golden_selfcheck_full", [
    "每行一条 golden assertion，数据来自 WSL 中对 rtl_cases_real_active 的重新实测。",
    "strict_check_all_true 对应用户要求的 10 个硬条件是否全部成立。",
    "同时补充了每个 case 的 temporal_type、自然语言设计意图，以及 LLM robust-success 覆盖情况。",
  ]);
  return wb;
}

async function buildTemporalWorkbook() {
  const summary = await readCsv(path.join(dataDir, "golden_temporal_type_summary.csv"));
  const hardest = await readCsv(path.join(dataDir, "golden_temporal_type_hardest.csv"));
  const caseMap = await readCsv(path.join(dataDir, "golden_llm_gap_case_map.csv"));

  const wb = Workbook.create();
  const s1 = wb.worksheets.add("Temporal_Summary");
  applyBaseSheetStyle(s1, toMatrix(summary.headers, summary.rows), {
    widths: { temporal_type: 18 },
    temporalHeaders: ["temporal_type"],
    centerHeaders: summary.headers.filter((h) => h !== "temporal_type"),
  });

  const s2 = wb.worksheets.add("Hardest_Rank");
  applyBaseSheetStyle(s2, toMatrix(hardest.headers, hardest.rows), {
    widths: { temporal_type: 18 },
    temporalHeaders: ["temporal_type"],
    centerHeaders: hardest.headers.filter((h) => h !== "temporal_type"),
  });

  const s3 = wb.worksheets.add("Case_Map");
  applyBaseSheetStyle(s3, toMatrix(caseMap.headers, caseMap.rows), {
    freezeCols: 2,
    widths: { case_id: 34, temporal_type: 18, failure_reason: 28, best_llm_methods: 24 },
    temporalHeaders: ["temporal_type"],
    booleanHeaders: [
      "strict_check_all_true",
      "llm_case_present",
      "any_llm_robust_success",
      "spec_only_has_robust_success",
      "spec_plus_rtl_has_robust_success",
      "spec_rtl_raw_trace_has_robust_success",
      "spec_rtl_trace_summary_has_robust_success",
    ],
  });

  addReadmeSheet(wb, "golden_by_temporal_type", [
    "Temporal_Summary 汇总每类 golden 的严格自检结果与 LLM robust-success 覆盖率。",
    "Hardest_Rank 按 strict golden 上的 LLM 成功率从低到高排序，可直接看最难 temporal_type。",
    "Case_Map 给出每个 case 的 temporal_type 和方法级 robust-success 命中情况。",
  ]);
  return wb;
}

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const fullWb = await buildFullWorkbook();
  const fullOut = await SpreadsheetFile.exportXlsx(fullWb);
  await fullOut.save(files.full);

  const temporalWb = await buildTemporalWorkbook();
  const temporalOut = await SpreadsheetFile.exportXlsx(temporalWb);
  await temporalOut.save(files.temporal);

  console.log(files.full);
  console.log(files.temporal);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
