#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

from sva_static_filter import analyze_sva


PROMPT_FILES = [
    ("prompt_1_spec_only.txt", "sva_1_spec_only.sv"),
    ("prompt_2_spec_plus_rtl.txt", "sva_2_spec_plus_rtl.sv"),
    ("prompt_3_spec_rtl_raw_trace.txt", "sva_3_spec_rtl_raw_trace.sv"),
    ("prompt_4_spec_rtl_trace_summary.txt", "sva_4_spec_rtl_trace_summary.sv"),
]

METHOD_ALIASES = {
    "1": "prompt_1_spec_only.txt",
    "2": "prompt_2_spec_plus_rtl.txt",
    "3": "prompt_3_spec_rtl_raw_trace.txt",
    "4": "prompt_4_spec_rtl_trace_summary.txt",
    "spec_only": "prompt_1_spec_only.txt",
    "spec_plus_rtl": "prompt_2_spec_plus_rtl.txt",
    "spec_rtl_raw_trace": "prompt_3_spec_rtl_raw_trace.txt",
    "spec_rtl_trace_summary": "prompt_4_spec_rtl_trace_summary.txt",
}

ASSERT_FULL_RE = re.compile(
    r"^\s*assert\s+property\s*\(\s*@\(\s*posedge\s+clk\s*\)\s*disable\s+iff\s*\(\s*!\s*rst_n\s*\)\s*"
    r"\((?P<ante>.*?)\)\s*(?P<op>\|->|\|=>)\s*\((?P<cons>.*?)\)\s*\)\s*;\s*$",
    re.IGNORECASE | re.DOTALL,
)

BANNED_SNIPPETS = [
    "next_state",
    "count_next",
    "count_prev",
    "$past",
    "##",
    "old(",
]

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
FATAL_INFRA_ERROR_SNIPPETS = [
    "cannot locate ollama.exe",
    "explicit --ollama-exe path was not found",
    "cannot find powershell.exe",
    "cannot find pwsh.exe",
    "cannot reach ollama at",
    "is reachable but model",
    "error loading model",
    "llama-server process has terminated",
    "500 internal server error",
    "model_not_found",
    "does not exist or you do not have access to it",
    "qwen api http 404",
]


def extract_assertion_line(text: str) -> str:
    # Remove ANSI escape/control sequences that may appear in TTY-style output.
    text = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", text)
    text = text.replace("\r", "")
    text = text.replace("```systemverilog", "").replace("```", "")
    m = re.search(r"assert\s+property\s*\(.*?\)\s*;", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    line = m.group(0)
    line = re.sub(r"\s+", " ", line).strip()
    return line


def strip_balanced_outer_parens(expr: str) -> str:
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        balanced = True
        for idx, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(expr) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        expr = expr[1:-1].strip()
    return expr


def split_top_level_implication(expr: str) -> Tuple[str, str, str]:
    depth = 0
    i = 0
    while i < len(expr) - 1:
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            if expr.startswith("|->", i):
                return expr[:i].strip(), "|->", expr[i + 3 :].strip()
            if expr.startswith("|=>", i):
                return expr[:i].strip(), "|=>", expr[i + 3 :].strip()
        i += 1
    return "", "", ""


def simplify_boolean_expr(expr: str) -> str:
    expr = strip_balanced_outer_parens(expr)
    left, op, right = split_top_level_implication(expr)
    if not op:
        return expr
    left_s = strip_balanced_outer_parens(left)
    right_s = strip_balanced_outer_parens(right)
    if normalize_expr(left_s) == normalize_expr(right_s):
        return left_s
    return ""


def normalize_assertion_candidate(text: str) -> str:
    line = extract_assertion_line(text)
    if not line:
        return ""
    if ASSERT_FULL_RE.fullmatch(line):
        return line

    m = re.fullmatch(
        r"^\s*assert\s+property\s*\(\s*@\(\s*posedge\s+clk\s*\)\s*disable\s+iff\s*\(\s*!\s*rst_n\s*\)\s*(?P<body>.*)\)\s*;\s*$",
        line,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return line

    body = strip_balanced_outer_parens(m.group("body"))
    ante, op, cons = split_top_level_implication(body)
    if not op:
        return line

    ante = simplify_boolean_expr(ante)
    cons = simplify_boolean_expr(cons)
    if not ante or not cons:
        return line

    fixed = (
        f"assert property (@(posedge clk) disable iff (!rst_n) "
        f"({ante}) {op} ({cons}));"
    )
    return re.sub(r"\s+", " ", fixed).strip()


def parse_trace_file(path: Path) -> List[Dict[str, int]]:
    rows: List[Dict[str, int]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or ":" not in line:
            continue
        _, payload = line.split(":", 1)
        row: Dict[str, int] = {}
        for item in payload.split(","):
            item = item.strip()
            if not item or "=" not in item:
                continue
            k, v = item.split("=", 1)
            row[k.strip()] = sv_value_to_int(v.strip())
        if row:
            rows.append(row)
    return rows


def extract_first_json_dict(text: str) -> Dict:
    text = text.strip()
    # Fast path: whole text is JSON
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    # Robust path: find first decodable JSON object in noisy text.
    decoder = json.JSONDecoder()
    for idx, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text[idx:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


def build_sva_from_json_obj(obj: Dict) -> Tuple[str, List[str]]:
    reasons = []
    if not isinstance(obj, dict):
        return "", ["JSON object is missing."]

    op = obj.get("op", "")
    ant = obj.get("antecedent", "")
    cons = obj.get("consequent", "")

    if not isinstance(op, str):
        op = ""
    if not isinstance(ant, str):
        ant = ""
    if not isinstance(cons, str):
        cons = ""

    op = op.strip()
    ant = ant.strip()
    cons = cons.strip()

    if op not in ("|->", "|=>"):
        reasons.append("JSON field op must be '|->' or '|=>'.")
    if not ant:
        reasons.append("JSON field antecedent is empty.")
    if not cons:
        reasons.append("JSON field consequent is empty.")

    if reasons:
        return "", reasons

    line = (
        f"assert property (@(posedge clk) disable iff (!rst_n) "
        f"({ant}) {op} ({cons}));"
    )
    line = re.sub(r"\s+", " ", line).strip()
    return line, []


def sv_literal_to_int(token: str) -> int:
    token = token.strip()
    m = re.fullmatch(r"(\d+)'([sS]?)([bBoOdDhH])([0-9a-fA-F_xXzZ]+)", token)
    if not m:
        return int(token, 0)
    base = m.group(3).lower()
    digits = m.group(4).replace("_", "")
    digits = re.sub(r"[xXzZ]", "0", digits)
    if base == "b":
        return int(digits, 2)
    if base == "o":
        return int(digits, 8)
    if base == "d":
        return int(digits, 10)
    return int(digits, 16)


def sv_value_to_int(token: str) -> int:
    token = token.strip()
    if token == "":
        return 0
    if re.fullmatch(r"[01xXzZ]+", token):
        token = re.sub(r"[xXzZ]", "0", token)
        return int(token, 2)
    if "'" in token:
        return sv_literal_to_int(token)
    return int(token, 0)


def normalize_expr(expr: str) -> str:
    return re.sub(r"\s+", "", expr)


def validate_sva(
    sva_line: str, allowed_signals: List[str], vector_signals: List[str] | None = None
) -> Tuple[bool, List[str]]:
    if not sva_line.strip():
        return False, ["Empty output."]

    line_l = sva_line.lower()
    for snippet in BANNED_SNIPPETS:
        if snippet.lower() in line_l:
            return False, [f"Contains banned snippet: {snippet}"]
    if re.search(r"\bS_[A-Za-z_]\w*\b", sva_line):
        return False, ["Contains banned state-symbol style name S_*."]

    result = analyze_sva(sva_line, allowed_signals, vector_signals)
    reasons = [reason.replace("_", " ") for reason in result["reasons"]]
    return bool(result["pass"]), reasons


def bool_expr_supports_trace_eval(sva_line: str) -> Tuple[bool, List[str]]:
    reasons = []
    m = ASSERT_FULL_RE.fullmatch(sva_line.strip())
    if not m:
        return False, ["Does not match strict single-line assertion format."]
    body = m.group("ante") + " " + m.group("cons")
    if "?" in body or ":" in body:
        reasons.append("Trace gate does not support ternary expressions yet.")
    return (len(reasons) == 0), reasons


def convert_sv_expr_to_python(expr: str, signal_names: List[str]) -> str:
    out = expr
    out = re.sub(
        r"\b(\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ_]+)\b",
        lambda m: str(sv_literal_to_int(m.group(1))),
        out,
    )

    # Protect slice/bit-select expansions from later bare-signal rewriting.
    placeholders: Dict[str, str] = {}

    def repl_slice(match):
        key = f"__PH_{len(placeholders)}__"
        placeholders[key] = f'sl("{match.group(1)}", {match.group(2)}, {match.group(3)})'
        return key

    def repl_bit(match):
        key = f"__PH_{len(placeholders)}__"
        placeholders[key] = f'bt("{match.group(1)}", {match.group(2)})'
        return key

    out = re.sub(r"\b([A-Za-z_]\w*)\[(\d+):(\d+)\]", repl_slice, out)
    out = re.sub(r"\b([A-Za-z_]\w*)\[(\d+)\]", repl_bit, out)

    for sig in sorted(signal_names, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(sig)}\b", f'sg("{sig}")', out)

    for key, value in placeholders.items():
        out = out.replace(key, value)

    out = out.replace("&&", " and ")
    out = out.replace("||", " or ")
    out = re.sub(r"!(?!=)", " not ", out)
    return out


def eval_trace_expr(expr: str, row: Dict[str, int], signal_names: List[str]) -> int:
    py_expr = convert_sv_expr_to_python(expr, signal_names)

    def sg(name: str) -> int:
        return int(row.get(name, 0))

    def bt(name: str, idx: int) -> int:
        return (int(row.get(name, 0)) >> int(idx)) & 1

    def sl(name: str, hi: int, lo: int) -> int:
        hi_i = int(hi)
        lo_i = int(lo)
        width = hi_i - lo_i + 1
        mask = (1 << width) - 1
        return (int(row.get(name, 0)) >> lo_i) & mask

    val = eval(py_expr, {"__builtins__": {}}, {"sg": sg, "bt": bt, "sl": sl})
    return int(bool(val))


def score_candidate_on_trace(
    sva_line: str,
    good_rows: List[Dict[str, int]],
    bad_rows: List[Dict[str, int]],
    signal_names: List[str],
) -> Tuple[int, Dict[str, int], List[str]]:
    ok, reasons = bool_expr_supports_trace_eval(sva_line)
    if not ok:
        return -1000, {}, reasons

    m = ASSERT_FULL_RE.fullmatch(sva_line.strip())
    assert m is not None
    ante = m.group("ante")
    cons = m.group("cons")
    op = m.group("op")

    def run(rows: List[Dict[str, int]]) -> Tuple[int, int]:
        hits = 0
        fails = 0
        if op == "|->":
            for row in rows:
                if eval_trace_expr(ante, row, signal_names):
                    hits += 1
                    if not eval_trace_expr(cons, row, signal_names):
                        fails += 1
        else:
            for idx in range(len(rows) - 1):
                if eval_trace_expr(ante, rows[idx], signal_names):
                    hits += 1
                    if not eval_trace_expr(cons, rows[idx + 1], signal_names):
                        fails += 1
        return hits, fails

    try:
        good_hits, good_fails = run(good_rows)
        bad_hits, bad_fails = run(bad_rows)
    except Exception as e:
        return -1000, {}, [f"Trace gate eval error: {e}"]
    total_hits = good_hits + bad_hits

    score = 0
    if total_hits > 0:
        score += 10
    if good_fails == 0:
        score += 20
    if bad_fails > 0:
        score += 40
    score += min(bad_fails, 5)
    score -= min(good_fails, 5) * 10

    metrics = {
        "good_hits": good_hits,
        "good_fails": good_fails,
        "bad_hits": bad_hits,
        "bad_fails": bad_fails,
    }
    return score, metrics, []


def run_llm_command(command_template: str, prompt_path: Path) -> str:
    cmd = command_template.format(prompt_file=str(prompt_path))
    result = subprocess.run(
        cmd,
        shell=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LLM command failed for {prompt_path}:\n{result.stdout}")
    return extract_assertion_line(result.stdout.strip())


def is_fatal_infra_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(snippet in lowered for snippet in FATAL_INFRA_ERROR_SNIPPETS)


def resolve_ollama_base_url(cli_value: str | None) -> str:
    for candidate in [cli_value, os.environ.get("OLLAMA_BASE_URL"), os.environ.get("OLLAMA_HOST")]:
        if candidate and candidate.strip():
            return candidate.strip().rstrip("/")
    return DEFAULT_OLLAMA_BASE_URL


def summarize_http_error_body(body: str) -> str:
    text = (body or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except Exception:
        return text[:500]
    if isinstance(data, dict):
        for key in ["error", "message", "detail"]:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return text[:500]


def ollama_generate_once(model: str, prompt: str, temperature: float, ollama_base_url: str) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature},
    }
    req = urllib.request.Request(
        f"{ollama_base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        detail = summarize_http_error_body(body)
        msg = f"Ollama HTTP {e.code}"
        if detail:
            msg += f": {detail}"
        raise RuntimeError(msg) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach Ollama at {ollama_base_url}: {e}"
        ) from e
    data = json.loads(body)
    return data.get("response", "").strip()


def check_ollama_available(model: str, ollama_base_url: str) -> None:
    req = urllib.request.Request(
        f"{ollama_base_url}/api/tags",
        headers={"Content-Type": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as e:
        raise RuntimeError(
            "Cannot reach Ollama at "
            f"{ollama_base_url}. Start Ollama with 'ollama serve' or launch the Ollama app. "
            f"Original error: {e}"
        ) from e

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama at {ollama_base_url} returned invalid JSON from /api/tags."
        ) from e

    models = data.get("models", [])
    model_names = {
        entry.get("name", "")
        for entry in models
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    }
    if model not in model_names:
        available = ", ".join(sorted(name for name in model_names if name)) or "(none)"
        raise RuntimeError(
            f"Ollama is reachable but model '{model}' is not installed. "
            f"Available models: {available}. Install it with 'ollama pull {model}'."
        )


def build_json_prompt(
    base_prompt: str, allowed_signals: List[str], feedback: str = ""
) -> str:
    allowed = ", ".join(allowed_signals)
    fb = f"\nPrevious rejection feedback:\n{feedback}\n" if feedback else ""
    return (
        "Return STRICT JSON only. No markdown. No extra text.\n"
        "Schema:\n"
        "{\n"
        '  "op": "|-> or |=>",\n'
        '  "antecedent": "boolean expression",\n'
        '  "consequent": "boolean expression"\n'
        "}\n"
        "Rules:\n"
        "- Use only allowed signals.\n"
        "- Do not use next_state, count_next, count_prev, old(...), S_* names.\n"
        "- No nested implication operators inside expressions.\n"
        "- For register updates, prefer |=>.\n"
        f"- Allowed signals: {allowed}\n"
        f"{fb}\n"
        "Task context:\n"
        f"{base_prompt}"
    )


def build_format_repair_prompt(
    base_prompt: str,
    invalid_output: str,
    allowed_signals: List[str],
    reasons: List[str],
) -> str:
    allowed = ", ".join(allowed_signals)
    reason_text = "; ".join(reasons) if reasons else "previous output did not satisfy validation"
    return (
        "Return exactly one SystemVerilog assertion line and nothing else.\n"
        "You are repairing a nearly-correct assertion so that it matches the required syntax.\n"
        "Hard requirements:\n"
        "- exactly one line in this exact outer shape:\n"
        "  assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));\n"
        "  or\n"
        "  assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |=> (<CONSEQUENT>));\n"
        "- antecedent and consequent must be plain boolean expressions only\n"
        "- do not place |-> or |=> inside antecedent or consequent\n"
        "- use only allowed signals\n"
        "- do not use next_state, count_next, count_prev, old(...), S_* names, or other internal names\n"
        "- if the invalid candidate uses illegal names, replace them with the closest legal condition over allowed signals\n"
        f"- allowed signals: {allowed}\n"
        f"Validation errors to fix: {reason_text}\n\n"
        "Invalid candidate:\n"
        f"{invalid_output}\n\n"
        "Original task context:\n"
        f"{base_prompt}"
    )


def generate_one_ollama_candidate(
    model: str,
    prompt_path: Path,
    allowed_signals: List[str],
    vector_signals: List[str],
    max_attempts: int,
    ollama_base_url: str,
) -> Tuple[str, List[str]]:
    prompt = prompt_path.read_text(encoding="utf-8")
    reasons: List[str] = []
    last_raw_output = ""

    # Stage 1: JSON generation + local assembly.
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        json_prompt = build_json_prompt(prompt, allowed_signals, feedback=feedback)
        raw = ollama_generate_once(
            model, json_prompt, temperature=(0.2 if attempt == 1 else 0.0), ollama_base_url=ollama_base_url
        )
        last_raw_output = raw
        obj = extract_first_json_dict(raw)
        candidate, json_reasons = build_sva_from_json_obj(obj)
        if candidate:
            ok, reasons = validate_sva(candidate, allowed_signals, vector_signals)
            if ok:
                return candidate, []
            feedback = "Validation failed: " + "; ".join(reasons)
            continue
        reasons = json_reasons or ["Failed to parse valid JSON object."]
        feedback = "; ".join(reasons)

    # Stage 2 fallback: direct assertion generation (legacy path).
    bad_candidate = ""
    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            direct_prompt = prompt + (
                "\n\nOutput exactly one assertion line only:\n"
                "assert property (@(posedge clk) disable iff (!rst_n) "
                "(<ANTECEDENT>) |-> (<CONSEQUENT>));"
            )
            raw = ollama_generate_once(model, direct_prompt, temperature=0.2, ollama_base_url=ollama_base_url)
        else:
            repair_prompt = (
                "Regenerate exactly one assertion line.\n"
                f"Rejected assertion: {bad_candidate}\n"
                f"Reasons: {'; '.join(reasons)}\n"
                "Hard constraints:\n"
                "- exactly one 'assert property (...) ;'\n"
                "- only allowed signals: " + ", ".join(allowed_signals) + "\n"
                "- do not use next_state, count_next, count_prev, old(...), S_* names\n"
                "- no nested implication in antecedent/consequent\n"
                "- prefer |=> for register-update checks\n\n"
                "Base prompt:\n" + prompt
            )
            raw = ollama_generate_once(model, repair_prompt, temperature=0.0, ollama_base_url=ollama_base_url)

        last_raw_output = raw
        candidate = normalize_assertion_candidate(raw)
        ok, reasons = validate_sva(candidate, allowed_signals, vector_signals)
        if ok:
            return candidate, []
        bad_candidate = candidate if candidate else "(empty)"

    # Stage 3 fallback: syntax-repair pass on the last raw output.
    repair_seed = bad_candidate if bad_candidate and bad_candidate != "(empty)" else last_raw_output
    if repair_seed:
        for _ in range(2):
            repair_prompt = build_format_repair_prompt(
                prompt, repair_seed, allowed_signals, reasons
            )
            raw = ollama_generate_once(model, repair_prompt, temperature=0.0, ollama_base_url=ollama_base_url)
            last_raw_output = raw
            candidate = normalize_assertion_candidate(raw)
            ok, reasons = validate_sva(candidate, allowed_signals, vector_signals)
            if ok:
                return candidate, []
            repair_seed = candidate if candidate else raw

    return "", reasons


def load_cases(root: Path):
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    return manifest["cases"]


def infer_vector_signals(rows: List[Dict[str, int]]) -> List[str]:
    vector_signals = set()
    for row in rows:
        for key in row.keys():
            m = re.match(r"^([A-Za-z_]\w*)\[\d+(?::\d+)?\]$", key)
            if m:
                vector_signals.add(m.group(1))
    return sorted(vector_signals)


def candidate_output_name(base_name: str, index: int) -> str:
    stem = Path(base_name).stem
    suffix = Path(base_name).suffix or ".sv"
    return f"{stem}__cand_{index:02d}{suffix}"


def parse_methods_arg(value: str | None) -> List[str] | None:
    if value is None:
        return None
    selected: List[str] = []
    for token in value.split(","):
        key = token.strip()
        if not key:
            continue
        if key not in METHOD_ALIASES:
            raise ValueError(f"Unsupported method selector: {key}")
        resolved = METHOD_ALIASES[key]
        if resolved not in selected:
            selected.append(resolved)
    return selected or None


def main():
    parser = argparse.ArgumentParser(
        description="Generate SVA files from prepared prompts using an external LLM command."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument(
        "--llm-command",
        help=(
            "Shell command template that returns one SVA line to stdout. "
            "Use {prompt_file} placeholder. Example: "
            "\"my_llm_cli --prompt-file {prompt_file}\""
        ),
    )
    parser.add_argument(
        "--ollama-model",
        help=(
            "Use local Ollama model directly. Example: qwen2.5-coder:7b-instruct. "
            "If set, this is used instead of --llm-command."
        ),
    )
    parser.add_argument(
        "--ollama-base-url",
        help=(
            "Optional Ollama base URL, for example http://127.0.0.1:11434 or "
            "http://172.27.80.1:11434. Defaults to OLLAMA_BASE_URL/OLLAMA_HOST env var, "
            "then http://127.0.0.1:11434."
        ),
    )
    parser.add_argument("--case", help="Optional single case.")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=4,
        help="Max regeneration attempts per prompt when validation fails (default: 4).",
    )
    parser.add_argument(
        "--num-candidates",
        type=int,
        default=5,
        help="Generate this many candidates per prompt and pick the best by trace gate (default: 5).",
    )
    parser.add_argument(
        "--methods",
        help="Optional comma-separated method filter. Example: 3,4 or spec_rtl_raw_trace,spec_rtl_trace_summary.",
    )
    args = parser.parse_args()

    if not args.ollama_model and not args.llm_command:
        parser.error("Provide either --ollama-model or --llm-command.")
    if args.ollama_model and args.llm_command:
        parser.error("Use only one of --ollama-model or --llm-command.")

    root = Path(args.root).resolve()
    case_entries = load_cases(root)
    selected_prompt_files = parse_methods_arg(args.methods)
    if args.case:
        case_entries = [c for c in case_entries if c["name"] == args.case]

    if args.ollama_model:
        ollama_base_url = resolve_ollama_base_url(args.ollama_base_url)
        check_ollama_available(args.ollama_model, ollama_base_url)
    else:
        ollama_base_url = ""

    error_count = 0
    candidate_error_count = 0
    fatal_abort_error = ""

    for c in case_entries:
        case_name = c["name"]
        allowed_signals = c["key_signals"]
        case_dir = root / case_name
        prompts_dir = case_dir / "experiment" / "prompts"
        gen_dir = case_dir / "experiment" / "generated"
        gen_dir.mkdir(parents=True, exist_ok=True)
        good_rows = parse_trace_file(case_dir / "experiment" / "trace_good.txt")
        bad_rows = parse_trace_file(case_dir / "experiment" / "trace_bad.txt")
        vector_signals = infer_vector_signals(good_rows + bad_rows)

        for p_name, out_name in PROMPT_FILES:
            if selected_prompt_files is not None and p_name not in selected_prompt_files:
                continue
            p = prompts_dir / p_name
            if not p.exists():
                print(f"[SKIP] missing prompt: {p}")
                continue
            produced = 0
            for cand_idx in range(1, args.num_candidates + 1):
                out_path = gen_dir / candidate_output_name(out_name, cand_idx)
                try:
                    if args.ollama_model:
                        sva, rej_reasons = generate_one_ollama_candidate(
                            args.ollama_model,
                            p,
                            allowed_signals,
                            vector_signals,
                            args.max_attempts,
                            ollama_base_url,
                        )
                        if not sva:
                            last_reasons = rej_reasons
                            raise RuntimeError(
                                "No valid assertion after retries: " + "; ".join(last_reasons)
                            )
                        score, metrics, _trace_reasons = score_candidate_on_trace(
                            sva, good_rows, bad_rows, allowed_signals
                        )
                    else:
                        sva = run_llm_command(args.llm_command, p)
                        ok, rej_reasons = validate_sva(
                            sva, allowed_signals, vector_signals
                        )
                        if not ok:
                            raise RuntimeError("Validation failed: " + "; ".join(rej_reasons))
                        score, metrics = 0, {}

                    if not sva:
                        raise RuntimeError("No valid assertion after retries.")

                    out_path.write_text(sva + "\n", encoding="utf-8", newline="\n")
                    produced += 1
                    print(
                        f"[OK] {case_name}: {out_path.name} "
                        f"(score={score} good_hits={metrics.get('good_hits', 0)} "
                        f"bad_hits={metrics.get('bad_hits', 0)})"
                    )
                except Exception as e:
                    candidate_error_count += 1
                    if is_fatal_infra_error(str(e)):
                        fatal_abort_error = str(e)
                    out_path.write_text(
                        f"// GENERATION_ERROR: {e}\n",
                        encoding="utf-8",
                        newline="\n",
                    )
                    print(f"[ERR] {case_name}: {out_path.name} -> {e}")
                    if fatal_abort_error:
                        break
            if fatal_abort_error:
                print("[FATAL] Aborting remaining generation because the LLM backend is unavailable.")
                break
            if produced != args.num_candidates:
                error_count += 1
                print(
                    f"[WARN] {case_name}: {out_name} produced {produced}/{args.num_candidates} "
                    "valid candidates; remaining slots were written as GENERATION_ERROR placeholders."
                )
        if fatal_abort_error:
            break

    if fatal_abort_error:
        raise SystemExit(
            "LLM generation aborted due to infrastructure error:\n"
            f"{fatal_abort_error}"
        )
    if error_count or candidate_error_count:
        print(
            f"[WARN] Generation completed with {candidate_error_count} candidate error(s) "
            f"across {error_count} prompt-method(s). Placeholder files were written so evaluation can continue."
        )


if __name__ == "__main__":
    main()
