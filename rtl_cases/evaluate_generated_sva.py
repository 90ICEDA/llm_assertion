#!/usr/bin/env python3
import argparse
import csv
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sva_eval_grammar import (
    GRAMMAR_VERSION,
    extract_single_assertion as shared_extract_single_assertion,
    strip_outer_parens,
)
from sva_static_filter import analyze_sva


PAST_RE = re.compile(r"\$past\s*\(\s*(?P<expr>[A-Za-z_]\w*(?:\[\d+(?::\d+)?\])?)\s*\)")
LEADING_DELAY_RE = re.compile(r"^##\s*(?P<delay>\d+)\b")
TEMPORAL_KEYWORD_RE = re.compile(
    r"\b(?:throughout|until|until_with|s_until|s_until_with|eventually|s_eventually|always|nexttime)\b",
    re.IGNORECASE,
)
OPTIONAL_ASSERT_LABEL_RE = re.compile(
    r"^(?:(?P<label>[A-Za-z_]\w*)\s*:\s*)?(?P<body>assert\s+property\b.*)$",
    re.IGNORECASE,
)

SVA_BASENAME_TO_METHOD = {
    "sva_1_spec_only.sv": "spec_only",
    "sva_2_spec_plus_rtl.sv": "spec_plus_rtl",
    "sva_3_spec_rtl_raw_trace.sv": "spec_rtl_raw_trace",
    "sva_4_spec_rtl_trace_summary.sv": "spec_rtl_trace_summary",
}

METHOD_ALIASES = {
    "1": "spec_only",
    "2": "spec_plus_rtl",
    "3": "spec_rtl_raw_trace",
    "4": "spec_rtl_trace_summary",
    "spec_only": "spec_only",
    "spec_plus_rtl": "spec_plus_rtl",
    "spec_rtl_raw_trace": "spec_rtl_raw_trace",
    "spec_rtl_trace_summary": "spec_rtl_trace_summary",
}

CANDIDATE_SUFFIX_RE = re.compile(r"^(?P<base>.+)__cand_(?P<idx>\d+)\.sv$")
SV_LITERAL_RE = re.compile(r"\b\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ_]+\b")
DECIMAL_RE = re.compile(r"\b\d+\b")
SIG_LITERAL_COMPARE_RE = re.compile(
    r"\b(?P<sig>[A-Za-z_]\w*(?:\[\d+(?::\d+)?\])?)\s*(?P<op>==|===|!=|!==)\s*"
    r"(?P<lit>\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ_]+|\d+)\b"
)
LITERAL_SIG_COMPARE_RE = re.compile(
    r"\b(?P<lit>\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ_]+|\d+)\s*(?P<op>==|===|!=|!==)\s*"
    r"(?P<sig>[A-Za-z_]\w*(?:\[\d+(?::\d+)?\])?)\b"
)


def run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def parse_module_name(verilog_text: str) -> str:
    m = re.search(r"\bmodule\s+([A-Za-z_]\w*)\b", verilog_text)
    if not m:
        raise ValueError("Cannot find module name.")
    return m.group(1)


def relaxed_compile_probe(sva_text: str) -> Tuple[bool, str]:
    normalized = normalize_sva_text(sva_text)
    m = OPTIONAL_ASSERT_LABEL_RE.match(normalized)
    if not m:
        return False, "Unsupported SVA format."
    body = m.group("body")
    try:
        shared_extract_single_assertion(body)
        return True, ""
    except Exception as exc:
        return False, str(exc)


def find_manual_review_csv(root: Path) -> Optional[Path]:
    candidates = [
        root / "case_method_review_current.csv",
        root / "case_method_review_latest.csv",
        root / "case_method_review.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def parse_semantic_reasonable_label(label: str) -> Optional[bool]:
    text = (label or "").strip().lower()
    if not text:
        return None
    if text.startswith("yes"):
        return True
    if text.startswith("no") or text.startswith("partial"):
        return False
    return None


def normalize_assertion_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def signal_base_name(name: str) -> str:
    return re.sub(r"\[.*\]$", "", (name or "").strip())


def parse_methods_arg(value: Optional[str]) -> Optional[List[str]]:
    if value is None:
        return None
    methods: List[str] = []
    for token in value.split(","):
        key = token.strip()
        if not key:
            continue
        if key not in METHOD_ALIASES:
            raise ValueError(f"Unsupported method selector: {key}")
        resolved = METHOD_ALIASES[key]
        if resolved not in methods:
            methods.append(resolved)
    return methods or None


def normalize_sva_text(text: str) -> str:
    return " ".join((text or "").strip().split())


def parse_leading_cycle_delay(expr: str) -> Tuple[int, str]:
    remaining = (expr or "").strip()
    total_delay = 0
    while True:
        m = LEADING_DELAY_RE.match(remaining)
        if not m:
            break
        total_delay += int(m.group("delay"))
        remaining = remaining[m.end() :].strip()
    return total_delay, strip_outer_parens(remaining)


def assert_no_unsupported_temporal(expr: str, role: str) -> None:
    text = strip_outer_parens(expr)
    if not text:
        raise ValueError(f"Empty {role} expression.")
    if "##" in text:
        raise ValueError(
            f"Unsupported {role} temporal sequence. Only a leading `##N` delay on the consequent is supported."
        )
    if TEMPORAL_KEYWORD_RE.search(text):
        raise ValueError(f"Unsupported temporal keyword in {role}: {text}")


def sv_literal_to_int(token: str) -> int:
    token = token.strip()
    m = re.fullmatch(r"(\d+)'([sS]?)([bBoOdDhH])([0-9a-fA-F_xXzZ_]+)", token)
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


def collect_literal_values_from_text(text: str) -> set[int]:
    values = {sv_literal_to_int(tok) for tok in SV_LITERAL_RE.findall(text or "")}
    for token in DECIMAL_RE.findall(text or ""):
        try:
            values.add(int(token, 10))
        except Exception:
            continue
    return values


def read_waveform_rows(csv_path: Path) -> List[Dict[str, int]]:
    if not csv_path.exists():
        return []
    rows: List[Dict[str, int]] = []
    with csv_path.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            parsed: Dict[str, int] = {}
            for key, value in row.items():
                if key == "time_ps":
                    continue
                base = signal_base_name(key)
                try:
                    parsed[base] = sv_value_to_int(value or "")
                except Exception:
                    continue
            if parsed:
                rows.append(parsed)
    return rows


def collect_observed_values(*waveform_sets: List[Dict[str, int]]) -> Dict[str, set[int]]:
    observed_by_signal: Dict[str, set[int]] = {}
    for rows in waveform_sets:
        for row in rows:
            for signal, value in row.items():
                observed_by_signal.setdefault(signal, set()).add(value)
    return observed_by_signal


def is_symbolic_state_signal(signal: str, rtl_text: str) -> bool:
    return signal == "state" and "localparam S_" in rtl_text


def extract_signal_literal_compares(expr: str, side: str) -> List[Dict[str, object]]:
    matches: List[Dict[str, object]] = []
    for regex in [SIG_LITERAL_COMPARE_RE, LITERAL_SIG_COMPARE_RE]:
        for m in regex.finditer(expr or ""):
            literal_text = m.group("lit")
            try:
                literal_value = sv_literal_to_int(literal_text)
            except Exception:
                continue
            matches.append(
                {
                    "signal": signal_base_name(m.group("sig")),
                    "op": m.group("op"),
                    "literal_text": literal_text,
                    "literal_value": literal_value,
                    "side": side,
                }
            )
    return matches


def detect_trace_literal_warning(
    case_dir: Path,
    case_meta: Dict[str, object],
    method: str,
    ante: str,
    cons: str,
    ports: List[Tuple[str, str]],
) -> Tuple[bool, str]:
    if method not in {"spec_rtl_raw_trace", "spec_rtl_trace_summary"}:
        return False, ""

    width_by_signal: Dict[str, int] = {}
    for name, rng in ports:
        if not rng:
            width_by_signal[name] = 1
            continue
        m = re.fullmatch(r"\[(\d+):(\d+)\]", rng)
        if not m:
            width_by_signal[name] = 2
            continue
        msb = int(m.group(1))
        lsb = int(m.group(2))
        width_by_signal[name] = abs(msb - lsb) + 1

    good_rows = read_waveform_rows(case_dir / "waveform_good.csv")
    bad_rows = read_waveform_rows(case_dir / "waveform_bad.csv")
    observed_by_signal = collect_observed_values(good_rows, bad_rows)

    correct_rtl_text = (case_dir / "correct.v").read_text(encoding="utf-8")
    allowed_literal_values = collect_literal_values_from_text(case_meta.get("spec", ""))
    allowed_literal_values |= collect_literal_values_from_text(correct_rtl_text)

    compares = extract_signal_literal_compares(ante, "ante") + extract_signal_literal_compares(cons, "cons")
    by_signal: Dict[str, List[Dict[str, object]]] = {}
    for item in compares:
        by_signal.setdefault(str(item["signal"]), []).append(item)

    reasons: List[str] = []
    for signal, items in sorted(by_signal.items()):
        width = width_by_signal.get(signal, 1)
        values = {int(item["literal_value"]) for item in items}
        sides = {str(item["side"]) for item in items}
        observed = observed_by_signal.get(signal, set())
        trace_only_values = sorted(v for v in values if v in observed and v not in allowed_literal_values)
        if (
            width >= 2
            and len(values) >= 2
            and {"ante", "cons"} <= sides
            and values <= observed
            and not (is_symbolic_state_signal(signal, correct_rtl_text) and values <= allowed_literal_values)
        ):
            literal_texts = ", ".join(sorted({str(item["literal_text"]) for item in items}))
            reasons.append(
                f"{signal} is pinned to multiple observed trace literals across antecedent/consequent ({literal_texts})"
            )
            continue
        if width >= 2 and trace_only_values:
            reasons.append(
                f"{signal} uses trace-only literal value(s) not justified by spec/RTL: "
                + ", ".join(str(v) for v in trace_only_values)
            )

    if reasons:
        return True, "; ".join(reasons)
    return False, ""


def heldout_metric_defaults() -> Dict[str, object]:
    return {
        "heldout_compile_ok": False,
        "heldout_pass_on_correct": False,
        "heldout_fail_on_buggy": False,
        "heldout_non_vacuous": False,
        "heldout_antecedent_triggered": False,
        "heldout_correct_antecedent_hits": 0,
        "heldout_buggy_antecedent_hits": 0,
        "heldout_correct_fail_count": -1,
        "heldout_buggy_fail_count": -1,
        "heldout_compile_error": "",
        "heldout_correct_log": "",
        "heldout_buggy_log": "",
    }


def build_trace_overfit_from_heldout(
    method: str,
    pass_on_correct: bool,
    fail_on_buggy: bool,
    non_vacuous: bool,
    antecedent_triggered: bool,
    heldout_metrics: Dict[str, object],
) -> Tuple[bool, str]:
    if method not in {"spec_rtl_raw_trace", "spec_rtl_trace_summary"}:
        return False, ""
    if not (pass_on_correct and fail_on_buggy and non_vacuous and antecedent_triggered):
        return False, ""

    reasons: List[str] = []
    if not heldout_metrics["heldout_compile_ok"]:
        detail = str(heldout_metrics.get("heldout_compile_error", "")).strip()
        reasons.append("held-out checker did not compile" + (f": {detail}" if detail else ""))
    if not heldout_metrics["heldout_antecedent_triggered"]:
        reasons.append("held-out correct trace stayed vacuous")
    if not heldout_metrics["heldout_pass_on_correct"]:
        reasons.append("held-out correct trace does not pass")
    if not heldout_metrics["heldout_fail_on_buggy"]:
        reasons.append("held-out buggy trace does not fail")

    if reasons:
        return True, "; ".join(reasons)
    return False, ""


def load_manual_review_lookup(path: Optional[Path]) -> Dict[Tuple[str, str], Dict[str, object]]:
    lookup: Dict[Tuple[str, str], Dict[str, object]] = {}
    if path is None or not path.exists():
        return lookup

    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            case_name = (row.get("case_name") or "").strip()
            method = (row.get("method") or "").strip()
            if not case_name or not method:
                continue
            label = (row.get("human_useful") or "").strip()
            reviewed_assertion = normalize_assertion_text(
                (row.get("generated_sva") or "").strip()
            )
            lookup[(case_name, method)] = {
                "semantic_reasonable": parse_semantic_reasonable_label(label),
                "semantic_review_label": label,
                "reviewed_assertion": reviewed_assertion,
            }
    return lookup


def infer_method_from_sva_file(sva_file: Path) -> Optional[str]:
    name = sva_file.name
    m = CANDIDATE_SUFFIX_RE.fullmatch(name)
    if m:
        base_name = m.group("base") + ".sv"
        return SVA_BASENAME_TO_METHOD.get(base_name)
    return SVA_BASENAME_TO_METHOD.get(name)


def infer_candidate_index_from_sva_file(sva_file: Path) -> Optional[int]:
    m = CANDIDATE_SUFFIX_RE.fullmatch(sva_file.name)
    if not m:
        return None
    return int(m.group("idx"))


def parse_optional_bool_flag(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    text = value.strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Unsupported boolean value: {value}")


def classify_failure_type(row: Dict[str, object]) -> str:
    if str(row.get("unsupported_reason", "")).strip():
        return "unsupported"
    detail = str(row.get("compile_error", "")).strip()
    if detail.startswith("STATIC_FILTER:"):
        return "static_filter_reject"
    if not row["syntax_pass"]:
        return "template_mismatch"
    if not row["compile_ok"]:
        return "compile_fail"
    if not row["pass_on_correct"]:
        return "false_positive_on_correct"
    if not row["antecedent_triggered"]:
        return "antecedent_not_triggered"
    if not row["non_vacuous"]:
        return "vacuous"
    if not row["fail_on_buggy"]:
        return "bug_not_detected_on_buggy"
    if row.get("trace_overfit"):
        return "trace_overfit"
    if row["semantic_reasonable"] is None:
        return "semantic_unreviewed"
    if not row["semantic_reasonable"]:
        return "semantic_unreasonable"
    return "strict_success"


def parse_dut_ports(correct_v_text: str) -> List[Tuple[str, str]]:
    header_match = re.search(
        r"\bmodule\b\s+[A-Za-z_]\w*\s*\((.*?)\)\s*;",
        correct_v_text,
        re.DOTALL,
    )
    if not header_match:
        raise ValueError("Cannot parse DUT ANSI-style port header.")
    header = header_match.group(1)
    ports = []
    seen = set()
    for m in re.finditer(
        r"\b(?:input|output|inout)\b\s+"
        r"(?:(?:wire|reg|logic)\s+)?"
        r"(?P<range>\[[^\]]+\]\s+)?"
        r"(?P<name>[A-Za-z_]\w*)",
        header,
        re.DOTALL,
    ):
        name = m.group("name")
        rng = (m.group("range") or "").strip()
        if name in seen:
            continue
        ports.append((name, rng))
        seen.add(name)
    return ports


def extract_single_assertion(sva_text: str) -> Tuple[str, str, str, str, str]:
    return shared_extract_single_assertion(sva_text)


def sanitize_past_name(expr: str) -> str:
    return "past__" + re.sub(r"[^A-Za-z0-9_]", "_", expr)


def infer_expr_range(expr: str, port_ranges: Dict[str, str]) -> str:
    part_sel = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+):(\d+)\]", expr)
    if part_sel:
        msb = int(part_sel.group(2))
        lsb = int(part_sel.group(3))
        hi = max(msb, lsb)
        lo = min(msb, lsb)
        return f"[{hi - lo}:0]"

    bit_sel = re.fullmatch(r"([A-Za-z_]\w*)\[(\d+)\]", expr)
    if bit_sel:
        return ""

    return port_ranges.get(expr, "")


def rewrite_past_refs(
    exprs: List[str], ports: List[Tuple[str, str]]
) -> Tuple[List[str], List[Tuple[str, str, str]]]:
    port_ranges = {name: rng for name, rng in ports}
    refs: List[Tuple[str, str, str]] = []
    seen = set()

    for expr in exprs:
        for m in PAST_RE.finditer(expr):
            raw = m.group("expr").strip()
            if raw in seen:
                continue
            seen.add(raw)
            refs.append((raw, sanitize_past_name(raw), infer_expr_range(raw, port_ranges)))

    rewritten = exprs
    for raw, repl, _rng in refs:
        pattern = re.compile(rf"\$past\s*\(\s*{re.escape(raw)}\s*\)")
        rewritten = [pattern.sub(repl, text) for text in rewritten]

    return rewritten, refs


def checker_module_text(
    ports: List[Tuple[str, str]],
    assertion_line: str,
    disable_expr: str,
    ante: str,
    op: str,
    cons: str,
) -> str:
    delay_cycles, cons = parse_leading_cycle_delay(cons)
    if disable_expr:
        assert_no_unsupported_temporal(disable_expr, "disable iff")
    assert_no_unsupported_temporal(ante, "antecedent")
    assert_no_unsupported_temporal(cons, "consequent")

    exprs: List[str] = []
    if disable_expr:
        exprs.append(disable_expr)
    exprs.extend([ante, cons])
    rewritten_exprs, past_refs = rewrite_past_refs(exprs, ports)
    if disable_expr:
        disable_expr = rewritten_exprs[0]
        ante = rewritten_exprs[1]
        cons = rewritten_exprs[2]
    else:
        ante = rewritten_exprs[0]
        cons = rewritten_exprs[1]

    port_lines = []
    for p, rng in ports:
        if rng:
            port_lines.append(f"    input logic {rng} {p}")
        else:
            port_lines.append(f"    input logic {p}")
    port_decl = ",\n".join(port_lines)
    past_decl_lines = []
    past_init_lines = []
    past_update_lines = []
    for raw, repl, rng in past_refs:
        if rng:
            past_decl_lines.append(f"    logic {rng} {repl};")
        else:
            past_decl_lines.append(f"    logic {repl};")
        past_init_lines.append(f"        {repl} = '0;")
        past_update_lines.append(f"        {repl} = {raw};")
    past_decl = "\n".join(past_decl_lines)
    past_init = "\n".join(past_init_lines)
    past_update = "\n".join(past_update_lines)

    total_delay = delay_cycles + (0 if op == "|->" else 1)
    pending_decl = ""
    pending_init = ""
    pending_clear = ""

    if total_delay == 0:
        check_logic = f"""
            if (({ante}) === 1'b1) begin
                antecedent_hits = antecedent_hits + 1;
                if (({cons}) !== 1'b1) begin
                    fail_count = fail_count + 1;
                    $error("SVA_FAIL: implication violated.");
                end
            end
"""
    else:
        pending_decl = "\n".join(f"    integer pending_d{i};" for i in range(total_delay + 1))
        pending_init = "\n".join(f"        pending_d{i} = 0;" for i in range(total_delay + 1))
        pending_clear = "\n".join(f"            pending_d{i} = 0;" for i in range(total_delay + 1))
        shift_lines = [f"            pending_d{i} = pending_d{i + 1};" for i in range(total_delay)]
        shift_lines.append(f"            pending_d{total_delay} = 0;")
        check_logic = f"""
{chr(10).join(shift_lines)}
            if (pending_d0 > 0 && (({cons}) !== 1'b1)) begin
                fail_count = fail_count + pending_d0;
                $error("SVA_FAIL: delayed implication violated.");
            end
            if (({ante}) === 1'b1) begin
                antecedent_hits = antecedent_hits + 1;
                pending_d{total_delay} = pending_d{total_delay} + 1;
            end
"""

    guarded_logic = check_logic
    if disable_expr:
        guarded_logic = f"""
        if (({disable_expr}) === 1'b1) begin
{pending_clear or "            ;"}
        end else begin
{check_logic}
        end
"""

    return f"""module sva_checker (
{port_decl}
);
    integer antecedent_hits;
    integer fail_count;
{past_decl}
{pending_decl}

    // Syntax check hook for the original assertion text.
    `ifdef CHECK_SVA_SYNTAX
    {assertion_line}
    `endif

    initial begin
        antecedent_hits = 0;
        fail_count = 0;
{past_init}
{pending_init}
    end

    always @(posedge clk) begin
{guarded_logic}
{past_update}
        // Print summary after state updates so the last sampled cycle is not lost.
        $display("SVA_SUMMARY antecedent_hits=%0d fail_count=%0d", antecedent_hits, fail_count);
    end
endmodule
"""


def inject_checker_into_tb(
    tb_text: str, tb_module_name: str, ports: List[Tuple[str, str]]
) -> str:
    conn = ",\n".join([f"        .{p}({p})" for p, _ in ports])
    inst = f"""
    sva_checker u_sva_checker (
{conn}
    );
"""
    idx = tb_text.rfind("endmodule")
    if idx < 0:
        raise ValueError(f"Cannot find endmodule in TB module {tb_module_name}")
    return tb_text[:idx] + inst + tb_text[idx:]


def syntax_checker_module_text(
    ports: List[Tuple[str, str]],
    sva_text: str,
) -> str:
    port_lines = []
    for p, rng in ports:
        if rng:
            port_lines.append(f"    input logic {rng} {p}")
        else:
            port_lines.append(f"    input logic {p}")
    port_decl = ",\n".join(port_lines)
    return f"""module sva_checker (
{port_decl}
);
    `ifdef CHECK_SVA_SYNTAX
    {sva_text.strip()}
    `endif
endmodule
"""


def compile_original_sva_syntax(
    iverilog: str,
    temp_dir: Path,
    rtl_file: Path,
    tb_text: str,
    tb_top_name: str,
    ports: List[Tuple[str, str]],
    assertion_text: str,
) -> Tuple[bool, str]:
    checker_file = temp_dir / "sva_syntax_checker.sv"
    eval_tb_file = temp_dir / "tb_syntax_eval.sv"
    checker_file.write_text(
        syntax_checker_module_text(ports, assertion_text),
        encoding="utf-8",
        newline="\n",
    )
    eval_tb_file.write_text(
        inject_checker_into_tb(tb_text, tb_top_name, ports),
        encoding="utf-8",
        newline="\n",
    )
    out_vvp = temp_dir / "syntax_only.out"
    compile_cmd = [
        iverilog,
        "-g2012",
        "-DCHECK_SVA_SYNTAX",
        "-s",
        tb_top_name,
        "-o",
        str(out_vvp),
        str(rtl_file),
        str(eval_tb_file),
        str(checker_file),
    ]
    c = run_cmd(compile_cmd, cwd=temp_dir)
    if c.returncode == 0:
        return True, ""
    relaxed_ok, relaxed_error = relaxed_compile_probe(assertion_text)
    if relaxed_ok:
        return True, ""
    return False, first_error_line(c.stdout) or relaxed_error


def parse_summary(log: str) -> Tuple[int, int]:
    matches = re.findall(r"SVA_SUMMARY\s+antecedent_hits=(\d+)\s+fail_count=(\d+)", log)
    if not matches:
        return 0, -1
    last = matches[-1]
    return int(last[0]), int(last[1])


def first_error_line(log: str) -> str:
    for line in log.splitlines():
        low = line.lower()
        if "error" in low or "syntax" in low or "undefined" in low:
            return line.strip()
    return ""


def run_case_sim(
    iverilog: str,
    vvp: str,
    temp_dir: Path,
    rtl_file: Path,
    eval_tb_file: Path,
    tb_top_name: str,
    checker_file: Path,
) -> Dict[str, object]:
    out_vvp = temp_dir / "simv.out"
    compile_cmd = [
        iverilog,
        "-g2012",
        "-s",
        tb_top_name,
        "-o",
        str(out_vvp),
        str(rtl_file),
        str(eval_tb_file),
        str(checker_file),
    ]
    c = run_cmd(compile_cmd, cwd=temp_dir)
    if c.returncode != 0:
        return {
            "compile_ok": False,
            "sim_ok": False,
            "antecedent_hits": 0,
            "fail_count": -1,
            "log": c.stdout,
        }

    s = run_cmd([vvp, str(out_vvp)], cwd=temp_dir)
    hits, fails = parse_summary(s.stdout)
    return {
        "compile_ok": True,
        "sim_ok": s.returncode == 0 or fails >= 0,
        "antecedent_hits": hits,
        "fail_count": fails,
        "log": s.stdout,
    }


def evaluate_one(
    root: Path,
    case_name: str,
    sva_file: Path,
    iverilog_bin: str,
    vvp_bin: str,
    bug_type: str = "",
    method: str = "",
    candidate_index: Optional[int] = None,
    semantic_reasonable: Optional[bool] = None,
    semantic_review_label: str = "",
    reviewed_assertion: str = "",
) -> Dict[str, object]:
    case_dir = root / case_name
    correct_v = case_dir / "correct.v"
    buggy_v = case_dir / "buggy.v"
    tb_v = case_dir / "tb.v"
    tb_holdout_v = case_dir / "tb_holdout.v"
    sva_text = sva_file.read_text(encoding="utf-8")
    heldout_defaults = heldout_metric_defaults()
    correct_text = correct_v.read_text(encoding="utf-8")
    tb_text = tb_v.read_text(encoding="utf-8")
    ports = parse_dut_ports(correct_text)
    tb_module_name = parse_module_name(tb_text)
    vector_signals = [name for name, rng in ports if rng]
    case_meta = next(
        (item for item in load_case_entries(root) if item["name"] == case_name),
        {"key_signals": []},
    )
    with tempfile.TemporaryDirectory(prefix="sva_syntax_probe_") as syntax_td:
        raw_compile_ok, raw_compile_error = compile_original_sva_syntax(
            iverilog_bin,
            Path(syntax_td),
            correct_v,
            tb_text,
            tb_module_name,
            ports,
            sva_text,
        )

    try:
        assertion_line, disable_expr, ante, op, cons = extract_single_assertion(sva_text)
    except Exception as e:
        return {
            "grammar_version": GRAMMAR_VERSION,
            "case_name": case_name,
            "bug_type": bug_type,
            "method": method,
            "candidate_index": candidate_index if candidate_index is not None else "",
            "sva_file": str(sva_file),
            "syntax_pass": False,
            "analysis_supported": False,
            "compile_ok": raw_compile_ok,
            "pass_on_correct": False,
            "fail_on_buggy": False,
            "non_vacuous": False,
            "antecedent_triggered": False,
            "correct_antecedent_hits": 0,
            "buggy_antecedent_hits": 0,
            "correct_fail_count": -1,
            "buggy_fail_count": -1,
            "semantic_reasonable": semantic_reasonable,
            "semantic_review_label": semantic_review_label,
            "trace_overfit": False,
            "trace_overfit_reason": "",
            "trace_literal_warning": False,
            "trace_literal_warning_reason": "",
            "unsupported_reason": "",
            "strict_success": False,
            "failure_type": "template_mismatch",
            "assertion_line": "",
            "compile_error": "" if raw_compile_ok else (raw_compile_error or ""),
            "syntax_log": f"TEMPLATE_MISMATCH: {e}",
            "correct_log": "",
            "buggy_log": "",
            **heldout_defaults,
        }
    if reviewed_assertion and normalize_assertion_text(assertion_line) != reviewed_assertion:
        semantic_reasonable = None
        semantic_review_label = "unreviewed:text_changed_from_manual_review"
    static_result = analyze_sva(
        assertion_line,
        list(case_meta.get("key_signals", [])),
        vector_signals,
    )
    if not static_result["pass"]:
        return {
            "grammar_version": GRAMMAR_VERSION,
            "case_name": case_name,
            "bug_type": bug_type,
            "method": method,
            "candidate_index": candidate_index if candidate_index is not None else "",
            "sva_file": str(sva_file),
            "syntax_pass": True,
            "analysis_supported": True,
            "compile_ok": raw_compile_ok,
            "pass_on_correct": False,
            "fail_on_buggy": False,
            "non_vacuous": False,
            "antecedent_triggered": False,
            "correct_antecedent_hits": 0,
            "buggy_antecedent_hits": 0,
            "correct_fail_count": -1,
            "buggy_fail_count": -1,
            "semantic_reasonable": semantic_reasonable,
            "semantic_review_label": semantic_review_label,
            "trace_overfit": False,
            "trace_overfit_reason": "",
            "trace_literal_warning": False,
            "trace_literal_warning_reason": "",
            "unsupported_reason": "",
            "strict_success": False,
            "failure_type": "static_filter_reject",
            "assertion_line": assertion_line,
            "compile_error": "" if raw_compile_ok else (raw_compile_error or ""),
            "syntax_log": "STATIC_FILTER: " + "; ".join(static_result["reasons"]),
            "correct_log": "",
            "buggy_log": "",
            **heldout_defaults,
        }
    tb_holdout_text = tb_holdout_v.read_text(encoding="utf-8") if tb_holdout_v.exists() else ""
    tb_holdout_module_name = parse_module_name(tb_holdout_text) if tb_holdout_text else ""

    with tempfile.TemporaryDirectory(prefix="sva_eval_") as td:
        temp_dir = Path(td)
        checker = temp_dir / "sva_checker.sv"
        eval_tb = temp_dir / "tb_eval.sv"
        eval_tb_holdout = temp_dir / "tb_holdout_eval.sv"
        try:
            checker_text = checker_module_text(ports, assertion_line, disable_expr, ante, op, cons)
        except ValueError as e:
            return {
                "grammar_version": GRAMMAR_VERSION,
                "case_name": case_name,
                "bug_type": bug_type,
                "method": method,
                "candidate_index": candidate_index if candidate_index is not None else "",
                "sva_file": str(sva_file),
                "syntax_pass": True,
                "analysis_supported": False,
                "compile_ok": raw_compile_ok,
                "pass_on_correct": False,
                "fail_on_buggy": False,
                "non_vacuous": False,
                "antecedent_triggered": False,
                "correct_antecedent_hits": 0,
                "buggy_antecedent_hits": 0,
                "correct_fail_count": -1,
                "buggy_fail_count": -1,
                "semantic_reasonable": semantic_reasonable,
                "semantic_review_label": semantic_review_label,
                "trace_overfit": False,
                "trace_overfit_reason": "",
                "trace_literal_warning": False,
                "trace_literal_warning_reason": "",
                "unsupported_reason": str(e),
                "strict_success": False,
                "failure_type": "unsupported",
                "assertion_line": assertion_line,
                "compile_error": "" if raw_compile_ok else (raw_compile_error or ""),
                "syntax_log": "UNSUPPORTED: " + str(e),
                "correct_log": "",
                "buggy_log": "",
                **heldout_defaults,
            }
        checker.write_text(
            checker_text,
            encoding="utf-8",
            newline="\n",
        )
        eval_tb.write_text(
            inject_checker_into_tb(tb_text, tb_module_name, ports),
            encoding="utf-8",
            newline="\n",
        )
        if tb_holdout_text:
            eval_tb_holdout.write_text(
                inject_checker_into_tb(tb_holdout_text, tb_holdout_module_name, ports),
                encoding="utf-8",
                newline="\n",
            )

        correct_res = run_case_sim(
            iverilog_bin, vvp_bin, temp_dir, correct_v, eval_tb, tb_module_name, checker
        )
        buggy_res = run_case_sim(
            iverilog_bin, vvp_bin, temp_dir, buggy_v, eval_tb, tb_module_name, checker
        )
        heldout_correct_res = heldout_metric_defaults()
        heldout_buggy_res = heldout_metric_defaults()
        if tb_holdout_text:
            heldout_correct_res = run_case_sim(
                iverilog_bin,
                vvp_bin,
                temp_dir,
                correct_v,
                eval_tb_holdout,
                tb_holdout_module_name,
                checker,
            )
            heldout_buggy_res = run_case_sim(
                iverilog_bin,
                vvp_bin,
                temp_dir,
                buggy_v,
                eval_tb_holdout,
                tb_holdout_module_name,
                checker,
            )

    compile_ok = correct_res["compile_ok"] and buggy_res["compile_ok"]
    antecedent_triggered = (correct_res["antecedent_hits"] > 0) or (
        buggy_res["antecedent_hits"] > 0
    )
    non_vacuous = compile_ok and (correct_res["antecedent_hits"] > 0)
    pass_on_correct = compile_ok and correct_res["fail_count"] == 0
    fail_on_buggy = compile_ok and buggy_res["fail_count"] > 0
    compile_error = ""
    if not compile_ok:
        compile_error = first_error_line(correct_res["log"]) or first_error_line(
            buggy_res["log"]
        )
    trace_literal_warning, trace_literal_warning_reason = detect_trace_literal_warning(
        case_dir,
        case_meta,
        method,
        ante,
        cons,
        ports,
    )
    heldout_metrics = heldout_metric_defaults()
    if tb_holdout_text:
        heldout_compile_ok = bool(heldout_correct_res["compile_ok"] and heldout_buggy_res["compile_ok"])
        heldout_compile_error = ""
        if not heldout_compile_ok:
            heldout_compile_error = first_error_line(str(heldout_correct_res["log"])) or first_error_line(
                str(heldout_buggy_res["log"])
            )
        heldout_metrics = {
            "heldout_compile_ok": heldout_compile_ok,
            "heldout_pass_on_correct": heldout_compile_ok and heldout_correct_res["fail_count"] == 0,
            "heldout_fail_on_buggy": heldout_compile_ok and heldout_buggy_res["fail_count"] > 0,
            "heldout_non_vacuous": heldout_compile_ok and heldout_correct_res["antecedent_hits"] > 0,
            "heldout_antecedent_triggered": heldout_compile_ok and heldout_correct_res["antecedent_hits"] > 0,
            "heldout_correct_antecedent_hits": heldout_correct_res["antecedent_hits"],
            "heldout_buggy_antecedent_hits": heldout_buggy_res["antecedent_hits"],
            "heldout_correct_fail_count": heldout_correct_res["fail_count"],
            "heldout_buggy_fail_count": heldout_buggy_res["fail_count"],
            "heldout_compile_error": heldout_compile_error,
            "heldout_correct_log": heldout_correct_res["log"],
            "heldout_buggy_log": heldout_buggy_res["log"],
        }
    elif method in {"spec_rtl_raw_trace", "spec_rtl_trace_summary"}:
        heldout_metrics["heldout_compile_error"] = "missing tb_holdout.v"

    trace_overfit, trace_overfit_reason = build_trace_overfit_from_heldout(
        method,
        pass_on_correct,
        fail_on_buggy,
        non_vacuous,
        antecedent_triggered,
        heldout_metrics,
    )

    row = {
        "grammar_version": GRAMMAR_VERSION,
        "case_name": case_name,
        "bug_type": bug_type,
        "method": method,
        "candidate_index": candidate_index if candidate_index is not None else "",
        "sva_file": str(sva_file),
        "syntax_pass": True,
        "analysis_supported": True,
        "compile_ok": compile_ok,
        "pass_on_correct": pass_on_correct,
        "fail_on_buggy": fail_on_buggy,
        "non_vacuous": non_vacuous,
        "antecedent_triggered": antecedent_triggered,
        "correct_antecedent_hits": correct_res["antecedent_hits"],
        "buggy_antecedent_hits": buggy_res["antecedent_hits"],
        "correct_fail_count": correct_res["fail_count"],
        "buggy_fail_count": buggy_res["fail_count"],
        "semantic_reasonable": semantic_reasonable,
        "semantic_review_label": semantic_review_label,
        "trace_overfit": trace_overfit,
        "trace_overfit_reason": trace_overfit_reason,
        "trace_literal_warning": trace_literal_warning,
        "trace_literal_warning_reason": trace_literal_warning_reason,
        "unsupported_reason": "",
        "assertion_line": assertion_line,
        "compile_error": compile_error,
        "syntax_log": "",
        "correct_log": correct_res["log"],
        "buggy_log": buggy_res["log"],
        **heldout_metrics,
    }
    row["strict_success"] = (
        row["compile_ok"]
        and row["pass_on_correct"]
        and row["fail_on_buggy"]
        and row["non_vacuous"]
        and row["antecedent_triggered"]
        and not row["trace_overfit"]
        and (row["semantic_reasonable"] is True)
    )
    row["failure_type"] = classify_failure_type(row)
    return row


def load_case_entries(root: Path) -> List[Dict[str, object]]:
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    return manifest["cases"]


def infer_sva_files(case_dir: Path, methods: Optional[List[str]] = None) -> List[Path]:
    generated = case_dir / "experiment" / "generated"
    if not generated.exists():
        return []
    candidate_files = sorted(generated.glob("sva_*__cand_*.sv"))
    if candidate_files:
        if methods is None:
            return candidate_files
        return [
            p for p in candidate_files if infer_method_from_sva_file(p) in set(methods)
        ]
    candidates = [
        generated / "sva_1_spec_only.sv",
        generated / "sva_2_spec_plus_rtl.sv",
        generated / "sva_3_spec_rtl_raw_trace.sv",
        generated / "sva_4_spec_rtl_trace_summary.sv",
    ]
    existing = [p for p in candidates if p.exists()]
    if methods is None:
        return existing
    return [p for p in existing if infer_method_from_sva_file(p) in set(methods)]


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate generated SVA on correct/buggy RTL with compile, pass/fail, and vacuity checks."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument("--case", help="Single case name, e.g. case03_valid_ready_or_bug.")
    parser.add_argument("--sva-file", help="Path to one SVA file to evaluate.")
    parser.add_argument("--output-csv", default="sva_eval_report.csv", help="Output CSV report path.")
    parser.add_argument("--iverilog", default="iverilog", help="iverilog binary name/path.")
    parser.add_argument("--vvp", default="vvp", help="vvp binary name/path.")
    parser.add_argument(
        "--methods",
        help="Optional comma-separated method filter. Example: 3,4 or spec_rtl_raw_trace,spec_rtl_trace_summary.",
    )
    parser.add_argument(
        "--manual-review-csv",
        help="Optional manual review CSV containing case_name, method, and human_useful columns.",
    )
    parser.add_argument(
        "--semantic-reasonable",
        help="Optional override for one-off evaluation: true/false.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()

    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")

    manual_review_csv = (
        Path(args.manual_review_csv).resolve()
        if args.manual_review_csv
        else find_manual_review_csv(root)
    )
    manual_review_lookup = load_manual_review_lookup(manual_review_csv)
    semantic_override = parse_optional_bool_flag(args.semantic_reasonable)
    selected_methods = parse_methods_arg(args.methods)
    manifest_cases = load_case_entries(root)
    bug_type_by_case = {c["name"]: c.get("bug_type", "") for c in manifest_cases}

    rows = []
    if args.sva_file and args.case:
        sva_path = Path(args.sva_file).resolve()
        method = infer_method_from_sva_file(sva_path)
        candidate_index = infer_candidate_index_from_sva_file(sva_path)
        review_info = manual_review_lookup.get((args.case, method or ""), {})
        semantic_reasonable = semantic_override
        reviewed_assertion = ""
        if semantic_reasonable is None:
            semantic_reasonable = review_info.get("semantic_reasonable")
            reviewed_assertion = str(review_info.get("reviewed_assertion", ""))
        if semantic_override is None:
            semantic_review_label = str(review_info.get("semantic_review_label", ""))
        else:
            semantic_review_label = f"override:{semantic_override}"
        rows.append(
            evaluate_one(
                root,
                args.case,
                sva_path,
                args.iverilog,
                args.vvp,
                bug_type=bug_type_by_case.get(args.case, ""),
                method=method or "",
                candidate_index=candidate_index,
                semantic_reasonable=semantic_reasonable,
                semantic_review_label=semantic_review_label,
                reviewed_assertion=reviewed_assertion,
            )
        )
    else:
        cases = [args.case] if args.case else [c["name"] for c in manifest_cases]
        for c in cases:
            case_dir = root / c
            sva_files = infer_sva_files(case_dir, selected_methods)
            for sf in sva_files:
                method = infer_method_from_sva_file(sf)
                candidate_index = infer_candidate_index_from_sva_file(sf)
                review_info = manual_review_lookup.get((c, method or ""), {})
                semantic_reasonable = semantic_override
                reviewed_assertion = ""
                if semantic_reasonable is None:
                    semantic_reasonable = review_info.get("semantic_reasonable")
                    reviewed_assertion = str(review_info.get("reviewed_assertion", ""))
                if semantic_override is None:
                    semantic_review_label = str(review_info.get("semantic_review_label", ""))
                else:
                    semantic_review_label = f"override:{semantic_override}"
                rows.append(
                    evaluate_one(
                        root,
                        c,
                        sf,
                        args.iverilog,
                        args.vvp,
                        bug_type=bug_type_by_case.get(c, ""),
                        method=method or "",
                        candidate_index=candidate_index,
                        semantic_reasonable=semantic_reasonable,
                        semantic_review_label=semantic_review_label,
                        reviewed_assertion=reviewed_assertion,
                    )
                )

    out_csv = Path(args.output_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "grammar_version",
        "case_name",
        "bug_type",
        "method",
        "candidate_index",
        "sva_file",
        "syntax_pass",
        "analysis_supported",
        "compile_ok",
        "pass_on_correct",
        "fail_on_buggy",
        "non_vacuous",
        "antecedent_triggered",
        "correct_antecedent_hits",
        "buggy_antecedent_hits",
        "correct_fail_count",
        "buggy_fail_count",
        "semantic_reasonable",
        "semantic_review_label",
        "trace_overfit",
        "trace_overfit_reason",
        "trace_literal_warning",
        "trace_literal_warning_reason",
        "unsupported_reason",
        "heldout_compile_ok",
        "heldout_pass_on_correct",
        "heldout_fail_on_buggy",
        "heldout_non_vacuous",
        "heldout_antecedent_triggered",
        "heldout_correct_antecedent_hits",
        "heldout_buggy_antecedent_hits",
        "heldout_correct_fail_count",
        "heldout_buggy_fail_count",
        "heldout_compile_error",
        "strict_success",
        "failure_type",
        "assertion_line",
        "compile_error",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    print(f"[DONE] Wrote report: {out_csv}")
    for r in rows:
        print(
            f"{r['case_name']} | {Path(r['sva_file']).name} | "
            f"template={r['syntax_pass']} compile={r['compile_ok']} correct_pass={r['pass_on_correct']} "
            f"buggy_fail={r['fail_on_buggy']} non_vacuous={r['non_vacuous']} "
            f"strict_success={r['strict_success']} failure_type={r['failure_type']}"
        )


if __name__ == "__main__":
    main()
