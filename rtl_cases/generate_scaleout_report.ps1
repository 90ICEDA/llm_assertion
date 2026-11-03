$ErrorActionPreference = 'Stop'

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$activeRoot = Join-Path $repoRoot 'rtl_cases_real_active'
$admittedRoot = Join-Path $repoRoot 'rtl_cases_real_admitted_20260619'
$docsRoot = Join-Path $repoRoot 'docs\real_rtl_scaleout'
$attachmentsRoot = Join-Path $env:USERPROFILE '.codex\attachments'

New-Item -ItemType Directory -Force -Path $docsRoot | Out-Null

function ConvertTo-BoolString($value) {
  if ($null -eq $value) { return '' }
  $text = [string]$value
  if ($text -eq 'True' -or $text -eq 'False') { return $text }
  if ($value) { return 'True' }
  return 'False'
}

function Load-JsonFile([string]$path) {
  return ((Get-Content $path -Raw) | ConvertFrom-Json)
}

function Index-CsvBy([object[]]$rows, [string]$columnName) {
  $index = @{}
  foreach ($row in $rows) {
    $index[$row.$columnName] = $row
  }
  return $index
}

function Parse-StrictEvalAttachment([string]$path) {
  $rows = @()
  $regex = '^(?<case>[^|]+?)\s+\|\s+(?<file>sva_(?<methodId>\d+)_([^|]+?)__cand_(?<cand>\d+)\.sv)\s+\|\s+template=(?<template>\w+)\s+compile=(?<compile>\w+)\s+correct_pass=(?<correct>\w+)\s+buggy_fail=(?<buggy>\w+)\s+non_vacuous=(?<nv>\w+)\s+strict_success=(?<ss>\w+)\s+failure_type=(?<ft>\S+)'
  foreach ($line in Get-Content $path) {
    $m = [regex]::Match($line, $regex)
    if (-not $m.Success) { continue }
    $method = switch ($m.Groups['methodId'].Value) {
      '1' { 'spec_only' }
      '2' { 'spec_plus_rtl' }
      '3' { 'spec_rtl_raw_trace' }
      '4' { 'spec_rtl_trace_summary' }
      default { "unknown_$($m.Groups['methodId'].Value)" }
    }
    $rows += [pscustomobject]@{
      case_name       = $m.Groups['case'].Value.Trim()
      method          = $method
      candidate_index = [int]$m.Groups['cand'].Value
      sva_file        = $m.Groups['file'].Value
      template        = $m.Groups['template'].Value
      compile         = $m.Groups['compile'].Value
      correct_pass    = $m.Groups['correct'].Value
      buggy_fail      = $m.Groups['buggy'].Value
      non_vacuous     = $m.Groups['nv'].Value
      strict_success  = $m.Groups['ss'].Value
      failure_type    = $m.Groups['ft'].Value
    }
  }
  return $rows
}

function Get-PrimaryAttribution([object[]]$rows) {
  $fts = @($rows | ForEach-Object { $_.failure_type })
  if ($fts -contains 'trace_overfit') { return 'trace_overfit' }
  if ($fts -contains 'compile_fail') { return 'compile_fail' }
  if ($fts -contains 'template_mismatch') { return 'template_mismatch' }
  if ($fts -contains 'antecedent_not_triggered') { return 'antecedent_too_weak_or_not_triggered' }
  if ($fts -contains 'bug_not_detected_on_buggy') { return 'consequent_too_conservative_or_temporal_operator_wrong' }
  if ($fts -contains 'false_positive_on_correct') { return 'consequent_or_temporal_operator_too_strict' }
  if ($fts -contains 'vacuous') { return 'vacuous' }
  if ($fts -contains 'semantic_unreviewed') { return 'semantic_unreviewed' }
  return (($fts | Sort-Object -Unique) -join ';')
}

$manifest = Load-JsonFile (Join-Path $activeRoot 'case_manifest.json')
$cases = @($manifest.cases)
$caseIndex = @{}
foreach ($case in $cases) {
  $caseIndex[$case.name] = $case
}

$inventoryRows = foreach ($case in $cases) {
  $caseDir = Join-Path $activeRoot $case.name
  [pscustomobject]@{
    case_name                = $case.name
    bug_class                = $case.bug_class
    bug_family               = $case.bug_family
    bug_type                 = $case.bug_type
    source_project           = $case.source_project
    source_module            = $case.source_module
    overfit_lure_present     = ConvertTo-BoolString(-not [string]::IsNullOrWhiteSpace([string]$case.overfit_lure))
    case_dir                 = $caseDir
    correct_rtl_exists       = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'correct.v'))
    buggy_rtl_exists         = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'buggy.v'))
    golden_in_manifest       = ConvertTo-BoolString(-not [string]::IsNullOrWhiteSpace([string]$case.golden_sva.sva))
    spec_exists              = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'experiment\spec.txt'))
    good_trace_exists        = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'experiment\trace_good.txt'))
    bad_trace_exists         = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'experiment\trace_bad.txt'))
    heldout_good_trace_exists= ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'experiment\trace_good_holdout.txt'))
    heldout_bad_trace_exists = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'experiment\trace_bad_holdout.txt'))
    good_wave_csv_exists     = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'waveform_good.csv'))
    bad_wave_csv_exists      = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'waveform_bad.csv'))
    heldout_good_wave_exists = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'waveform_good_holdout.csv'))
    heldout_bad_wave_exists  = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'waveform_bad_holdout.csv'))
    tb_exists                = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'tb.v'))
    tb_holdout_exists        = ConvertTo-BoolString(Test-Path (Join-Path $caseDir 'tb_holdout.v'))
  }
}
$inventoryPath = Join-Path $docsRoot 'dataset_inventory_30cases.csv'
$inventoryRows | Sort-Object case_name | Export-Csv -NoTypeInformation -Encoding UTF8 $inventoryPath

$goldenRows = Import-Csv (Join-Path $activeRoot 'golden_sva_check_report.csv')
$goldenIndex = Index-CsvBy $goldenRows 'case_name'
$hardnessLatestRows = Import-Csv (Join-Path $activeRoot 'hardness_check_report_latest.csv')
$hardnessLatestIndex = Index-CsvBy $hardnessLatestRows 'case_name'
$hardnessPulsefixIndex = Index-CsvBy (Import-Csv (Join-Path $activeRoot 'hardness_check_report_case116_pulsefix.csv')) 'case_name'

$goldenStatusRows = foreach ($case in $cases) {
  $g = $goldenIndex[$case.name]
  $hLatest = $hardnessLatestIndex[$case.name]
  $hPulse = $hardnessPulsefixIndex[$case.name]
  $statusSource = ''
  $goldenOk = ''
  $antecedentHits = ''
  $antecedentTriggered = ''
  $failureReason = ''
  $statusNote = ''

  if ($g) {
    $statusSource = 'golden_report'
    $goldenOk = $g.golden_ok
    $antecedentHits = $g.buggy_antecedent_hits
    $antecedentTriggered = $g.antecedent_triggered
    $failureReason = $g.failure_reason
    $statusNote = 'report_row_present'
  } elseif ($case.name -eq 'case116_prim_filter_late_accept' -and $hPulse) {
    $statusSource = 'case116_pulsefix_hardness_report'
    $goldenOk = $hPulse.golden_ok
    $antecedentHits = $hPulse.golden_buggy_hits
    $antecedentTriggered = if ([int]$hPulse.golden_buggy_hits -gt 0) { 'True' } else { 'False' }
    $failureReason = $hPulse.failure_reason
    $statusNote = 'missing_from_golden_report__pulsefix_hardness_says_pass'
  } else {
    $statusSource = 'missing'
    $statusNote = 'no_local_gold_report_row'
  }

  if ($case.name -eq 'case116_prim_filter_late_accept' -and $hLatest -and $hPulse -and $hLatest.golden_ok -ne $hPulse.golden_ok) {
    $statusNote = 'conflict__latest_hardness_false_but_case116_pulsefix_true'
  }

  [pscustomobject]@{
    case_name            = $case.name
    bug_class            = $case.bug_class
    golden_source_status = $statusSource
    golden_ok            = $goldenOk
    antecedent_triggered = $antecedentTriggered
    buggy_antecedent_hits= $antecedentHits
    failure_reason       = $failureReason
    status_note          = $statusNote
  }
}
$goldenStatusPath = Join-Path $docsRoot 'golden_status_30cases.csv'
$goldenStatusRows | Sort-Object case_name | Export-Csv -NoTypeInformation -Encoding UTF8 $goldenStatusPath

$antecedentRows = foreach ($row in $goldenStatusRows) {
  $hits = 0
  if ($row.buggy_antecedent_hits -match '^\d+$') { $hits = [int]$row.buggy_antecedent_hits }
  [pscustomobject]@{
    case_name               = $row.case_name
    bug_class               = $row.bug_class
    golden_source_status    = $row.golden_source_status
    antecedent_triggered    = $row.antecedent_triggered
    buggy_antecedent_hits   = $row.buggy_antecedent_hits
    antecedent_coverage_ok  = ConvertTo-BoolString($hits -gt 0)
    status_note             = $row.status_note
  }
}
$antecedentPath = Join-Path $docsRoot 'antecedent_coverage_30cases.csv'
$antecedentRows | Sort-Object case_name | Export-Csv -NoTypeInformation -Encoding UTF8 $antecedentPath

$cloudMethodBugclassCsv = @'
method,bug_class,rows,cases,compile_ok,correct_pass,buggy_fail,non_vacuous,strict_success
spec_only,combination_same_cycle,60,12,58,23,38,48,0
spec_only,temporal_cross_cycle,55,11,55,48,16,23,0
spec_plus_rtl,combination_same_cycle,60,12,60,22,29,35,0
spec_plus_rtl,temporal_cross_cycle,55,11,55,44,10,16,0
spec_rtl_raw_trace,combination_same_cycle,60,12,60,26,39,34,0
spec_rtl_raw_trace,temporal_cross_cycle,55,11,55,22,9,10,0
spec_rtl_trace_summary,combination_same_cycle,60,12,59,36,27,32,0
spec_rtl_trace_summary,temporal_cross_cycle,55,11,50,27,14,16,0
'@ | ConvertFrom-Csv

$cloudOverallCsv = @'
method,rows,compile_ok,correct_pass,buggy_fail,non_vacuous,strict_success
spec_only,115,113,71,54,71,0
spec_plus_rtl,115,115,66,39,51,0
spec_rtl_raw_trace,115,115,48,48,44,0
spec_rtl_trace_summary,115,109,63,41,48,0
'@ | ConvertFrom-Csv

$cloudSummaryPath = Join-Path $docsRoot 'full_admitted_cloud_method_bugclass_candidate_level.csv'
$cloudMethodBugclassCsv | Export-Csv -NoTypeInformation -Encoding UTF8 $cloudSummaryPath

$cloudOverallPath = Join-Path $docsRoot 'full_admitted_cloud_overall_candidate_level.csv'
$cloudOverallCsv | Export-Csv -NoTypeInformation -Encoding UTF8 $cloudOverallPath

$specPlusByClass = @{}
$traceSummaryByClass = @{}
foreach ($row in $cloudMethodBugclassCsv) {
  if ($row.method -eq 'spec_plus_rtl') { $specPlusByClass[$row.bug_class] = $row }
  if ($row.method -eq 'spec_rtl_trace_summary') { $traceSummaryByClass[$row.bug_class] = $row }
}

$gapRows = foreach ($bugClass in @('combination_same_cycle', 'temporal_cross_cycle')) {
  $base = $specPlusByClass[$bugClass]
  $trace = $traceSummaryByClass[$bugClass]
  [pscustomobject]@{
    scope                              = $bugClass
    evaluation_level                   = 'candidate_row'
    baseline_method                    = 'spec_plus_rtl'
    compare_method                     = 'spec_rtl_trace_summary'
    baseline_cases                     = $base.cases
    baseline_rows                      = $base.rows
    baseline_correct_pass              = $base.correct_pass
    baseline_buggy_fail                = $base.buggy_fail
    baseline_strict_success            = $base.strict_success
    trace_summary_correct_pass         = $trace.correct_pass
    trace_summary_buggy_fail           = $trace.buggy_fail
    trace_summary_strict_success       = $trace.strict_success
    gap_correct_pass                   = ([int]$trace.correct_pass - [int]$base.correct_pass)
    gap_buggy_fail                     = ([int]$trace.buggy_fail - [int]$base.buggy_fail)
    gap_strict_success                 = ([int]$trace.strict_success - [int]$base.strict_success)
  }
}

$overallBase = $cloudOverallCsv | Where-Object { $_.method -eq 'spec_plus_rtl' } | Select-Object -First 1
$overallTrace = $cloudOverallCsv | Where-Object { $_.method -eq 'spec_rtl_trace_summary' } | Select-Object -First 1
$gapRows += [pscustomobject]@{
  scope                              = 'overall'
  evaluation_level                   = 'candidate_row'
  baseline_method                    = 'spec_plus_rtl'
  compare_method                     = 'spec_rtl_trace_summary'
  baseline_cases                     = 23
  baseline_rows                      = $overallBase.rows
  baseline_correct_pass              = $overallBase.correct_pass
  baseline_buggy_fail                = $overallBase.buggy_fail
  baseline_strict_success            = $overallBase.strict_success
  trace_summary_correct_pass         = $overallTrace.correct_pass
  trace_summary_buggy_fail           = $overallTrace.buggy_fail
  trace_summary_strict_success       = $overallTrace.strict_success
  gap_correct_pass                   = ([int]$overallTrace.correct_pass - [int]$overallBase.correct_pass)
  gap_buggy_fail                     = ([int]$overallTrace.buggy_fail - [int]$overallBase.buggy_fail)
  gap_strict_success                 = ([int]$overallTrace.strict_success - [int]$overallBase.strict_success)
}

$gapPath = Join-Path $docsRoot 'trace_summary_vs_spec_plus_rtl_gap_candidate_level.csv'
$gapRows | Export-Csv -NoTypeInformation -Encoding UTF8 $gapPath

$resumeAttachment = Get-ChildItem -Path $attachmentsRoot -Recurse -Filter 'pasted-text.txt' |
  Where-Object { $_.FullName -match '8e442875-2f8e-489d-ba9b-1237e732da42' } |
  Select-Object -First 1 -ExpandProperty FullName
$parsedAttachmentRows = @()
if ($resumeAttachment -and (Test-Path $resumeAttachment)) {
  $parsedAttachmentRows = Parse-StrictEvalAttachment $resumeAttachment
}

$observedTraceSummaryRows = @($parsedAttachmentRows | Where-Object { $_.method -eq 'spec_rtl_trace_summary' })
$observedTraceSummaryPath = Join-Path $docsRoot 'resume_observed_trace_summary_candidate_rows.csv'
$observedTraceSummaryRows | Sort-Object case_name, candidate_index | Export-Csv -NoTypeInformation -Encoding UTF8 $observedTraceSummaryPath

$traceSummaryAttributionRows = foreach ($group in ($observedTraceSummaryRows | Group-Object case_name | Sort-Object Name)) {
  $case = $caseIndex[$group.Name]
  $rows = @($group.Group)
  $failRows = @($rows | Where-Object { $_.buggy_fail -ne 'True' -or $_.correct_pass -ne 'True' -or $_.strict_success -ne 'True' })
  if (-not $failRows) { continue }
  [pscustomobject]@{
    case_name                 = $group.Name
    bug_class                 = if ($case) { $case.bug_class } else { '' }
    observed_candidates       = $rows.Count
    any_correct_pass          = ConvertTo-BoolString(($rows | Where-Object { $_.correct_pass -eq 'True' }).Count -gt 0)
    any_buggy_fail            = ConvertTo-BoolString(($rows | Where-Object { $_.buggy_fail -eq 'True' }).Count -gt 0)
    any_strict_success        = ConvertTo-BoolString(($rows | Where-Object { $_.strict_success -eq 'True' }).Count -gt 0)
    failure_types_observed    = (($rows | ForEach-Object { $_.failure_type } | Sort-Object -Unique) -join ';')
    primary_attribution       = Get-PrimaryAttribution $rows
    evidence_scope            = 'resume_attachment_observed_candidates_only'
  }
}
$traceSummaryAttributionPath = Join-Path $docsRoot 'trace_summary_failure_attribution_resume_observed.csv'
$traceSummaryAttributionRows | Sort-Object case_name | Export-Csv -NoTypeInformation -Encoding UTF8 $traceSummaryAttributionPath

$traceOverfitObservedRows = @($parsedAttachmentRows | Where-Object { $_.failure_type -eq 'trace_overfit' } | ForEach-Object {
  $case = $caseIndex[$_.case_name]
  [pscustomobject]@{
    case_name       = $_.case_name
    bug_class       = if ($case) { $case.bug_class } else { '' }
    method          = $_.method
    candidate_index = $_.candidate_index
    evidence_scope  = 'resume_attachment_observed_candidates_only'
  }
})
$traceOverfitObservedPath = Join-Path $docsRoot 'trace_overfit_observed_from_resume_attachment.csv'
$traceOverfitObservedRows | Sort-Object case_name, method, candidate_index | Export-Csv -NoTypeInformation -Encoding UTF8 $traceOverfitObservedPath

$inventoryByBugClass = $cases | Group-Object bug_class | Sort-Object Name
$overfitLureCases = @($cases | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_.overfit_lure) } | ForEach-Object { $_.name })
$goldenPassCount = @($goldenStatusRows | Where-Object { $_.golden_ok -eq 'True' }).Count
$goldenConflictCount = @($goldenStatusRows | Where-Object { $_.status_note -like 'conflict*' }).Count
$antecedentOkCount = @($antecedentRows | Where-Object { $_.antecedent_coverage_ok -eq 'True' }).Count
$observedOverfitCaseNames = @($traceOverfitObservedRows | ForEach-Object { $_.case_name } | Sort-Object -Unique)

$observedOverfitText = if ($observedOverfitCaseNames.Count -gt 0) { $observedOverfitCaseNames -join ', ' } else { 'none observed locally' }
$goldenComment = if ($goldenConflictCount -gt 0) {
  'There are still local report consistency conflicts; see `golden_status_30cases.csv` for the affected cases.'
} else {
  'The latest local active-root golden stamp is fully consistent at 30/30.'
}

$markdownLines = @(
  '# Trace Summary Scale-Out Report (2026-06-21)',
  '',
  '## 1. Main Table',
  '',
  '- Source: cloud full-admitted iv12 rerun for `rtl_cases_real_admitted_20260619`.',
  '- Limitation: the deduped case-level `strict_eval_report_iv12.csv` is not present locally, so this package reports candidate-row summaries for the main method x bug_class table.',
  '- Evaluation subset size: 23 cases, 115 candidate rows. bug_class split: 12 combination_same_cycle, 11 temporal_cross_cycle.',
  '- Key gap (`spec_rtl_trace_summary - spec_plus_rtl`):',
  '  - combination_same_cycle: correct_pass +14, buggy_fail -2, strict_success +0',
  '  - temporal_cross_cycle: correct_pass -17, buggy_fail +4, strict_success +0',
  '  - overall: correct_pass -3, buggy_fail +2, strict_success +0',
  '- Readout: there is no stable class-specific breakout in favor of trace summary. Combination cases improve only on correct_pass but get worse on fail_on_buggy; temporal cases regress strongly on correct_pass. strict_success remains 0 everywhere.',
  '',
  '## 2. Dataset Body',
  '',
  '- The most complete local 30-case dataset body is `rtl_cases_real_active`: 14 combination_same_cycle and 16 temporal_cross_cycle.',
  '- Machine-readable inventory: `dataset_inventory_30cases.csv`.',
  "- Non-empty overfit_lure cases: $($overfitLureCases.Count).",
  '',
  '## 3. Golden Self-Check',
  '',
  "- Locally confirmed golden passes from `golden_sva_check_report.csv`: $goldenPassCount / $($cases.Count).",
  "- $goldenComment",
  '- Per-case status: `golden_status_30cases.csv`.',
  '',
  '## 4. Antecedent Coverage',
  '',
  "- Locally confirmed cases with ``buggy_antecedent_hits > 0``: $antecedentOkCount / $($cases.Count).",
  '- The locally recorded golden rows do show that bad traces actually hit the antecedent.',
  '- Per-case coverage: `antecedent_coverage_30cases.csv`.',
  '',
  '## 5. Overfit / Generalization',
  '',
  '- Cloud full-admitted aggregate reports `trace_overfit = 13`.',
  '- The full per-candidate cloud `strict_eval_report_iv12.csv` is not stored locally, so the complete 13-case list cannot be reconstructed from the workspace alone.',
  "- Observable real-RTL overfit cases retained in local resume logs: $observedOverfitText.",
  '- Observed rows: `trace_overfit_observed_from_resume_attachment.csv`.',
  '',
  '## 6. Trace Summary Failure Attribution',
  '',
  '- I extracted the retained resume-stage per-candidate log rows for method `spec_rtl_trace_summary` and aggregated them by case.',
  '- This is an observed subset, not the final full-admitted complete table. Even so, the dominant modes are `antecedent_not_triggered`, `bug_not_detected_on_buggy`, and `false_positive_on_correct`, not strict_success.',
  '- Attribution table: `trace_summary_failure_attribution_resume_observed.csv`.',
  '',
  '## 7. My Judgment',
  '',
  '- The scaled-up evidence currently supports "no robust advantage over spec+RTL" more than "real breakout on some bug class".',
  '- Temporal/cross-cycle cases do not split in favor of trace summary; they regress on correct_pass.',
  '- Combination/same-cycle cases gain correct_pass but lose fail_on_buggy, which looks more like drift/loosening than better bug capture.',
  '- With strict_success still at 0, there is no evidence yet that trace summary is simultaneously precise, bug-catching, non-vacuous, and held-out-stable.',
  '',
  '## Artifact Index',
  '',
  '- `dataset_inventory_30cases.csv`',
  '- `golden_status_30cases.csv`',
  '- `antecedent_coverage_30cases.csv`',
  '- `full_admitted_cloud_method_bugclass_candidate_level.csv`',
  '- `full_admitted_cloud_overall_candidate_level.csv`',
  '- `trace_summary_vs_spec_plus_rtl_gap_candidate_level.csv`',
  '- `resume_observed_trace_summary_candidate_rows.csv`',
  '- `trace_summary_failure_attribution_resume_observed.csv`',
  '- `trace_overfit_observed_from_resume_attachment.csv`'
)

$reportPath = Join-Path $docsRoot 'trace_summary_scaleout_report_20260621.md'
$markdownLines -join "`r`n" | Set-Content -Encoding UTF8 $reportPath

Write-Output "Wrote $inventoryPath"
Write-Output "Wrote $goldenStatusPath"
Write-Output "Wrote $antecedentPath"
Write-Output "Wrote $cloudSummaryPath"
Write-Output "Wrote $cloudOverallPath"
Write-Output "Wrote $gapPath"
Write-Output "Wrote $observedTraceSummaryPath"
Write-Output "Wrote $traceSummaryAttributionPath"
Write-Output "Wrote $traceOverfitObservedPath"
Write-Output "Wrote $reportPath"
