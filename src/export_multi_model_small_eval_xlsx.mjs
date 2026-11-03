import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const root = path.resolve(__dirname, "..");
const threadId = "019ed9f6-87cf-7830-adb8-595fe2ae140d";
const dataDir = path.join(root, "outputs", threadId, "multi_model_eval_data");
const outputDir = path.join(root, "outputs", threadId);

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

function toBool(value) {
  return ["true", "1", "yes"].includes(String(value ?? "").trim().toLowerCase());
}

function toNum(value) {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
}

function mean(values) {
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
}

function groupBy(rows, keyFn) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFn(row);
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(row);
  }
  return groups;
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

function toMatrix(headers, rows) {
  return [headers, ...rows.map((r) => headers.map((h) => r[h] ?? ""))];
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
    wrapText: true,
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
}

function tintBooleanColumn(sheet, matrix, header, yesColor, noColor) {
  const colIdx = matrix[0].indexOf(header);
  if (colIdx < 0) return;
  const colLetter = numberToColumn(colIdx + 1);
  for (let r = 2; r <= matrix.length; r++) {
    const val = String(matrix[r - 1][colIdx] ?? "").toLowerCase();
    if (val === "true") {
      sheet.getRange(`${colLetter}${r}`).format.fill = yesColor;
    } else if (val === "false") {
      sheet.getRange(`${colLetter}${r}`).format.fill = noColor;
    }
  }
}

function buildFailureModeSummary(rows) {
  const groupCols = ["model_label", "provider", "model_name", "method"];
  const groups = groupBy(rows, (row) => groupCols.map((k) => row[k] ?? "").join("||"));
  const out = [];
  for (const [key, sub] of groups.entries()) {
    const [modelLabel, provider, modelName, method] = key.split("||");
    const failureModes = sub.map((row) => row.failure_mode ?? "");
    out.push({
      model_label: modelLabel,
      provider: provider,
      model_name: modelName,
      method: method,
      candidate_count: sub.length,
      success_count: failureModes.filter((x) => x === "success").length,
      vacuity_count: failureModes.filter((x) => x === "vacuity").length,
      too_weak_count: failureModes.filter((x) => x === "too_weak").length,
      too_strong_count: failureModes.filter((x) => x === "too_strong").length,
      overfit_suspect_count: failureModes.filter((x) => x === "overfit_suspect").length,
      ineffective_count: failureModes.filter((x) => x === "ineffective").length,
      compile_fail_count: failureModes.filter((x) => x === "compile_fail").length,
      success_rate: mean(failureModes.map((x) => (x === "success" ? 1 : 0))),
      vacuity_rate: mean(failureModes.map((x) => (x === "vacuity" ? 1 : 0))),
      too_weak_rate: mean(failureModes.map((x) => (x === "too_weak" ? 1 : 0))),
      too_strong_rate: mean(failureModes.map((x) => (x === "too_strong" ? 1 : 0))),
      overfit_suspect_rate: mean(failureModes.map((x) => (x === "overfit_suspect" ? 1 : 0))),
      ineffective_rate: mean(failureModes.map((x) => (x === "ineffective" ? 1 : 0))),
      compile_fail_rate: mean(failureModes.map((x) => (x === "compile_fail" ? 1 : 0))),
    });
  }
  return out.sort((a, b) =>
    [a.model_label, a.method].join("||").localeCompare([b.model_label, b.method].join("||")),
  );
}

function buildCaseMethodSummary(rows) {
  const groupCols = ["model_label", "method", "case_id", "selection_tags", "selection_reason"];
  const groups = groupBy(rows, (row) => groupCols.map((k) => row[k] ?? "").join("||"));
  const out = [];
  for (const [key, sub] of groups.entries()) {
    const [modelLabel, method, caseId, selectionTags, selectionReason] = key.split("||");
    const strictSuccess = sub.map(
      (row) =>
        toBool(row.heldout_correct_pass) &&
        toBool(row.heldout_buggy_fail) &&
        toBool(row.heldout_antecedent_hit) &&
        toBool(row.heldout_non_vacuous),
    );
    const dominantFailureMode = Object.entries(
      sub.reduce((acc, row) => {
        const mode = row.failure_mode ?? "";
        acc[mode] = (acc[mode] ?? 0) + 1;
        return acc;
      }, {}),
    ).sort((a, b) => b[1] - a[1] || String(a[0]).localeCompare(String(b[0])))[0]?.[0] ?? "";

    const bestCandidate = sub
      .slice()
      .sort((a, b) => {
        const aScore =
          (toBool(a.correct_pass) ? 4 : 0) +
          (toBool(a.buggy_fail) ? 4 : 0) +
          (toBool(a.heldout_correct_pass) ? 2 : 0) +
          (toBool(a.heldout_buggy_fail) ? 2 : 0) +
          (toBool(a.antecedent_hit_buggy) ? 1 : 0) -
          (toBool(a.trace_overfit) ? 2 : 0) -
          (a.failure_mode === "compile_fail" ? 8 : 0);
        const bScore =
          (toBool(b.correct_pass) ? 4 : 0) +
          (toBool(b.buggy_fail) ? 4 : 0) +
          (toBool(b.heldout_correct_pass) ? 2 : 0) +
          (toBool(b.heldout_buggy_fail) ? 2 : 0) +
          (toBool(b.antecedent_hit_buggy) ? 1 : 0) -
          (toBool(b.trace_overfit) ? 2 : 0) -
          (b.failure_mode === "compile_fail" ? 8 : 0);
        return bScore - aScore;
      })[0];

    out.push({
      model_label: modelLabel,
      method: method,
      case_id: caseId,
      selection_tags: selectionTags,
      selection_reason: selectionReason,
      candidate_count: sub.length,
      compile_ok_rate: mean(sub.map((row) => (toBool(row.compile_ok) ? 1 : 0))),
      correct_pass_rate: mean(sub.map((row) => (toBool(row.correct_pass) ? 1 : 0))),
      buggy_fail_rate: mean(sub.map((row) => (toBool(row.buggy_fail) ? 1 : 0))),
      antecedent_hit_buggy_rate: mean(sub.map((row) => (toBool(row.antecedent_hit_buggy) ? 1 : 0))),
      non_vacuous_buggy_rate: mean(sub.map((row) => (toBool(row.non_vacuous_buggy) ? 1 : 0))),
      heldout_correct_pass_rate: mean(sub.map((row) => (toBool(row.heldout_correct_pass) ? 1 : 0))),
      heldout_buggy_fail_rate: mean(sub.map((row) => (toBool(row.heldout_buggy_fail) ? 1 : 0))),
      heldout_antecedent_hit_rate: mean(sub.map((row) => (toBool(row.heldout_antecedent_hit) ? 1 : 0))),
      trace_overfit_rate: mean(sub.map((row) => (toBool(row.trace_overfit) ? 1 : 0))),
      literal_hardcoding_rate: mean(sub.map((row) => (toBool(row.literal_hardcoding) ? 1 : 0))),
      semantic_reasonable_rate: mean(sub.map((row) => (toBool(row.semantic_reasonable) ? 1 : 0))),
      strict_success_rate: mean(strictSuccess.map((x) => (x ? 1 : 0))),
      dominant_failure_mode: dominantFailureMode,
      best_candidate_index: bestCandidate?.candidate_index ?? "",
      best_candidate_failure_mode: bestCandidate?.failure_mode ?? "",
      best_candidate_text: bestCandidate?.assertion_text ?? "",
    });
  }
  return out.sort((a, b) =>
    [a.model_label, a.case_id, a.method].join("||").localeCompare([b.model_label, b.case_id, b.method].join("||")),
  );
}

async function main() {
  const workbook = Workbook.create();
  const summary = await readCsv(path.join(dataDir, "multi_model_summary.csv"));
  const raw = await readCsv(path.join(dataDir, "multi_model_results_raw.csv"));
  const promptLog = await readCsv(path.join(dataDir, "multi_model_prompt_log.csv"));
  const runMeta = JSON.parse(await fs.readFile(path.join(dataDir, "multi_model_run_meta.json"), "utf8"));
  const modelSpecs = runMeta.model_specs ?? runMeta.active_model_specs ?? [];
  const methodSpecs = runMeta.method_specs ?? runMeta.active_method_specs ?? [];

  const failureModeSummaryRows = buildFailureModeSummary(raw.rows);
  const caseMethodSummaryRows = buildCaseMethodSummary(raw.rows);

  const readme = workbook.worksheets.add("README");
  applyBaseSheetStyle(
    readme,
    [
      ["artifact", "multi_model_small_eval"],
      ["description", "Small multi-model evaluation on 5 representative trace-sensitive cases."],
      ["selected_case_count", String(runMeta.representative_case_ids.length)],
      ["model_count", String(modelSpecs.length)],
      ["method_count", String(methodSpecs.length)],
      ["candidates_per_cell", String(runMeta.candidates_per_cell)],
      ["sheet", "model_method_summary"],
      ["sheet", "failure_mode_summary"],
      ["sheet", "case_method_summary"],
      ["sheet", "candidate_results"],
      ["sheet", "prompt_log"],
    ],
    { freezeCols: 1, widths: { artifact: 24, description: 56, sheet: 26 } },
  );

  const summarySheet = workbook.worksheets.add("model_method_summary");
  const summaryMatrix = toMatrix(summary.headers, summary.rows);
  applyBaseSheetStyle(summarySheet, summaryMatrix, {
    freezeCols: 4,
    widths: {
      model_label: 14,
      provider: 14,
      model_name: 24,
      method: 30,
    },
  });

  const failureSheet = workbook.worksheets.add("failure_mode_summary");
  const failureHeaders = Object.keys(failureModeSummaryRows[0] ?? {
    model_label: "",
    provider: "",
    model_name: "",
    method: "",
  });
  const failureMatrix = toMatrix(failureHeaders, failureModeSummaryRows);
  applyBaseSheetStyle(failureSheet, failureMatrix, {
    freezeCols: 4,
    widths: {
      model_label: 14,
      provider: 14,
      model_name: 24,
      method: 30,
    },
  });

  const caseSheet = workbook.worksheets.add("case_method_summary");
  const caseHeaders = Object.keys(caseMethodSummaryRows[0] ?? {
    model_label: "",
    method: "",
    case_id: "",
  });
  const caseMatrix = toMatrix(caseHeaders, caseMethodSummaryRows);
  applyBaseSheetStyle(caseSheet, caseMatrix, {
    freezeCols: 3,
    widths: {
      model_label: 14,
      method: 30,
      case_id: 38,
      selection_tags: 28,
      selection_reason: 42,
      best_candidate_text: 52,
    },
  });

  const rawSheet = workbook.worksheets.add("candidate_results");
  const rawMatrix = toMatrix(raw.headers, raw.rows);
  applyBaseSheetStyle(rawSheet, rawMatrix, {
    freezeCols: 5,
    widths: {
      model_label: 14,
      provider: 14,
      model_name: 24,
      case_id: 38,
      selection_tags: 26,
      selection_reason: 40,
      method: 30,
      trace_input_label: 24,
      assertion_text: 52,
      semantic_reason: 30,
      failure_reason: 32,
    },
  });
  [
    "compile_ok",
    "correct_pass",
    "buggy_fail",
    "antecedent_hit_buggy",
    "non_vacuous_buggy",
    "heldout_correct_pass",
    "heldout_buggy_fail",
    "heldout_antecedent_hit",
    "heldout_non_vacuous",
    "trace_overfit",
    "literal_hardcoding",
    "semantic_reasonable",
  ].forEach((header) => tintBooleanColumn(rawSheet, rawMatrix, header, "#D9EAD3", "#F4CCCC"));

  const promptSheet = workbook.worksheets.add("prompt_log");
  const promptMatrix = toMatrix(promptLog.headers, promptLog.rows);
  applyBaseSheetStyle(promptSheet, promptMatrix, {
    freezeCols: 4,
    widths: {
      model_label: 14,
      provider: 14,
      model_name: 24,
      case_id: 38,
      selection_tags: 26,
      selection_reason: 40,
      method: 30,
      prompt_path: 52,
      raw_generation_responses: 64,
    },
  });

  const out = await SpreadsheetFile.exportXlsx(workbook);
  await out.save(path.join(outputDir, "multi_model_small_eval.xlsx"));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
