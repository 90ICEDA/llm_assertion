import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const outputDir = path.join(
  root,
  "outputs",
  "019ed9f6-87cf-7830-adb8-595fe2ae140d",
);

const masterCsvPath = path.join(
  root,
  "docs",
  "real_rtl_scaleout",
  "assertion_clean_master_iv12.csv",
);
const statsCsvPath = path.join(
  root,
  "docs",
  "real_rtl_scaleout",
  "assertion_clean_stats_iv12.csv",
);
const notesTxtPath = path.join(outputDir, "模板垃圾清理说明.txt");
const masterXlsxPath = path.join(outputDir, "主表_clean.xlsx");
const statsXlsxPath = path.join(outputDir, "候选去重统计.xlsx");

async function formatCsvWorkbook(csvPath, sheetName, title) {
  const csvText = await fs.readFile(csvPath, "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const sheet = workbook.worksheets.getItem(sheetName);
  sheet.showGridLines = false;

  const used = sheet.getUsedRange();
  const usedValues = used.values ?? [];
  const rowCount = usedValues.length;
  const colCount = rowCount ? usedValues[0].length : 0;
  const lastCol = numberToColumn(colCount || 1);
  const headers = rowCount ? usedValues[0].map((x) => String(x ?? "")) : [];

  sheet.getRange(`A1:${lastCol}1`).format = {
    fill: "#1F4E78",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    horizontalAlignment: "Center",
    verticalAlignment: "Center",
    borders: { preset: "all", style: "thin", color: "#D9E2F3" },
  };
  sheet.getRange(`A1:${lastCol}${Math.max(rowCount, 1)}`).format.borders = {
    preset: "all",
    style: "thin",
    color: "#D9D9D9",
  };
  sheet.getRange(`A1:${lastCol}${Math.max(rowCount, 1)}`).format.verticalAlignment =
    "Top";

  if (rowCount >= 2) {
    sheet.getRange(`A2:${lastCol}${rowCount}`).format.wrapText = false;
  }

  sheet.freezePanes.freezeRows(1);
  sheet.getRange(`A1:${lastCol}${Math.max(rowCount, 1)}`).format.autofitColumns();
  sheet.getRange(`A1:${lastCol}${Math.max(rowCount, 1)}`).format.autofitRows();

  for (let c = 0; c < colCount; c++) {
    const colLetter = numberToColumn(c + 1);
    const width = sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth;
    if (width && width > 28) {
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = 28;
    }
  }

  const preferredWidths = {
    assertion_text: 42,
    normalized_assertion: 42,
    failure_reason: 36,
    candidate_indices: 16,
    prompt_type: 22,
    case_id: 26,
    module: 22,
    bug_name: 28,
    bug_class: 22,
    failure_type: 22,
  };
  headers.forEach((header, idx) => {
    const preferred = preferredWidths[header];
    if (preferred) {
      const colLetter = numberToColumn(idx + 1);
      sheet.getRange(`${colLetter}:${colLetter}`).format.columnWidth = preferred;
    }
  });

  if (colCount >= 1) {
    sheet.getRange(`A1:${lastCol}1`).format.rowHeight = 28;
  }

  const meta = workbook.worksheets.add("README");
  meta.showGridLines = false;
  meta.getRange("A1:B6").values = [
    ["artifact", title],
    ["source_csv", path.relative(root, csvPath)],
    ["generated_at", new Date().toISOString()],
    ["note_1", "Header frozen at row 1"],
    ["note_2", "Columns autofit then capped to keep workbook readable"],
    ["note_3", "This workbook is a formatted export of the clean CSV deliverable"],
  ];
  meta.getRange("A1:B1").format = {
    fill: "#D9EAD3",
    font: { bold: true },
  };
  meta.getRange("A1:B6").format.autofitColumns();

  return workbook;
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

async function renderPreview(workbook, sheetName, fileName) {
  const blob = await workbook.render({
    sheetName,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(fileName, new Uint8Array(await blob.arrayBuffer()));
}

async function exportWorkbook(workbook, savePath) {
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(savePath);
}

async function buildNotesText() {
  const statsCsv = await fs.readFile(statsCsvPath, "utf8");
  const lines = statsCsv.trim().split(/\r?\n/);
  const headers = splitCsvLine(lines[0]);
  const rows = lines.slice(1).map((line) => {
    const values = splitCsvLine(line);
    return Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""]));
  });
  const overall = rows.find((row) => row.scope === "overall");
  const byMethod = rows.filter((row) => row.scope === "method");

  const parts = [];
  parts.push("模板垃圾清理说明");
  parts.push("");
  parts.push("1. 数据来源");
  parts.push("- 主来源：rtl_cases_real_admitted_20260619/strict_eval_report_iv12.csv");
  parts.push("- case 元数据补充：docs/real_rtl_scaleout/dataset_inventory_30cases.csv");
  parts.push("");
  parts.push("2. clean 主表保留原则");
  parts.push("- clean 主表只保留有 assertion_text 的候选。");
  parts.push("- 每一行是一条去重后的 assertion，而不是原始重复候选。");
  parts.push("- 当前去重键为：(case_id, method, normalized_assertion)。");
  parts.push("");
  parts.push("3. 模板垃圾定义");
  parts.push("- assertion_text 为空；或");
  parts.push("- failure_type == template_mismatch。");
  parts.push("- 这两类都记入 template_garbage_count，不再与 compile fail / unsupported 混算。");
  parts.push("");
  parts.push("4. 分项统计（overall）");
  parts.push(`- 原始候选数 raw_candidate_count = ${overall?.raw_candidate_count ?? ""}`);
  parts.push(`- 有 assertion 文本的原始候选数 raw_assertion_text_count = ${overall?.raw_assertion_text_count ?? ""}`);
  parts.push(`- 去重后候选数 dedup_candidate_count = ${overall?.dedup_candidate_count ?? ""}`);
  parts.push(`- 模板垃圾数 template_garbage_count = ${overall?.template_garbage_count ?? ""}`);
  parts.push(`- unsupported 数 unsupported_count = ${overall?.unsupported_count ?? ""}`);
  parts.push(`- compile fail 数 compile_fail_count = ${overall?.compile_fail_count ?? ""}`);
  parts.push(`- 其中 syntax error 数 syntax_error_count = ${overall?.syntax_error_count ?? ""}`);
  parts.push("");
  parts.push("5. 各 method 的模板垃圾数");
  for (const row of byMethod) {
    parts.push(
      `- ${row.scope_value}: raw=${row.raw_candidate_count}, dedup=${row.dedup_candidate_count}, template=${row.template_garbage_count}, unsupported=${row.unsupported_count}, compile_fail=${row.compile_fail_count}, syntax_error=${row.syntax_error_count}`,
    );
  }
  parts.push("");
  parts.push("6. 说明");
  parts.push("- 这版数据里 unsupported_count 为 0；也就是当前 analysis_supported == False 的行都落在模板垃圾集合内，没有额外独立 unsupported 行。");
  parts.push("- compile_fail_count 与 syntax_error_count 分开列出；当前 compile fail 都是 syntax error。");
  return parts.join("\n");
}

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

async function main() {
  await fs.mkdir(outputDir, { recursive: true });

  const masterWb = await formatCsvWorkbook(masterCsvPath, "clean_master", "主表_clean");
  const statsWb = await formatCsvWorkbook(statsCsvPath, "dedupe_stats", "候选去重统计");

  await exportWorkbook(masterWb, masterXlsxPath);
  await exportWorkbook(statsWb, statsXlsxPath);

  await renderPreview(masterWb, "clean_master", path.join(outputDir, "主表_clean_preview.png"));
  await renderPreview(statsWb, "dedupe_stats", path.join(outputDir, "候选去重统计_preview.png"));

  const notesText = await buildNotesText();
  await fs.writeFile(notesTxtPath, `\uFEFF${notesText}`, "utf8");

  console.log(masterXlsxPath);
  console.log(statsXlsxPath);
  console.log(notesTxtPath);
}

await main();
