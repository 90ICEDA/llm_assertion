#!/usr/bin/env python3
import argparse
import base64
import html
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def pick_powershell() -> str:
    for candidate in ["powershell.exe", "pwsh.exe"]:
        if shutil.which(candidate):
            return candidate
    raise RuntimeError("Cannot find powershell.exe or pwsh.exe from this environment.")


def wsl_path_to_windows(path_text: str) -> str:
    text = path_text.strip()
    if text.startswith("/mnt/") and len(text) > 6 and text[5].isalpha() and text[6] == "/":
        drive = text[5].upper()
        rest = text[7:].replace("/", "\\")
        return f"{drive}:\\{rest}"
    return text


def resolve_ollama_override(cli_value: str | None) -> str:
    for candidate in [cli_value, os.environ.get("OLLAMA_EXE"), os.environ.get("OLLAMA_WINDOWS_EXE")]:
        if candidate and candidate.strip():
            return wsl_path_to_windows(candidate)
    return ""


def run_powershell(script: str, shell_bin: str, input_text: str = "") -> subprocess.CompletedProcess[str]:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return subprocess.run(
        [shell_bin, "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-EncodedCommand", encoded],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def clean_powershell_output(text: str) -> str:
    if not text.startswith("#< CLIXML"):
        return text
    error_parts = re.findall(r'<S S="Error">(.*?)</S>', text, flags=re.DOTALL)
    if not error_parts:
        return text
    cleaned = "".join(error_parts)
    cleaned = html.unescape(cleaned)
    cleaned = cleaned.replace("_x000D__x000A_", "\n")
    cleaned = cleaned.replace("_x000D_", "")
    return cleaned.strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bridge WSL/Linux prompt-file calls to a Windows Ollama CLI."
    )
    parser.add_argument("--model", required=True, help="Ollama model name.")
    parser.add_argument("--prompt-file", help="Prompt file path.")
    parser.add_argument(
        "--ollama-exe",
        help=(
            "Optional explicit Windows path to ollama.exe. Also accepted from "
            "OLLAMA_EXE or OLLAMA_WINDOWS_EXE."
        ),
    )
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Only probe whether a usable Windows ollama.exe can be found, then exit.",
    )
    args = parser.parse_args()

    shell_bin = pick_powershell()
    ollama_override = resolve_ollama_override(args.ollama_exe)

    if not args.probe and not args.prompt_file:
        parser.error("--prompt-file is required unless --probe is used.")

    prompt_text = ""
    if args.prompt_file:
        prompt_path = Path(args.prompt_file).resolve()
        prompt_text = prompt_path.read_text(encoding="utf-8")

    ps_script = f"""
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$prompt = [Console]::In.ReadToEnd()
$override = @'
{ollama_override}
'@.Trim()
$ollamaCmd = $null
if ($override) {{
    if (Test-Path $override) {{
        $ollamaCmd = $override
    }} else {{
        Write-Error "Explicit --ollama-exe path was not found: $override"
        exit 1
    }}
}}
if (-not $ollamaCmd) {{
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) {{
        $ollamaCmd = $cmd.Source
    }}
}}
if (-not $ollamaCmd) {{
    $whereHits = @(cmd.exe /d /c where ollama 2>$null)
    if ($whereHits.Count -gt 0) {{
        foreach ($hit in $whereHits) {{
            if ($hit -and (Test-Path $hit)) {{
                $ollamaCmd = $hit
                break
            }}
        }}
    }}
}}
if (-not $ollamaCmd) {{
    $appPathKeys = @(
        "HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\ollama.exe",
        "HKLM:\\Software\\Microsoft\\Windows\\CurrentVersion\\App Paths\\ollama.exe"
    )
    foreach ($key in $appPathKeys) {{
        if (Test-Path $key) {{
            $props = Get-ItemProperty $key -ErrorAction SilentlyContinue
            if ($props.'(default)' -and (Test-Path $props.'(default)')) {{
                $ollamaCmd = $props.'(default)'
                break
            }}
        }}
    }}
}}
if (-not $ollamaCmd) {{
    $candidates = @(
        "C:\\Users\\没有惊喜\\AppData\\Local\\Programs\\Ollama\\ollama.exe",
        "$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe",
        "$env:LOCALAPPDATA\\Programs\\Ollama\\resources\\ollama.exe",
        "$env:ProgramFiles\\Ollama\\ollama.exe",
        "$env:ProgramFiles(x86)\\Ollama\\ollama.exe",
        "$env:LOCALAPPDATA\\Microsoft\\WinGet\\Links\\ollama.exe",
        "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\ollama.exe",
        "$env:USERPROFILE\\AppData\\Local\\Microsoft\\WinGet\\Links\\ollama.exe",
        "$env:USERPROFILE\\AppData\\Local\\Microsoft\\WindowsApps\\ollama.exe",
        "$env:USERPROFILE\\scoop\\shims\\ollama.exe",
        "$env:USERPROFILE\\scoop\\apps\\ollama\\current\\ollama.exe"
    )
    foreach ($candidate in $candidates) {{
        if (Test-Path $candidate) {{
            $ollamaCmd = $candidate
            break
        }}
    }}
}}
if (-not $ollamaCmd) {{
    $checked = @(
        "PATH:Get-Command ollama",
        "PATH:cmd.exe /c where ollama",
        "App Paths:HKCU/HKLM ...\\App Paths\\ollama.exe",
        "$env:LOCALAPPDATA\\Programs\\Ollama\\ollama.exe",
        "$env:LOCALAPPDATA\\Programs\\Ollama\\resources\\ollama.exe",
        "$env:ProgramFiles\\Ollama\\ollama.exe",
        "$env:ProgramFiles(x86)\\Ollama\\ollama.exe",
        "$env:LOCALAPPDATA\\Microsoft\\WinGet\\Links\\ollama.exe",
        "$env:LOCALAPPDATA\\Microsoft\\WindowsApps\\ollama.exe",
        "$env:USERPROFILE\\scoop\\shims\\ollama.exe",
        "$env:USERPROFILE\\scoop\\apps\\ollama\\current\\ollama.exe"
    ) -join "; "
    Write-Error "Cannot locate ollama.exe on Windows. Checked: $checked . You can pass --ollama-exe C:\\path\\to\\ollama.exe."
    exit 1
}}
"""

    if args.probe:
        probe_script = ps_script + "\nWrite-Output \"[FOUND] $ollamaCmd\"\nexit 0\n"
        result = run_powershell(probe_script, shell_bin)
        sys.stdout.write(clean_powershell_output(result.stdout))
        return result.returncode

    ps_script += f"""
& $ollamaCmd run '{args.model}' $prompt
"""

    result = run_powershell(ps_script, shell_bin, input_text=prompt_text)
    if result.returncode != 0:
        raise RuntimeError(
            f"Windows Ollama CLI call failed for model '{args.model}'. Output:\n"
            f"{clean_powershell_output(result.stdout)}"
        )

    sys.stdout.write(clean_powershell_output(result.stdout))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
