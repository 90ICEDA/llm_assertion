$ErrorActionPreference = 'Stop'

param(
  [string]$HostName = 'connect.westb.seetacloud.com',
  [int]$Port = 11112,
  [string]$User = 'root',
  [string]$RemotePath = '/root/AssertionForge-main/rtl_cases_real_admitted_20260619/strict_eval_report_iv12.csv',
  [string]$LocalDir = 'rtl_cases_real_admitted_20260619',
  [string]$LocalName = 'strict_eval_report_iv12.csv'
)

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$targetDir = Join-Path $repoRoot $LocalDir
$targetPath = Join-Path $targetDir $LocalName

New-Item -ItemType Directory -Force -Path $targetDir | Out-Null

$scp = (Get-Command scp.exe -ErrorAction Stop).Source
$sourceSpec = "${User}@${HostName}:${RemotePath}"

Write-Output "[INFO] Pulling $sourceSpec"
Write-Output "[INFO] Saving to $targetPath"

& $scp -P $Port $sourceSpec $targetPath

if (-not (Test-Path $targetPath)) {
  throw "SCP completed but target file is missing: $targetPath"
}

$size = (Get-Item $targetPath).Length
Write-Output "[DONE] Synced strict report: $targetPath ($size bytes)"
