$ErrorActionPreference='Stop'
Set-Location (Resolve-Path (Join-Path $PSScriptRoot '..'))
$root=(Get-Location).Path
$out=Join-Path $root 'deliverables/independent_blind_workspace_20260922'
$seal=@(Import-Csv (Join-Path $out 'SEAL_SHA256.csv'))
$actual=@(Get-ChildItem -LiteralPath $out -Recurse -File | Where-Object Name -ne 'SEAL_SHA256.csv')
if ($seal.Count -ne $actual.Count) { throw "File count differs: seal=$($seal.Count), actual=$($actual.Count)" }
foreach($r in $seal){
  $path=Join-Path $out $r.path
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing: $($r.path)" }
  $f=Get-Item -LiteralPath $path
  if ($f.Length -ne [long]$r.bytes) { throw "Size differs: $($r.path)" }
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $r.sha256) { throw "Hash differs: $($r.path)" }
}
$source=@(Import-Csv (Join-Path $out 'SOURCE_HASHES.csv'))
foreach($r in $source){
  $path=Join-Path $root $r.source_path
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Source missing: $($r.source_path)" }
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant() -ne $r.sha256) { throw "Source changed: $($r.source_path)" }
}
$parents=@(Import-Csv (Join-Path $out 'PARENTS.csv'))
if ($parents.Count -ne 30 -or @($parents.parent_bug_id|Sort-Object -Unique).Count -ne 30) { throw 'Parent frame invalid' }
foreach($p in $parents.parent_bug_id){ foreach($n in 1..7){ $s='{0:d2}' -f $n; foreach($f in @('request.json','prompt.txt','raw_response.json','candidate.sva')){if(-not(Test-Path (Join-Path $out "parents/$p/candidates/slot_$s/$f"))){throw "Missing candidate: $p $s $f"}}} }
$bad=@(Get-ChildItem -LiteralPath $out -Recurse -File | Where-Object {$_.Name -match '(?i)probe|feedback|chosen|rejected|failure.count|evidence\.json' -or $_.FullName -match 'slot_08'})
if($bad.Count){throw "Forbidden content paths: $($bad.FullName -join ', ')"}
"PASS: $($parents.Count) parents, 210 natural candidates, $($source.Count) source hashes, $($seal.Count) sealed files, zero mismatches"
