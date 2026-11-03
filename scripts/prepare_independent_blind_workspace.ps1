$ErrorActionPreference = 'Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root = (Get-Location).Path
$out = Join-Path $root 'deliverables/independent_blind_workspace_20260922'
if (Test-Path (Join-Path $out 'SEAL_SHA256.csv')) { throw "Already sealed: $out" }
$rows = @(Import-Csv 'outputs/behavioral_preference_pilot_v1/selected_train_parents.csv')
if ($rows.Count -ne 30 -or @($rows.parent_bug_id | Sort-Object -Unique).Count -ne 30) { throw 'Parent frame is not 30 unique parents' }
$inventory = [System.Collections.Generic.List[object]]::new()
function Add-Source($source, $relative) {
  $src = Join-Path $root $source
  if (-not (Test-Path -LiteralPath $src -PathType Leaf)) { throw "Missing source: $source" }
  $dst = Join-Path $out $relative
  New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
  Copy-Item -LiteralPath $src -Destination $dst
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $src).Hash.ToLowerInvariant()
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $dst).Hash.ToLowerInvariant() -ne $hash) { throw "Hash mismatch: $source" }
  $inventory.Add([pscustomobject]@{copy_path=$relative.Replace('\','/');source_path=$source.Replace('\','/');bytes=(Get-Item -LiteralPath $src).Length;sha256=$hash})
}
$caseNames = @('buggy.v','correct.v','mutation.diff','rtl_mutation.diff','spec.md','STIMULUS_NOTES.md','case_metadata.json','hardness_evaluation.json','tb.v','tb_decoy.v','tb_holdout.v','waveform_bad.csv','waveform_good.csv','waveform_bad_decoy.csv','waveform_good_decoy.csv','waveform_bad_holdout.csv','waveform_good_holdout.csv','waveform_bad.vcd','waveform_good.vcd','waveform_bad_decoy.vcd','waveform_good_decoy.vcd','waveform_bad_holdout.vcd','waveform_good_holdout.vcd')
foreach ($r in $rows) {
  $p=$r.parent_bug_id; $base="$($r.dataset_root)/$p"
  foreach ($name in $caseNames) {
    $src="$base/$name"
    if (Test-Path -LiteralPath (Join-Path $root $src) -PathType Leaf) { Add-Source $src "parents/$p/bug/$name" }
  }
  foreach ($name in @('spec.txt','trace_bad.txt','trace_good.txt','trace_bad_holdout.txt','trace_good_holdout.txt','trace_summary.json','trace_summary.txt')) {
    $src="$base/experiment/$name"
    if (Test-Path -LiteralPath (Join-Path $root $src) -PathType Leaf) { Add-Source $src "parents/$p/bug/$name" }
  }
  foreach ($name in @('buggy.v','correct.v')) { if (-not (Test-Path (Join-Path $out "parents/$p/bug/$name"))) { throw "Missing RTL $p $name" } }
  if (-not (Test-Path (Join-Path $out "parents/$p/bug/mutation.diff")) -and -not (Test-Path (Join-Path $out "parents/$p/bug/rtl_mutation.diff"))) {
    $diff = & git -c core.autocrlf=false diff --no-index -- (Join-Path $root "$base/correct.v") (Join-Path $root "$base/buggy.v")
    if ($LASTEXITCODE -ne 1) { throw "Cannot derive patch for $p" }
    $diff | Set-Content -Encoding utf8 (Join-Path $out "parents/$p/bug/derived_mutation.diff")
  }
  foreach ($slot in 1..7) {
    $s='{0:d2}' -f $slot
    $gen="outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30/$p/slot_$s/attempt_01"
    foreach ($name in @('request.json','prompt.txt','raw_response.json','candidate.sva')) { Add-Source "$gen/$name" "parents/$p/candidates/slot_$s/$name" }
  }
}
Add-Source 'outputs/behavioral_preference_pilot_v1/selected_train_parents.csv' 'sources/selected_train_parents.csv'
Add-Source 'outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/parent_split_24_6.jsonl' 'sources/parent_split_24_6.jsonl'
$inventory | Sort-Object copy_path | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'SOURCE_HASHES.csv')
$rows | Select-Object parent_bug_id,source_project,bug_family,dataset_root,case_id | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'PARENTS.csv')
$readme = @'
# Independent blind review workspace

Frozen source frame: 30 unique parents from `sources/selected_train_parents.csv`; seven natural model candidate slots per parent (210 total). Slot 8 is excluded because its rendered assertion is a synthetic control. Candidate files contain only request, prompt, raw response, and rendered SVA. Bug folders contain RTL, specification, patch, hardness and waveform/trace evidence where present. For legacy scale120 cases without an original patch, `derived_mutation.diff` is generated from the selected source RTL pair; its source RTL hashes are in `SOURCE_HASHES.csv`. An absent hardness file means no per-case hardness evaluation was available at that source path.

`SOURCE_HASHES.csv` records byte hashes of every copied source. `SEAL_SHA256.csv` hashes every workspace file except itself; recheck with `scripts/verify_independent_blind_workspace.ps1` from the repository root. No old probe results, failure counts, chosen/rejected labels, or feedback files are included. This seal precedes any new review judgment.
'@
$readme | Set-Content -Encoding utf8 (Join-Path $out 'README.md')
$forbidden = Get-ChildItem -LiteralPath $out -Recurse -File | Where-Object { $_.Name -match '(?i)probe|feedback|chosen|rejected|failure.count|evidence\.json' }
if ($forbidden) { throw "Forbidden files: $($forbidden.FullName -join ', ')" }
$seal = Get-ChildItem -LiteralPath $out -Recurse -File | ForEach-Object { [pscustomobject]@{path=$_.FullName.Substring($out.Length+1).Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()} } | Sort-Object path
$seal | Export-Csv -NoTypeInformation -Encoding utf8 (Join-Path $out 'SEAL_SHA256.csv')
"sealed parents=$($rows.Count) natural_candidates=210 source_files=$($inventory.Count) sealed_files=$($seal.Count)"
