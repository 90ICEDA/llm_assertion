from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import socket
import ssl
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_trace_abstraction_prototype import (  # noqa: E402
    CASES_ROOT as DEFAULT_TRACEABS_CASES_ROOT,
    SELECTED_CASES as DEFAULT_ABSTRACTED_SELECTED_CASES,
    extract_rtl_from_prompt,
    extract_sva_candidates,
    extract_waveform_guidance,
    make_prompt_bundle,
    parse_allowed_signals,
    probe_property_support,
    read_text,
    run_case_eval,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / THREAD_ID / "multi_model_eval_data"
SECRETS_DIR = ROOT / ".secrets"
OPENAI_CHAT_URL = os.environ.get(
    "MULTIMODEL_OPENAI_BASE_URL",
    "https://api.openai.com/v1/chat/completions",
)
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
ANTHROPIC_MESSAGES_URL = os.environ.get(
    "MULTIMODEL_CLAUDE_BASE_URL",
    "https://api.anthropic.com/v1/messages",
)

REPRESENTATIVE_CASE_IDS = [
    "case101_prim_onehot_multihot_suppressed",
    "case104_prim_fifo_full_early",
    "case112_prim_intr_test_pulse_dropped",
    "case125_prim_fifo_wrap_late",
    "case135_prim_intr_enable_mask_ignored",
]

MODEL_SPECS: list[dict[str, Any]] = [
    {
        "model_label": "GPT",
        "provider": "openai",
        "model_name": os.environ.get("MULTIMODEL_OPENAI_MODEL", "gpt-4.1"),
        "api_key_env": "OPENAI_API_KEY",
    },
    {
        "model_label": "Claude",
        "provider": os.environ.get("MULTIMODEL_CLAUDE_PROVIDER", "anthropic"),
        "model_name": os.environ.get("MULTIMODEL_CLAUDE_MODEL", "claude-sonnet-4-5"),
        "api_key_env": "ANTHROPIC_API_KEY",
        "key_file_name": "anthropic_api_key.txt",
        "relay_base_url_env": "MULTIMODEL_CLAUDE_BASE_URL",
        "relay_auth_scheme_env": "MULTIMODEL_CLAUDE_AUTH_SCHEME",
        "relay_extra_headers_env": "MULTIMODEL_CLAUDE_EXTRA_HEADERS_JSON",
        "relay_max_retries_env": "MULTIMODEL_CLAUDE_MAX_RETRIES",
        "relay_retry_backoff_env": "MULTIMODEL_CLAUDE_RETRY_BACKOFF_SEC",
    },
    {
        "model_label": "Qwen",
        "provider": os.environ.get("MULTIMODEL_QWEN_PROVIDER", "ollama"),
        "model_name": os.environ.get("MULTIMODEL_QWEN_MODEL", os.environ.get("MULTIMODEL_OLLAMA_MODEL", "qwen2.5-coder:7b-instruct")),
        "base_url": os.environ.get("MULTIMODEL_QWEN_OLLAMA_URL", os.environ.get("MULTIMODEL_OLLAMA_URL", OLLAMA_CHAT_URL)),
        "api_key_env": "QWEN_API_KEY",
        "key_file_name": "qwen_api_key.txt",
        "relay_base_url_env": "MULTIMODEL_QWEN_BASE_URL",
        "relay_auth_scheme_env": "MULTIMODEL_QWEN_AUTH_SCHEME",
        "relay_extra_headers_env": "MULTIMODEL_QWEN_EXTRA_HEADERS_JSON",
        "relay_max_retries_env": "MULTIMODEL_QWEN_MAX_RETRIES",
        "relay_retry_backoff_env": "MULTIMODEL_QWEN_RETRY_BACKOFF_SEC",
    },
    {
        "model_label": "OpenMedium",
        "provider": "ollama",
        "model_name": os.environ.get("MULTIMODEL_OPEN_MEDIUM_MODEL", "qwen2.5-coder:7b-instruct"),
        "base_url": os.environ.get("MULTIMODEL_OPEN_MEDIUM_URL", OLLAMA_CHAT_URL),
        "api_key_env": "OPEN_MEDIUM_UNUSED",
    },
]

METHOD_SPECS: list[dict[str, str]] = [
    {
        "method": "spec_rtl_only",
        "trace_input_label": "No waveform trace",
    },
    {
        "method": "spec_rtl_raw_trace",
        "trace_input_label": "Raw good/bad trace",
    },
    {
        "method": "spec_rtl_trace_summary",
        "trace_input_label": "Normal trace summary",
    },
    {
        "method": "spec_rtl_abstracted_trace_summary",
        "trace_input_label": "Abstracted trace summary",
    },
]

METHOD_ALIASES = {
    "spec_only": "spec_only",
    "spec_plus_rtl": "spec_plus_rtl",
    "spec_rtl_only": "spec_plus_rtl",
    "spec_rtl_raw_trace": "spec_rtl_raw_trace",
    "spec_rtl_trace_summary": "spec_rtl_trace_summary",
    "spec_rtl_abstracted_trace_summary": "spec_rtl_abstracted_trace_summary",
}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def redact_secrets(text: str) -> str:
    redacted = str(text or "")
    redacted = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-***REDACTED***", redacted)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._-]{12,}", "Bearer ***REDACTED***", redacted, flags=re.IGNORECASE)
    return redacted


def parse_int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def parse_float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def is_transient_http_status(code: int) -> bool:
    return code in {408, 409, 425, 429} or 500 <= code < 600


def is_transient_url_error(exc: urllib.error.URLError) -> bool:
    reason = exc.reason
    if isinstance(reason, (TimeoutError, socket.timeout, ConnectionResetError, ConnectionAbortedError, ssl.SSLError)):
        return True
    reason_text = str(reason).lower()
    transient_markers = [
        "timed out",
        "timeout",
        "tempor",
        "connection reset",
        "connection aborted",
        "unexpected eof",
        "eof occurred",
        "tlsv1 alert",
        "ssl",
        "remote end closed connection",
    ]
    return any(marker in reason_text for marker in transient_markers)


def is_transient_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, (http.client.RemoteDisconnected, ConnectionResetError, ConnectionAbortedError, TimeoutError, socket.timeout, ssl.SSLError)):
        return True
    text = str(exc).lower()
    transient_markers = [
        "remote end closed connection",
        "unexpected eof",
        "connection reset",
        "connection aborted",
        "timed out",
        "timeout",
        "ssl",
    ]
    return any(marker in text for marker in transient_markers)


def as_bool_series(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    return normalized.isin(["1", "true", "yes"])


def literal_hardcoding_flag(assertion_text: str) -> bool:
    literal_tokens = re.findall(
        r"\b\d+'[bdho][0-9a-fA-F_xzXZ?]+\b|\b\d+\b",
        str(assertion_text or ""),
    )
    for tok in literal_tokens:
        low = tok.lower()
        if low in {"0", "1", "1'b0", "1'b1", "1'd0", "1'd1", "1'h0", "1'h1"}:
            continue
        return True
    return False


def heuristic_semantic_reason(candidate_text: str) -> tuple[bool, str]:
    text = str(candidate_text or "").lower()
    literal_patterns = [
        r"\b\d+'[bdho][0-9a-f_xz?]+\b",
        r"\b\d+\b",
        r"\b0x[0-9a-f]+\b",
    ]
    literal_hits = sum(bool(re.search(pat, text)) for pat in literal_patterns)
    suspicious_terms = ["cycle", "observed", "trace", "sample", "captured"]
    suspicious = any(term in text for term in suspicious_terms)
    if "rst_n" in text and len(re.findall(r"\b[a-z_][a-z0-9_]*\b", text)) <= 4:
        return False, "Heuristic fallback: reset-only or trivial relation."
    if literal_hits >= 2 or suspicious:
        return False, "Heuristic fallback: likely literal-specific or trace-specific relation."
    return True, "Heuristic fallback: relation appears plausibly aligned with the spec."


def sanitize_abstracted_summary(summary_text: str) -> str:
    kept_lines = []
    for raw_line in str(summary_text or "").splitlines():
        line = raw_line.rstrip()
        low = line.lower()
        if "do not hardcode" in low:
            continue
        if "avoid hardcoding" in low:
            continue
        if line.strip().startswith("- Preserve the relation"):
            continue
        if line.strip().startswith("- Preserve the cross-cycle relation"):
            continue
        if line.strip().startswith("- Preserve the same-cycle"):
            continue
        if line.strip().startswith("- Preserve the boundary relation"):
            continue
        kept_lines.append(line)
    cleaned = "\n".join(line for line in kept_lines if line.strip()).strip()
    return cleaned


def read_manifest(root: Path) -> list[dict[str, Any]]:
    manifest_path = root / "case_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return list(payload.get("cases", []))


def load_abstracted_summary_lookup(selected_cases_json: Path | None = None) -> dict[str, str]:
    lookup = {
        str(item["case_id"]): sanitize_abstracted_summary(str(item.get("abstracted_summary", "")))
        for item in DEFAULT_ABSTRACTED_SELECTED_CASES
        if str(item.get("abstracted_summary", "")).strip()
    }
    if not selected_cases_json:
        return lookup

    payload = json.loads(selected_cases_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list in selected cases json: {selected_cases_json}")
    for item in payload:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        summary = sanitize_abstracted_summary(str(item.get("abstracted_summary", "")))
        if case_id and summary:
            lookup[case_id] = summary
    return lookup


def build_case_bundles(
    *,
    cases_root: Path,
    case_ids: list[str],
    abstracted_summary_lookup: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    abstracted_summary_lookup = abstracted_summary_lookup or {}
    selected_lookup = {item["case_id"]: item for item in DEFAULT_ABSTRACTED_SELECTED_CASES}
    bundles: list[dict[str, Any]] = []
    for case_id in case_ids:
        meta = selected_lookup.get(case_id, {})
        case_dir = cases_root / case_id / "experiment"
        raw_prompt_src = read_text(case_dir / "prompts" / "prompt_3_spec_rtl_raw_trace.txt")
        spec_only_prompt_src = read_text(case_dir / "prompts" / "prompt_1_spec_only.txt")
        spec_plus_rtl_prompt_src = read_text(case_dir / "prompts" / "prompt_2_spec_plus_rtl.txt")
        bundles.append(
            {
                "case_id": case_id,
                "selection_tags": meta.get("selection_tags", ""),
                "selection_reason": meta.get("selection_reason", ""),
                "spec": read_text(case_dir / "spec.txt").strip(),
                "allowed_signals": parse_allowed_signals(spec_only_prompt_src),
                # The RTL context must come from the trace-free prompt.  Using
                # raw_prompt_src here can leak waveform rows into every RTL
                # context ablation when the trace label differs from the
                # legacy parser's cut marker.
                "rtl_text": extract_rtl_from_prompt(spec_plus_rtl_prompt_src),
                "additional_guidance": extract_waveform_guidance(raw_prompt_src),
                "raw_trace_input": (
                    "Good trace (posedge cycles):\n"
                    + read_text(case_dir / "trace_good.txt").strip()
                    + "\n\nBad trace (posedge cycles):\n"
                    + read_text(case_dir / "trace_bad.txt").strip()
                ),
                "normal_trace_summary": read_text(case_dir / "trace_summary.txt").strip(),
                "abstracted_trace_summary": abstracted_summary_lookup.get(case_id, ""),
                "spec_only_prompt_src": spec_only_prompt_src,
                "spec_plus_rtl_prompt_src": spec_plus_rtl_prompt_src,
                "raw_prompt_src": raw_prompt_src,
            }
        )
    return bundles


def make_generation_prompt(
    *,
    allowed_signals: list[str],
    spec: str,
    rtl_text: str,
    trace_section: str,
    additional_guidance: str,
    target_count: int,
) -> str:
    signal_bases = {signal.split("[", 1)[0].strip() for signal in allowed_signals}
    if "clk" in signal_bases:
        clock_event = "@(posedge clk)"
    elif "clk_i" in signal_bases:
        clock_event = "@(posedge clk_i)"
    else:
        event_signals = [signal.split("[", 1)[0].strip() for signal in allowed_signals]
        event_signals = list(dict.fromkeys(signal for signal in event_signals if signal))
        clock_event = "@(" + " or ".join(event_signals) + ")"

    if "rst_n" in signal_bases:
        disable_expr = "!rst_n"
    elif "rst_ni" in signal_bases:
        disable_expr = "!rst_ni"
    elif "rst" in signal_bases:
        disable_expr = "rst"
    else:
        disable_expr = "1'b0"
    guidance_block = f"\nAdditional guidance:\n{additional_guidance}\n" if additional_guidance else ""
    rtl_block = f"RTL:\n{rtl_text}\n\n" if rtl_text.strip() else "No RTL is provided for this run.\n\n"
    return textwrap.dedent(
        f"""
        You are a formal verification engineer.
        Generate exactly {target_count} distinct SystemVerilog Assertions in this strict format, one assertion per line:
        assert property ({clock_event} disable iff ({disable_expr}) (<ANTECEDENT>) |-> (<CONSEQUENT>));

        Rules:
        1) Output exactly {target_count} assertion lines total. No explanation. No markdown. No numbering.
        2) Use only allowed signals listed below.
        3) Each candidate must contain exactly one implication operator total: either one |-> or one |=>.
        4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
        5) Keep the {target_count} candidates meaningfully different while staying semantically faithful.
        6) Prefer candidates that pass on correct behavior and fail on buggy behavior.
        7) Avoid vacuous antecedents: choose conditions that actually occur on the bug-revealing scenario.
        8) Infer a reusable relation, not a one-off witnessed cycle.
        9) Do not hard-code observed literals unless the spec or RTL independently justifies them.

        Allowed signals:
        {", ".join(allowed_signals)}

        Specification:
        {spec}
        {guidance_block}
        {rtl_block}

        {trace_section}
        """
    ).strip()


def make_method_prompt(bundle: dict[str, Any], method: str, target_count: int) -> str:
    canonical_method = METHOD_ALIASES.get(method, method)
    trace_section_map = {
        "spec_only": (
            "No RTL or waveform trace is provided for this run.\n"
            "Infer a strong but general property only from the specification.\n"
            "Still prefer a relation that should distinguish correct from buggy behavior."
        ),
        "spec_plus_rtl": (
            "No waveform trace is provided for this run.\n"
            "Infer a strong but general property only from the specification and RTL.\n"
            "Still prefer a relation that should distinguish correct from buggy behavior."
        ),
        "spec_rtl_only": (
            "No waveform trace is provided for this run.\n"
            "Infer a strong but general property only from the specification and RTL.\n"
            "Still prefer a relation that should distinguish correct from buggy behavior."
        ),
        "spec_rtl_raw_trace": bundle["raw_trace_input"],
        "spec_rtl_trace_summary": (
            "Normal trace summary (existing summary-style input):\n"
            + bundle["normal_trace_summary"]
            + "\n\nSummary-driven checklist:\n"
            + "- Use the first divergence as evidence, not as a literal to memorize.\n"
            + "- Keep the property general across held-out traces.\n"
        ),
        "spec_rtl_abstracted_trace_summary": (
            "Abstracted trace summary:\n"
            + bundle["abstracted_trace_summary"]
        ),
    }
    return make_generation_prompt(
        allowed_signals=bundle["allowed_signals"],
        spec=bundle["spec"],
        rtl_text="" if canonical_method == "spec_only" else bundle["rtl_text"],
        trace_section=trace_section_map[canonical_method],
        additional_guidance=bundle["additional_guidance"],
        target_count=target_count,
    )


MODEL_CALL_TELEMETRY: list[dict[str, Any]] = []


def _record_model_call(**row: Any) -> None:
    MODEL_CALL_TELEMETRY.append(row)


def post_openai_chat(
    *,
    api_key: str,
    model_name: str,
    prompt: str,
    temperature: float,
    base_url: str | None = None,
    auth_scheme: str | None = None,
    extra_headers_raw: str | None = None,
    max_retries: int | None = None,
    retry_backoff_sec: float | None = None,
) -> str:
    use_base_url = (base_url or OPENAI_CHAT_URL).strip()
    use_auth_scheme = (auth_scheme or os.environ.get("MULTIMODEL_OPENAI_AUTH_SCHEME", "Bearer")).strip() or "Bearer"
    use_max_retries = (
        max(0, parse_int_env("MULTIMODEL_OPENAI_MAX_RETRIES", 4))
        if max_retries is None
        else max(0, int(max_retries))
    )
    use_retry_backoff_sec = (
        max(0.0, parse_float_env("MULTIMODEL_OPENAI_RETRY_BACKOFF_SEC", 5.0))
        if retry_backoff_sec is None
        else max(0.0, float(retry_backoff_sec))
    )
    if extra_headers_raw is None:
        extra_headers_raw = os.environ.get("MULTIMODEL_OPENAI_EXTRA_HEADERS_JSON", "").strip()
    extra_headers: dict[str, str] = {}
    if extra_headers_raw:
        try:
            parsed = json.loads(extra_headers_raw)
            if isinstance(parsed, dict):
                extra_headers = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "MULTIMODEL_OPENAI_EXTRA_HEADERS_JSON must be valid JSON object text."
            ) from exc
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert hardware verification engineer. "
                    "Follow the requested output format exactly and stay faithful to the spec, RTL, and traces."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
    }
    fixed_seed = os.environ.get("MULTIMODEL_SEED", "").strip()
    if fixed_seed:
        payload["seed"] = int(fixed_seed)
    req = urllib.request.Request(
        use_base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"{use_auth_scheme} {api_key}",
            **extra_headers,
        },
        method="POST",
    )
    call_started = time.perf_counter()
    for attempt in range(use_max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", errors="replace"))
            if attempt < use_max_retries and is_transient_http_status(exc.code):
                wait_sec = use_retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient OpenAI HTTP {exc.code}; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{use_max_retries})",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise RuntimeError(f"OpenAI HTTPError {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < use_max_retries and is_transient_url_error(exc):
                wait_sec = use_retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient OpenAI URLError; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{use_max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise RuntimeError(f"OpenAI URLError: {exc}") from exc
        except Exception as exc:
            if attempt < use_max_retries and is_transient_disconnect_error(exc):
                wait_sec = use_retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient OpenAI disconnect; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{use_max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "").strip()
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    total_tokens = usage.get("total_tokens")
    if total_tokens is None and isinstance(prompt_tokens, (int, float)) and isinstance(completion_tokens, (int, float)):
        total_tokens = prompt_tokens + completion_tokens
    _record_model_call(
        provider="openai_compatible",
        model_name=model_name,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        duration_sec=time.perf_counter() - call_started,
        retry_count=attempt,
        prompt_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        total_tokens=total_tokens,
        usage_available=bool(usage),
        provider_usage=usage,
    )
    return content


def post_ollama_chat(*, base_url: str, model_name: str, prompt: str, temperature: float) -> str:
    call_started = time.perf_counter()
    payload = {
        "model": model_name,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert hardware verification engineer. "
                    "Follow the requested output format exactly and stay faithful to the spec, RTL, and traces."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": 16384,
            "num_gpu": 0,
            "num_predict": 384,
        },
    }
    req = urllib.request.Request(
        base_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = redact_secrets(exc.read().decode("utf-8", errors="replace"))
        raise RuntimeError(f"Ollama HTTPError {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama URLError: {exc}") from exc
    content = (data.get("message") or {}).get("content", "").strip()
    prompt_tokens = data.get("prompt_eval_count")
    output_tokens = data.get("eval_count")
    total_tokens = prompt_tokens + output_tokens if isinstance(prompt_tokens, int) and isinstance(output_tokens, int) else None
    _record_model_call(provider="ollama", model_name=model_name,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        response_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        duration_sec=time.perf_counter()-call_started, retry_count=0,
        prompt_tokens=prompt_tokens, output_tokens=output_tokens, total_tokens=total_tokens,
        usage_available=total_tokens is not None, provider_usage={"prompt_eval_count":prompt_tokens,"eval_count":output_tokens})
    return content


def post_anthropic_messages(*, api_key: str, model_name: str, prompt: str, temperature: float) -> str:
    auth_mode = os.environ.get("MULTIMODEL_CLAUDE_AUTH_MODE", "x-api-key").strip().lower() or "x-api-key"
    api_version = os.environ.get("MULTIMODEL_CLAUDE_API_VERSION", "2023-06-01").strip() or "2023-06-01"
    max_tokens = int(os.environ.get("MULTIMODEL_CLAUDE_MAX_TOKENS", "1400") or "1400")
    max_retries = max(0, parse_int_env("MULTIMODEL_CLAUDE_MAX_RETRIES", 4))
    retry_backoff_sec = max(0.0, parse_float_env("MULTIMODEL_CLAUDE_RETRY_BACKOFF_SEC", 5.0))
    extra_headers_raw = os.environ.get("MULTIMODEL_CLAUDE_EXTRA_HEADERS_JSON", "").strip()
    extra_headers: dict[str, str] = {}
    if extra_headers_raw:
        try:
            parsed = json.loads(extra_headers_raw)
            if isinstance(parsed, dict):
                extra_headers = {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "MULTIMODEL_CLAUDE_EXTRA_HEADERS_JSON must be valid JSON object text."
            ) from exc

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "anthropic-version": api_version,
        **extra_headers,
    }
    if auth_mode == "x-api-key":
        headers["x-api-key"] = api_key
    elif auth_mode == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        raise RuntimeError("MULTIMODEL_CLAUDE_AUTH_MODE must be 'x-api-key' or 'bearer'.")

    payload = {
        "model": model_name,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": (
            "You are an expert hardware verification engineer. "
            "Follow the requested output format exactly and stay faithful to the spec, RTL, and traces."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            body = redact_secrets(exc.read().decode("utf-8", errors="replace"))
            if attempt < max_retries and is_transient_http_status(exc.code):
                wait_sec = retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient Anthropic HTTP {exc.code}; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{max_retries})",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise RuntimeError(f"Anthropic HTTPError {exc.code}: {body}") from exc
        except urllib.error.URLError as exc:
            if attempt < max_retries and is_transient_url_error(exc):
                wait_sec = retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient Anthropic URLError; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise RuntimeError(f"Anthropic URLError: {exc}") from exc
        except Exception as exc:
            if attempt < max_retries and is_transient_disconnect_error(exc):
                wait_sec = retry_backoff_sec * (attempt + 1)
                print(
                    f"[WARN] Transient Anthropic disconnect; retrying in {wait_sec:.1f}s "
                    f"({attempt + 1}/{max_retries}): {exc}",
                    file=sys.stderr,
                )
                time.sleep(wait_sec)
                continue
            raise

    content_blocks = data.get("content", [])
    text_parts: list[str] = []
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(str(block.get("text", "")))
    text = "\n".join(part for part in text_parts if part).strip()
    if not text:
        raise RuntimeError(f"Anthropic response missing text content: {json.dumps(data, ensure_ascii=False)[:800]}")
    return text


def post_model_chat(model_spec: dict[str, Any], prompt: str, temperature: float) -> str:
    provider = model_spec["provider"]
    if provider in {"openai", "openai_compatible"}:
        env_name = model_spec["api_key_env"]
        api_key = os.environ.get(env_name, "").strip()
        key_file_name = str(model_spec.get("key_file_name", "openai_api_key.txt"))
        key_file = SECRETS_DIR / key_file_name
        if not api_key:
            if key_file.exists():
                api_key = key_file.read_text(encoding="utf-8").strip()
        if not api_key:
            raise RuntimeError(
                f"Missing relay/model key. Set {env_name} or create {key_file} with the key only."
            )
        base_url_env = str(model_spec.get("relay_base_url_env", "MULTIMODEL_OPENAI_BASE_URL"))
        auth_scheme_env = str(model_spec.get("relay_auth_scheme_env", "MULTIMODEL_OPENAI_AUTH_SCHEME"))
        extra_headers_env = str(model_spec.get("relay_extra_headers_env", "MULTIMODEL_OPENAI_EXTRA_HEADERS_JSON"))
        max_retries_env = str(model_spec.get("relay_max_retries_env", "MULTIMODEL_OPENAI_MAX_RETRIES"))
        retry_backoff_env = str(model_spec.get("relay_retry_backoff_env", "MULTIMODEL_OPENAI_RETRY_BACKOFF_SEC"))
        return post_openai_chat(
            api_key=api_key,
            model_name=model_spec["model_name"],
            prompt=prompt,
            temperature=temperature,
            base_url=os.environ.get(base_url_env, "").strip() or OPENAI_CHAT_URL,
            auth_scheme=os.environ.get(auth_scheme_env, "Bearer").strip() or "Bearer",
            extra_headers_raw=os.environ.get(extra_headers_env, "").strip(),
            max_retries=parse_int_env(max_retries_env, 4),
            retry_backoff_sec=parse_float_env(retry_backoff_env, 5.0),
        )
    if provider == "anthropic":
        env_name = model_spec["api_key_env"]
        api_key = os.environ.get(env_name, "").strip()
        if not api_key:
            key_file = SECRETS_DIR / "anthropic_api_key.txt"
            if key_file.exists():
                api_key = key_file.read_text(encoding="utf-8").strip()
        if not api_key:
            raise RuntimeError(
                f"Missing Anthropic key. Set {env_name} or create {key_file} with the key only."
            )
        return post_anthropic_messages(
            api_key=api_key,
            model_name=model_spec["model_name"],
            prompt=prompt,
            temperature=temperature,
        )
    if provider == "ollama":
        return post_ollama_chat(
            base_url=model_spec["base_url"],
            model_name=model_spec["model_name"],
            prompt=prompt,
            temperature=temperature,
        )
    raise ValueError(f"Unsupported provider: {provider}")


def collect_candidates_with_metrics(
    *,
    model_spec: dict[str, Any],
    prompt: str,
    target_count: int,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    collected: list[str] = []
    raw_responses: list[str] = []
    call_metrics: list[dict[str, Any]] = []
    fixed_temperature = os.environ.get("MULTIMODEL_FIXED_TEMPERATURE", "").strip()
    # Keep temperature fixed while allowing up to three extraction attempts so
    # every model has the same requested candidate budget even when one response
    # yields too few distinct assertions.
    temperatures = [float(fixed_temperature)] * 3 if fixed_temperature else [0.2, 0.6, 0.9]
    for temp in temperatures:
        attempt_prompt = prompt
        if collected:
            attempt_prompt += "\n\nDo not repeat previous candidates:\n- " + "\n- ".join(collected)
        telemetry_start = len(MODEL_CALL_TELEMETRY)
        before = len(collected)
        response = post_model_chat(model_spec, attempt_prompt, temperature=temp)
        raw_responses.append(response)
        for candidate in extract_sva_candidates(response):
            if candidate not in collected:
                collected.append(candidate)
            if len(collected) >= target_count:
                break
        metric = dict(MODEL_CALL_TELEMETRY[-1]) if len(MODEL_CALL_TELEMETRY) > telemetry_start else {}
        metric.update({
            "temperature": temp,
            "candidate_count_before": before,
            "candidate_count_after": len(collected),
            "new_candidate_start": before + 1 if len(collected) > before else None,
            "new_candidate_end": len(collected) if len(collected) > before else None,
        })
        call_metrics.append(metric)
        if len(collected) >= target_count:
            return collected[:target_count], raw_responses, call_metrics
    return collected[:target_count], raw_responses, call_metrics


def collect_candidates(
    *, model_spec: dict[str, Any], prompt: str, target_count: int
) -> tuple[list[str], list[str]]:
    candidates, responses, _ = collect_candidates_with_metrics(
        model_spec=model_spec, prompt=prompt, target_count=target_count
    )
    return candidates, responses


def classify_failure(row: dict[str, Any]) -> tuple[str, str]:
    if not row["compile_ok"]:
        return "compile_fail", "Candidate does not compile across the evaluation benches."
    if row["correct_pass"] and row["buggy_fail"]:
        if row["trace_overfit"]:
            return "overfit_suspect", "Seen-trace success does not generalize to held-out behavior."
        return "success", "Passes correct and fails buggy."
    if row["correct_pass"] and not row["buggy_fail"]:
        if not row["antecedent_hit_buggy"]:
            return "vacuity", "Antecedent never triggers on buggy trace."
        return "too_weak", "Antecedent triggers on buggy trace but consequent does not distinguish buggy behavior."
    if (not row["correct_pass"]) and row["buggy_fail"]:
        return "too_strong", "Flags buggy behavior but also hurts correct behavior."
    return "ineffective", "Neither preserves correct behavior nor cleanly catches buggy behavior."


def persist_progress(
    result_rows: list[dict[str, Any]],
    prompt_rows: list[dict[str, Any]],
    summary_rows: list[dict[str, Any]] | None = None,
) -> None:
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if result_rows:
        pd.DataFrame(result_rows).to_csv(
            DEFAULT_OUTPUT_DIR / "multi_model_results_raw.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if prompt_rows:
        pd.DataFrame(prompt_rows).to_csv(
            DEFAULT_OUTPUT_DIR / "multi_model_prompt_log.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(
            DEFAULT_OUTPUT_DIR / "multi_model_summary.csv",
            index=False,
            encoding="utf-8-sig",
        )


RESULT_KEY_COLS = [
    "model_label",
    "provider",
    "model_name",
    "case_id",
    "method",
    "candidate_index",
]
PROMPT_KEY_COLS = [
    "model_label",
    "provider",
    "model_name",
    "case_id",
    "method",
]
SUMMARY_KEY_COLS = [
    "model_label",
    "provider",
    "model_name",
    "method",
]


def safe_model_slug(model_label: str, provider: str, model_name: str) -> str:
    raw = f"{model_label}__{provider}__{model_name}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", raw).strip("_") or "model"


def csv_to_df(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path, encoding="utf-8-sig", on_bad_lines="skip")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def rows_to_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def normalize_key_cols(df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in key_cols:
        if col not in out.columns:
            out[col] = ""
        out[col] = out[col].fillna("").astype(str)
    return out


def upsert_df(existing_df: pd.DataFrame, new_df: pd.DataFrame, key_cols: list[str]) -> pd.DataFrame:
    if new_df.empty:
        return existing_df.copy()
    existing_df = normalize_key_cols(existing_df, key_cols)
    new_df = normalize_key_cols(new_df, key_cols)
    combined = pd.concat([existing_df, new_df], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(subset=key_cols, keep="last")
    combined = combined.reset_index(drop=True)
    return combined


def write_df(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".writing")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(out_path)


def aggregate_and_write_outputs(
    *,
    result_rows: list[dict[str, Any]],
    prompt_rows: list[dict[str, Any]],
    model_specs: list[dict[str, Any]],
    method_specs: list[dict[str, Any]],
    candidates_per_cell: int,
    use_property: bool,
    output_dir: Path,
    selected_case_ids: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    new_result_df = rows_to_df(result_rows)
    new_prompt_df = rows_to_df(prompt_rows)

    aggregate_result_path = output_dir / "multi_model_results_raw.csv"
    aggregate_prompt_path = output_dir / "multi_model_prompt_log.csv"
    aggregate_summary_path = output_dir / "multi_model_summary.csv"
    aggregate_meta_path = output_dir / "multi_model_run_meta.json"

    aggregate_result_df = upsert_df(csv_to_df(aggregate_result_path), new_result_df, RESULT_KEY_COLS)
    aggregate_prompt_df = upsert_df(csv_to_df(aggregate_prompt_path), new_prompt_df, PROMPT_KEY_COLS)
    aggregate_summary_rows = build_summary(aggregate_result_df) if not aggregate_result_df.empty else []
    aggregate_summary_df = rows_to_df(aggregate_summary_rows)

    write_df(aggregate_result_df, aggregate_result_path)
    write_df(aggregate_prompt_df, aggregate_prompt_path)
    write_df(aggregate_summary_df, aggregate_summary_path)
    write_text(
        aggregate_meta_path,
        json.dumps(
            {
                "thread_id": THREAD_ID,
                "selected_case_ids": selected_case_ids,
                "active_model_specs": model_specs,
                "active_method_specs": method_specs,
                "candidates_per_cell": candidates_per_cell,
                "use_property_compile_mode": use_property,
                "write_mode": "upsert_append_by_unique_key",
                "result_key_cols": RESULT_KEY_COLS,
                "prompt_key_cols": PROMPT_KEY_COLS,
                "summary_key_cols": SUMMARY_KEY_COLS,
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    if new_result_df.empty:
        return

    for model_keys, sub_result in new_result_df.groupby(["model_label", "provider", "model_name"], dropna=False):
        model_label, provider, model_name = model_keys
        slug = safe_model_slug(str(model_label), str(provider), str(model_name))
        model_dir = output_dir / "models" / slug
        model_prompt_sub = new_prompt_df.loc[
            (new_prompt_df.get("model_label", "") == model_label)
            & (new_prompt_df.get("provider", "") == provider)
            & (new_prompt_df.get("model_name", "") == model_name)
        ].copy()
        model_result_path = model_dir / "multi_model_results_raw.csv"
        model_prompt_path = model_dir / "multi_model_prompt_log.csv"
        model_summary_path = model_dir / "multi_model_summary.csv"
        model_meta_path = model_dir / "multi_model_run_meta.json"

        model_result_df = upsert_df(csv_to_df(model_result_path), sub_result, RESULT_KEY_COLS)
        model_prompt_df_existing = upsert_df(csv_to_df(model_prompt_path), model_prompt_sub, PROMPT_KEY_COLS)
        model_summary_df = rows_to_df(build_summary(model_result_df))

        write_df(model_result_df, model_result_path)
        write_df(model_prompt_df_existing, model_prompt_path)
        write_df(model_summary_df, model_summary_path)
        write_text(
            model_meta_path,
            json.dumps(
                {
                    "thread_id": THREAD_ID,
                    "model_label": model_label,
                    "provider": provider,
                    "model_name": model_name,
                    "selected_case_ids": selected_case_ids,
                    "active_method_specs": method_specs,
                    "candidates_per_cell": candidates_per_cell,
                    "use_property_compile_mode": use_property,
                    "write_mode": "upsert_append_by_unique_key",
                    "result_key_cols": RESULT_KEY_COLS,
                    "prompt_key_cols": PROMPT_KEY_COLS,
                    "summary_key_cols": SUMMARY_KEY_COLS,
                    "slug": slug,
                    "argv": sys.argv,
                },
                indent=2,
                ensure_ascii=False,
            ),
        )


def build_summary(result_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    group_cols = ["model_label", "provider", "model_name", "method"]
    for keys, sub in result_df.groupby(group_cols, dropna=False):
        model_label, provider, model_name, method = keys
        compile_ok = as_bool_series(sub["compile_ok"])
        correct_pass = as_bool_series(sub["correct_pass"])
        buggy_fail = as_bool_series(sub["buggy_fail"])
        antecedent_hit_buggy = as_bool_series(sub["antecedent_hit_buggy"])
        heldout_correct_pass = as_bool_series(sub["heldout_correct_pass"])
        heldout_buggy_fail = as_bool_series(sub["heldout_buggy_fail"])
        heldout_antecedent_hit = as_bool_series(sub["heldout_antecedent_hit"])
        trace_overfit = as_bool_series(sub["trace_overfit"])
        literal_hardcoding = as_bool_series(sub["literal_hardcoding"])
        rows.append(
            {
                "model_label": model_label,
                "provider": provider,
                "model_name": model_name,
                "method": method,
                "candidate_count": int(len(sub)),
                "case_count": int(sub["case_id"].nunique()),
                "compile_ok_rate": float(compile_ok.mean()) if len(sub) else 0.0,
                "correct_pass_rate": float(correct_pass.mean()) if len(sub) else 0.0,
                "buggy_fail_rate": float(buggy_fail.mean()) if len(sub) else 0.0,
                "antecedent_hit_buggy_rate": float(antecedent_hit_buggy.mean()) if len(sub) else 0.0,
                "heldout_correct_pass_rate": float(heldout_correct_pass.mean()) if len(sub) else 0.0,
                "heldout_buggy_fail_rate": float(heldout_buggy_fail.mean()) if len(sub) else 0.0,
                "heldout_antecedent_hit_rate": float(heldout_antecedent_hit.mean()) if len(sub) else 0.0,
                "trace_overfit_rate": float(trace_overfit.mean()) if len(sub) else 0.0,
                "literal_hardcoding_rate": float(literal_hardcoding.mean()) if len(sub) else 0.0,
                "vacuity_rate": float((sub["failure_mode"] == "vacuity").mean()) if len(sub) else 0.0,
                "too_weak_rate": float((sub["failure_mode"] == "too_weak").mean()) if len(sub) else 0.0,
                "too_strong_rate": float((sub["failure_mode"] == "too_strong").mean()) if len(sub) else 0.0,
                "success_rate": float((sub["failure_mode"] == "success").mean()) if len(sub) else 0.0,
            }
        )
    return rows


def str_to_bool(text: str) -> bool:
    return str(text or "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_selected_case_ids(
    *,
    cases_root: Path,
    requested_case_ids: list[str],
    all_cases: bool,
    max_cases: int,
    shard_index: int,
    shard_count: int,
) -> list[str]:
    if requested_case_ids:
        case_ids = list(dict.fromkeys(requested_case_ids))
    elif all_cases:
        case_ids = [str(item["name"]) for item in read_manifest(cases_root)]
    else:
        case_ids = list(REPRESENTATIVE_CASE_IDS)

    for case_id in case_ids:
        if not (cases_root / case_id).exists():
            raise FileNotFoundError(f"Unknown case under {cases_root}: {case_id}")

    if shard_count <= 0:
        raise ValueError("--shard-count must be positive.")
    if shard_index < 0 or shard_index >= shard_count:
        raise ValueError("--shard-index must satisfy 0 <= shard-index < shard-count.")
    if shard_count > 1:
        case_ids = [case_id for idx, case_id in enumerate(case_ids) if idx % shard_count == shard_index]
    if max_cases > 0:
        case_ids = case_ids[:max_cases]
    return case_ids


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run multi-model SVA generation/evaluation over selected real-RTL cases. "
            "Defaults preserve the original representative 5-case study, but the runner "
            "can also target an entire dataset root such as rtl_cases_real_scale120."
        )
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("MULTIMODEL_CASES_ROOT", str(DEFAULT_TRACEABS_CASES_ROOT)),
        help="Dataset root containing case directories and case_manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("MULTIMODEL_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)),
        help="Directory to store prompts, raw results, summaries, and per-model shards.",
    )
    parser.add_argument("--case", action="append", default=[], help="Case id to include. Repeat to select multiple.")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        default=str_to_bool(os.environ.get("MULTIMODEL_ALL_CASES", "")),
        help="Select every case from case_manifest.json under --root.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=int(os.environ.get("MULTIMODEL_MAX_CASES", "0") or "0"),
        help="Optional cap after case selection/sharding. 0 means no cap.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=int(os.environ.get("MULTIMODEL_SHARD_INDEX", "0") or "0"),
        help="0-based shard index for splitting a large case list.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=int(os.environ.get("MULTIMODEL_SHARD_COUNT", "1") or "1"),
        help="Number of shards for splitting a large case list.",
    )
    parser.add_argument("--model", action="append", default=[], help="Model label to include. Repeat to select multiple.")
    parser.add_argument(
        "--method",
        action="append",
        default=[],
        help=(
            "Method to include. Supported: spec_only, spec_plus_rtl, spec_rtl_only, "
            "spec_rtl_raw_trace, spec_rtl_trace_summary, spec_rtl_abstracted_trace_summary."
        ),
    )
    parser.add_argument(
        "--candidates-per-cell",
        type=int,
        default=int(os.environ.get("MULTIMODEL_CANDIDATES_PER_CELL", "2") or "2"),
        help="How many distinct candidate assertions to request for each model/case/method cell.",
    )
    parser.add_argument(
        "--selected-cases-json",
        default=os.environ.get("MULTIMODEL_SELECTED_CASES_JSON", ""),
        help=(
            "Optional JSON list containing case_id + abstracted_summary entries. "
            "Used to enable spec_rtl_abstracted_trace_summary beyond the legacy handpicked subset."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=str_to_bool(os.environ.get("MULTIMODEL_DRY_RUN", "")),
        help="Prepare prompts and metadata only; skip model calls and WSL evaluation.",
    )
    args = parser.parse_args()

    cases_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env_model_filter = {
        item.strip()
        for item in os.environ.get("MULTIMODEL_MODEL_FILTER", "").split(",")
        if item.strip()
    }
    env_method_filter = {
        item.strip()
        for item in os.environ.get("MULTIMODEL_METHOD_FILTER", "").split(",")
        if item.strip()
    }
    env_case_filter = {
        item.strip()
        for item in os.environ.get("MULTIMODEL_CASE_FILTER", "").split(",")
        if item.strip()
    }
    requested_case_ids = [item.strip() for item in args.case if item.strip()]
    if env_case_filter:
        requested_case_ids.extend(sorted(env_case_filter))
    requested_model_labels = {item.strip() for item in args.model if item.strip()} | env_model_filter
    requested_methods = {item.strip() for item in args.method if item.strip()} | env_method_filter

    selected_case_ids = resolve_selected_case_ids(
        cases_root=cases_root,
        requested_case_ids=requested_case_ids,
        all_cases=args.all_cases,
        max_cases=args.max_cases,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
    )

    abstracted_summary_lookup = load_abstracted_summary_lookup(
        Path(args.selected_cases_json).resolve() if args.selected_cases_json else None
    )
    bundles = build_case_bundles(
        cases_root=cases_root,
        case_ids=selected_case_ids,
        abstracted_summary_lookup=abstracted_summary_lookup,
    )

    model_specs = [
        m for m in MODEL_SPECS if not requested_model_labels or m["model_label"] in requested_model_labels
    ]
    if requested_methods:
        for method_name in requested_methods:
            if method_name not in METHOD_ALIASES:
                raise ValueError(f"Unsupported --method: {method_name}")
        trace_labels = {
            "spec_only": "Specification only",
            "spec_plus_rtl": "Spec + RTL",
            "spec_rtl_only": "Spec + RTL",
            "spec_rtl_raw_trace": "Raw good/bad trace",
            "spec_rtl_trace_summary": "Normal trace summary",
            "spec_rtl_abstracted_trace_summary": "Abstracted trace summary",
        }
        method_specs = [
            {"method": method_name, "trace_input_label": trace_labels[method_name]}
            for method_name in requested_methods
        ]
    else:
        method_specs = list(METHOD_SPECS)

    if not bundles:
        raise RuntimeError("No cases selected for evaluation.")
    if not model_specs:
        raise RuntimeError("No models selected for evaluation.")
    if not method_specs:
        raise RuntimeError("No methods selected for evaluation.")

    use_property = False
    if not args.dry_run:
        use_property = probe_property_support(
            bundles[0]["case_id"],
            cases_root=cases_root,
            runtime_dir=output_dir / "_probe",
        )
    all_results: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []

    for model_spec in model_specs:
        for bundle in bundles:
            for method_spec in method_specs:
                method = method_spec["method"]
                if (
                    METHOD_ALIASES.get(method, method) == "spec_rtl_abstracted_trace_summary"
                    and not bundle["abstracted_trace_summary"].strip()
                ):
                    continue
                print(
                    f"[INFO] {model_spec['model_label']} | {bundle['case_id']} | {method}",
                    file=sys.stderr,
                )

                prompt_text = make_method_prompt(bundle, method, args.candidates_per_cell)
                prompt_dir = output_dir / "prompts" / model_spec["model_label"] / bundle["case_id"]
                prompt_path = prompt_dir / f"{method}.txt"
                write_text(prompt_path, prompt_text + "\n")
                method_prompt_rows: list[dict[str, Any]] = []
                method_result_rows: list[dict[str, Any]] = []

                candidates: list[str] = []
                raw_responses: list[str] = []
                if not args.dry_run:
                    candidates, raw_responses, call_metrics = collect_candidates_with_metrics(
                        model_spec=model_spec,
                        prompt=prompt_text,
                        target_count=args.candidates_per_cell,
                    )
                else:
                    call_metrics = []

                method_prompt_rows.append(
                    {
                        "model_label": model_spec["model_label"],
                        "provider": model_spec["provider"],
                        "model_name": model_spec["model_name"],
                        "case_id": bundle["case_id"],
                        "selection_tags": bundle["selection_tags"],
                        "selection_reason": bundle["selection_reason"],
                        "method": method,
                        "trace_input_label": method_spec["trace_input_label"],
                        "prompt_path": str(prompt_path.resolve()),
                        "prompt_text": prompt_text,
                        "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
                        "generation_metrics_json": json.dumps(call_metrics, ensure_ascii=False),
                    }
                )
                prompt_rows.extend(method_prompt_rows)

                if args.dry_run:
                    aggregate_and_write_outputs(
                        result_rows=[],
                        prompt_rows=method_prompt_rows,
                        model_specs=model_specs,
                        method_specs=method_specs,
                        candidates_per_cell=args.candidates_per_cell,
                        use_property=use_property,
                        output_dir=output_dir,
                        selected_case_ids=selected_case_ids,
                    )
                    continue

                for candidate_index, assertion_text in enumerate(candidates, start=1):
                    runtime_dir = (
                        output_dir
                        / "runtime"
                        / model_spec["model_label"]
                        / bundle["case_id"]
                        / method
                        / f"cand_{candidate_index:02d}"
                    )
                    eval_result = run_case_eval(
                        case_id=bundle["case_id"],
                        assertion_text=assertion_text,
                        signal_names=bundle["allowed_signals"],
                        use_property=use_property,
                        runtime_dir=runtime_dir,
                        cases_root=cases_root,
                    )
                    semantic_reasonable, semantic_reason = heuristic_semantic_reason(assertion_text)
                    row = {
                        "model_label": model_spec["model_label"],
                        "provider": model_spec["provider"],
                        "model_name": model_spec["model_name"],
                        "case_id": bundle["case_id"],
                        "selection_tags": bundle["selection_tags"],
                        "selection_reason": bundle["selection_reason"],
                        "method": method,
                        "trace_input_label": method_spec["trace_input_label"],
                        "candidate_index": candidate_index,
                        "assertion_text": assertion_text,
                        "compile_ok": bool(eval_result["compile_ok"]),
                        "correct_pass": bool(eval_result["correct_pass"]),
                        "buggy_fail": bool(eval_result["buggy_fail"]),
                        "antecedent_hit_buggy": bool(eval_result["antecedent_hit"]),
                        "non_vacuous_buggy": bool(eval_result["non_vacuous"]),
                        "heldout_correct_pass": bool(eval_result["heldout_correct_pass"]),
                        "heldout_buggy_fail": bool(eval_result["heldout_buggy_fail"]),
                        "heldout_antecedent_hit": bool(eval_result["heldout_antecedent_hit"]),
                        "heldout_non_vacuous": bool(eval_result["heldout_non_vacuous"]),
                        "trace_overfit": bool(eval_result["trace_overfit"]),
                        "literal_hardcoding": literal_hardcoding_flag(assertion_text),
                        "semantic_reasonable": semantic_reasonable,
                        "semantic_reason": semantic_reason,
                        "seen_good_ant_hits": int(eval_result["seen_good_ant_hits"]),
                        "seen_bad_ant_hits": int(eval_result["seen_bad_ant_hits"]),
                        "heldout_bad_ant_hits": int(eval_result["heldout_bad_ant_hits"]),
                        "seen_good_fail_hits": int(eval_result["seen_good_fail_hits"]),
                        "seen_bad_fail_hits": int(eval_result["seen_bad_fail_hits"]),
                        "heldout_good_fail_hits": int(eval_result["heldout_good_fail_hits"]),
                        "heldout_bad_fail_hits": int(eval_result["heldout_bad_fail_hits"]),
                        "compile_duration_sec": float(eval_result.get("compile_duration_sec", 0.0)),
                        "verification_duration_sec": float(eval_result.get("verification_duration_sec", 0.0)),
                        "use_property_compile_mode": use_property,
                    }
                    failure_mode, failure_reason = classify_failure(row)
                    row["failure_mode"] = failure_mode
                    row["failure_reason"] = failure_reason
                    all_results.append(row)
                    method_result_rows.append(row)

                aggregate_and_write_outputs(
                    result_rows=method_result_rows,
                    prompt_rows=method_prompt_rows,
                    model_specs=model_specs,
                    method_specs=method_specs,
                    candidates_per_cell=args.candidates_per_cell,
                    use_property=use_property,
                    output_dir=output_dir,
                    selected_case_ids=selected_case_ids,
                )

    aggregate_and_write_outputs(
        result_rows=all_results,
        prompt_rows=prompt_rows,
        model_specs=model_specs,
        method_specs=method_specs,
        candidates_per_cell=args.candidates_per_cell,
        use_property=use_property,
        output_dir=output_dir,
        selected_case_ids=selected_case_ids,
    )
    print(output_dir / "multi_model_results_raw.csv")
    print(output_dir / "multi_model_summary.csv")


if __name__ == "__main__":
    main()
