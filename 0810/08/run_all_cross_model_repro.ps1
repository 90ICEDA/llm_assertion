param([switch]$AllCases,[string]$OutputRoot="outputs/cross_model_repro_run",[int]$CandidatesPerCell=4)
$ErrorActionPreference="Stop"; $RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path; Set-Location $RepoRoot
$Python="C:\Users\没有惊喜\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"; if(-not(Test-Path $Python)){$Python=(Get-Command python).Source}
$env:OPENAI_API_KEY=(Get-Content .secrets/openai_api_key.txt -Raw).Trim();$env:ANTHROPIC_API_KEY=(Get-Content .secrets/anthropic_api_key.txt -Raw).Trim();$env:QWEN_API_KEY=(Get-Content .secrets/qwen_api_key.txt -Raw).Trim()
$base="https://api.highwayapi.ai/openai/chat/completions";$env:MULTIMODEL_OPENAI_BASE_URL=$base;$env:MULTIMODEL_OPENAI_MODEL="gpt-5.4";$env:MULTIMODEL_CLAUDE_PROVIDER="openai_compatible";$env:MULTIMODEL_CLAUDE_BASE_URL=$base;$env:MULTIMODEL_CLAUDE_MODEL="claude-opus-4-8";$env:MULTIMODEL_QWEN_PROVIDER="openai_compatible";$env:MULTIMODEL_QWEN_BASE_URL=$base;$env:MULTIMODEL_QWEN_MODEL="qwen/qwen-2.5-72b-instruct";$env:MULTIMODEL_FIXED_TEMPERATURE="0.2"
$data=Join-Path $OutputRoot "data";$direct=Join-Path $OutputRoot "direct";$two=Join-Path $OutputRoot "qwen_two_stage";$report=Join-Path $OutputRoot "report"
$prep=@("src/prepare_cross_model_benchmark.py","--source","rtl_cases_real_scale120","--out",$data);if($AllCases){$prep+="--all"};& $Python @prep;if($LASTEXITCODE){throw "data preparation failed"}
$args=@("src/run_multi_model_small_eval.py","--root",$data,"--output-dir",$direct,"--all-cases","--method","spec_rtl_raw_trace","--candidates-per-cell",$CandidatesPerCell,"--model","GPT","--model","Claude","--model","Qwen","--model","OpenMedium")
& $Python @args; if($LASTEXITCODE){throw "direct evaluation failed"}
& $Python src/run_qwen_two_stage_property_baseline.py --direct-dir $direct --cases-root $data --out-dir $two --candidates-per-cell $CandidatesPerCell; if($LASTEXITCODE){throw "Qwen two-stage failed"}
& $Python src/build_cross_model_repro_report.py --direct-dir $direct --two-stage-dir $two --cases-root $data --out-dir $report; if($LASTEXITCODE){throw "report/seal failed"}
& $Python src/audit_cross_model_run.py --direct-dir $direct --two-stage-dir $two --report-dir $report --out (Join-Path $report "run_all_stage_audit.json"); if($LASTEXITCODE){throw "run audit failed"}
Write-Host "COMPLETE: $report"
