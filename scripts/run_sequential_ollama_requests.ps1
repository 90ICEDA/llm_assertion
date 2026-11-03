param(
    [string]$Root = "D:\AssertionForge-main1",
    [string]$OllamaUrl = "http://127.0.0.1:11435/api/chat",
    [int]$Attempt = 1,
    [int]$Slot = 0,
    [string]$GenerationDir = "sequential_generation_v2",
    [string]$MissingManifest = ""
)

$ErrorActionPreference = "Stop"
$indexPath = Join-Path $Root ("outputs\behavioral_preference_pilot_v1\{0}\request_index.json" -f $GenerationDir)
$index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
$records = $index.records | Where-Object { [int]$_.attempt -eq $Attempt }
if ($Slot -gt 0) { $records = $records | Where-Object { [int]$_.slot -eq $Slot } }
if ($MissingManifest) {
    $missingPath = if ([System.IO.Path]::IsPathRooted($MissingManifest)) { $MissingManifest } else { Join-Path $Root $MissingManifest }
    $missing = Get-Content -LiteralPath $missingPath -Raw | ConvertFrom-Json
    $needed = @{}
    foreach ($item in $missing.slots) { $needed[("{0}|{1}" -f $item.parent_bug_id, [int]$item.slot)] = $true }
    $records = $records | Where-Object { $needed.ContainsKey(("{0}|{1}" -f $_.parent_bug_id, [int]$_.slot)) }
}

foreach ($record in $records) {
    $requestPath = Join-Path $Root ($record.request_path -replace '/', '\')
    $attemptDir = Split-Path -Parent $requestPath
    $responsePath = Join-Path $attemptDir "raw_response.json"
    $transportLog = Join-Path $attemptDir "curl_transport.log"
    if (Test-Path -LiteralPath $responsePath) {
        Write-Host ("parent={0} slot={1} attempt={2} status=existing_response_skipped" -f `
            $record.parent_bug_id, $record.slot, $record.attempt)
        continue
    }
    $started = [DateTimeOffset]::UtcNow
    & curl.exe --silent --show-error --max-time 1800 `
        --header "Content-Type: application/json" `
        --data-binary "@$requestPath" --output $responsePath $OllamaUrl 2> $transportLog
    $exitCode = $LASTEXITCODE
    $elapsed = ([DateTimeOffset]::UtcNow - $started).TotalSeconds
    Write-Host ("parent={0} slot={1} attempt={2} exit={3} seconds={4:N3}" -f `
        $record.parent_bug_id, $record.slot, $record.attempt, $exitCode, $elapsed)
    if ($exitCode -ne 0) { throw "curl failed for $requestPath with exit code $exitCode" }
}
