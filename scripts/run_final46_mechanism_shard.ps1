param(
    [Parameter(Mandatory=$true)][ValidateSet('GPT','Claude','Qwen')][string]$Model,
    [Parameter(Mandatory=$true)][ValidateSet('trace','rtl')][string]$Family
)
$ErrorActionPreference='Stop'
$repo=Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = if ($env:ASSERTIONFORGE_PYTHON) { $env:ASSERTIONFORGE_PYTHON } else {
    Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}
if(-not (Test-Path -LiteralPath $python)){throw "Python runtime not found: $python"}
$root=Join-Path $repo 'rtl_cases_real_scale210_independent_next'
$out=Join-Path $repo "outputs\final46_mechanism_controls\$Family\$Model"
$temporal=Join-Path $repo 'outputs\final46_main_experiment\temporal_abstractions.json'
New-Item -ItemType Directory -Force -Path $out|Out-Null

$env:MULTIMODEL_OPENAI_MODEL='gpt-5.4'
$env:MULTIMODEL_OPENAI_BASE_URL='https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_CLAUDE_PROVIDER='openai_compatible';$env:MULTIMODEL_CLAUDE_MODEL='claude-opus-4-8';$env:MULTIMODEL_CLAUDE_BASE_URL='https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_QWEN_PROVIDER='openai_compatible';$env:MULTIMODEL_QWEN_MODEL='qwen/qwen-2.5-72b-instruct';$env:MULTIMODEL_QWEN_BASE_URL='https://api.highwayapi.ai/openai/chat/completions'
$env:MULTIMODEL_OPENAI_MAX_RETRIES='8';$env:MULTIMODEL_CLAUDE_MAX_RETRIES='8';$env:MULTIMODEL_QWEN_MAX_RETRIES='8'
$env:MULTIMODEL_OPENAI_RETRY_BACKOFF_SEC='10';$env:MULTIMODEL_CLAUDE_RETRY_BACKOFF_SEC='10';$env:MULTIMODEL_QWEN_RETRY_BACKOFF_SEC='10'
$env:MULTIMODEL_SEED='20260808';$env:MULTIMODEL_FIXED_TEMPERATURE='0.2'

if($Family -eq 'trace'){
    $methods=@(
        'spec_rtl_trace_good_only','spec_rtl_trace_bad_only','spec_rtl_trace_local_window',
        'spec_rtl_trace_signal_subset','spec_rtl_trace_noise_signals','spec_rtl_trace_format_perturbed',
        'spec_rtl_trace_wrong_pairing','spec_rtl_temporal_no_trigger','spec_rtl_temporal_no_delay',
        'spec_rtl_temporal_no_polarity','spec_rtl_temporal_no_duration',
        'spec_rtl_temporal_strict_no_trigger','spec_rtl_temporal_strict_no_delay',
        'spec_rtl_temporal_strict_no_polarity','spec_rtl_temporal_strict_no_duration'
    )
    $args=@((Join-Path $repo 'src\run_trace_representation_ablation.py'),'--root',$root,'--output-dir',$out,'--all-cases','--model',$Model,'--temporal-summary-json',$temporal,'--candidates-per-cell','4','--resume')
} else {
    $methods=@(
        'spec_rtl_interface','spec_rtl_one_hop_slice','spec_rtl_two_hop_slice',
        'spec_rtl_signal_list_two_hop_slice','spec_rtl_random_slice','spec_rtl_wrong_signal_list'
    )
    $args=@((Join-Path $repo 'src\run_rtl_context_ablation.py'),'--root',$root,'--output-dir',$out,'--all-cases','--model',$Model,'--candidates-per-cell','4','--resume')
}
foreach($method in $methods){$args += @('--method',$method)}
& $python @args
if($LASTEXITCODE-ne0){throw "$Family/$Model failed $LASTEXITCODE"}
@{status='complete';family=$Family;model=$Model;completed_at=(Get-Date).ToString('o')}|ConvertTo-Json|Set-Content -Encoding utf8 (Join-Path $out 'run_status.json')
