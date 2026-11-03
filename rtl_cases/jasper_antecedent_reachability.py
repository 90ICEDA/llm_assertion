#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from evaluate_generated_sva import parse_dut_ports, parse_module_name
from sva_eval_grammar import extract_single_assertion as shared_extract_single_assertion


REPORT_COVER_STATUS_START = "### AF_ANTECEDENT_COVER_STATUS_START ###"
REPORT_COVER_STATUS_END = "### AF_ANTECEDENT_COVER_STATUS_END ###"
REPORT_UNDETECTABLE_START = "### AF_UNDETECTABLE_START ###"
REPORT_UNDETECTABLE_END = "### AF_UNDETECTABLE_END ###"
REPORT_UNPROCESSED_START = "### AF_UNPROCESSED_START ###"
REPORT_UNPROCESSED_END = "### AF_UNPROCESSED_END ###"


def extract_single_assertion(sva_text: str) -> Tuple[str, Optional[str], str, str, str]:
    return shared_extract_single_assertion(sva_text)


def split_top_level_implication(body: str) -> Tuple[str, str, str]:
    text = body.strip().rstrip(";").strip()
    depth_paren = 0
    depth_brack = 0
    depth_brace = 0
    for idx, ch in enumerate(text):
        if ch == "(":
            depth_paren += 1
        elif ch == ")":
            depth_paren = max(0, depth_paren - 1)
        elif ch == "[":
            depth_brack += 1
        elif ch == "]":
            depth_brack = max(0, depth_brack - 1)
        elif ch == "{":
            depth_brace += 1
        elif ch == "}":
            depth_brace = max(0, depth_brace - 1)
        if depth_paren == 0 and depth_brack == 0 and depth_brace == 0:
            if text.startswith("|->", idx):
                return text[:idx].rstrip(), "|->", text[idx + 3 :].lstrip()
            if text.startswith("|=>", idx):
                return text[:idx].rstrip(), "|=>", text[idx + 3 :].lstrip()
    raise ValueError(f"No top-level implication operator found in: {body}")


def build_antecedent_cover_body(assertion_text: str, clock_signal: str) -> str:
    _assertion_line, disable_expr, ante, _op, _cons = extract_single_assertion(assertion_text)
    parts = [f"@(posedge {clock_signal})"]
    if disable_expr:
        parts.append(f"disable iff ({disable_expr})")
    parts.append(f"({ante})")
    return " ".join(parts) + ";"


def normalize_tcl_path(path: Path) -> str:
    return path.resolve().as_posix()


def infer_clock_signal(ports: List[Tuple[str, str]]) -> str:
    names = [name for name, _ in ports]
    for preferred in ["clk", "clk_i", "clock", "clk_i"]:
        if preferred in names:
            return preferred
    return "clk"


def infer_reset_signal(ports: List[Tuple[str, str]]) -> Optional[str]:
    names = [name for name, _ in ports]
    for preferred in ["rst_n", "rst_ni", "reset_n", "rst_an", "rst_l"]:
        if preferred in names:
            return preferred
    for preferred in ["rst", "rst_i", "reset"]:
        if preferred in names:
            return preferred
    return None


def build_formal_module_text(
    top_module_name: str,
    ports: List[Tuple[str, str]],
    assertion_text: str,
    clock_signal: str,
    checker_module_name: str = "af_jg_checker",
) -> str:
    _assertion_line, disable_expr, ante, op, cons = extract_single_assertion(assertion_text)
    port_lines = []
    conn_lines = []
    for name, rng in ports:
        if rng:
            port_lines.append(f"    input logic {rng} {name}")
        else:
            port_lines.append(f"    input logic {name}")
        conn_lines.append(f"    .{name}({name})")
    port_decl = ",\n".join(port_lines)
    conn_decl = ",\n".join(conn_lines)
    body_parts = [f"@(posedge {clock_signal})"]
    if disable_expr:
        body_parts.append(f"disable iff ({disable_expr})")
    body_parts.append(f"({ante}) {op} ({cons})")
    assert_body = " ".join(body_parts) + ";"
    cover_body = build_antecedent_cover_body(assertion_text, clock_signal)
    return f"""module {checker_module_name} (
{port_decl}
);
    property af_gold_assert_p;
        {assert_body}
    endproperty
    af_gold_assert: assert property (af_gold_assert_p);

    property af_gold_antecedent_cover_p;
        {cover_body}
    endproperty
    af_gold_antecedent_cover: cover property (af_gold_antecedent_cover_p);
endmodule

bind {top_module_name} {checker_module_name} af_jg_checker_i (
{conn_decl}
);
"""


def build_formal_tcl_text(
    rtl_path: Path,
    bind_path: Path,
    top_module_name: str,
    clock_signal: str,
    reset_signal: Optional[str],
    prove_time_limit: str = "1m",
    cover_time_limit: str = "1m",
) -> str:
    reset_line = ""
    if reset_signal:
        if reset_signal.endswith("_n") or reset_signal.endswith("_ni") or reset_signal.endswith("_l"):
            reset_line = f"reset -expression !{reset_signal}"
        else:
            reset_line = f"reset -expression {reset_signal}"
    return f"""clear -all
analyze -clear
check_cov -init -model all -type all -exclude_module {top_module_name}_tb
analyze -sv12 {{{normalize_tcl_path(rtl_path)}}}
analyze -sv12 {{{normalize_tcl_path(bind_path)}}}
elaborate -top {top_module_name}
clock {clock_signal}
{reset_line}
prove -all -time_limit {prove_time_limit}
set proofs_status [get_status [get_property_list -include {{type {{assert}} disabled {{0}}}}]]
puts "proofs: $proofs_status"
if {{[catch {{cover -all -time_limit {cover_time_limit}}} af_cover_run_msg]}} {{
    puts "### AF_COVER_RUN_ERROR ###"
    puts $af_cover_run_msg
}}
set af_cover_props [get_property_list -include {{type {{cover}} disabled {{0}}}}]
set af_cover_status "__AF_NONE__"
if {{[llength $af_cover_props] > 0}} {{
    if {{[catch {{set af_cover_status [get_status $af_cover_props]}} af_cover_status_msg]}} {{
        set af_cover_status "__AF_ERROR__ $af_cover_status_msg"
    }}
}}
puts "{REPORT_COVER_STATUS_START}"
puts $af_cover_status
puts "{REPORT_COVER_STATUS_END}"
if {{[catch {{check_cov -measure -type all -verbose}} af_cov_measure_msg]}} {{
    puts "### AF_COVERAGE_MEASURE_ERROR ###"
    puts $af_cov_measure_msg
}}
set af_undetectable ""
if {{[catch {{set af_undetectable [check_cov -list -status undetectable -checker_mode coi]}} af_cov_undetectable_msg]}} {{
    set af_undetectable "__AF_ERROR__ $af_cov_undetectable_msg"
}}
puts "{REPORT_UNDETECTABLE_START}"
puts $af_undetectable
puts "{REPORT_UNDETECTABLE_END}"
set af_unprocessed ""
if {{[catch {{set af_unprocessed [check_cov -list -status unprocessed -checker_mode coi]}} af_cov_unprocessed_msg]}} {{
    set af_unprocessed "__AF_ERROR__ $af_cov_unprocessed_msg"
}}
puts "{REPORT_UNPROCESSED_START}"
puts $af_unprocessed
puts "{REPORT_UNPROCESSED_END}"
exit
"""


def _extract_marked_section(
    report_content: str, start_marker: str, end_marker: str
) -> Optional[str]:
    pattern = re.escape(start_marker) + r"\s*(.*?)\s*" + re.escape(end_marker)
    match = re.search(pattern, report_content, re.DOTALL)
    return match.group(1) if match else None


def _section_has_meaningful_entries(section_content: Optional[str]) -> Optional[bool]:
    if section_content is None:
        return None
    cleaned_lines = []
    for raw_line in section_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if line in {"{}", "[]"}:
            continue
        if lower in {"none", "null", "n/a", "no objects found", "no properties found"}:
            continue
        if lower.startswith("__af_error__"):
            return None
        cleaned_lines.append(line)
    return len(cleaned_lines) > 0


def _has_fatal_jasper_error(report_content: str) -> bool:
    fatal_patterns = [
        r"(?im)^\s*(?:fatal|internal\s+error)\s*:",
        r"(?im)^\s*error\s*:",
        r"(?im)^\s*\*\*?\s*error\b",
        r"(?im)\blicense\b.*\b(error|fail|denied|checkout failed)\b",
        r"(?im)\bcommand\s+not\s+found\b",
    ]
    ignored_patterns = [
        REPORT_COVER_STATUS_START,
        REPORT_COVER_STATUS_END,
        REPORT_UNDETECTABLE_START,
        REPORT_UNDETECTABLE_END,
        REPORT_UNPROCESSED_START,
        REPORT_UNPROCESSED_END,
        "### AF_COVER_RUN_ERROR ###",
        "### AF_COVERAGE_MEASURE_ERROR ###",
    ]
    filtered_lines = []
    for line in report_content.splitlines():
        if any(marker in line for marker in ignored_patterns):
            continue
        filtered_lines.append(line)
    filtered_report = "\n".join(filtered_lines)
    return any(re.search(pattern, filtered_report) for pattern in fatal_patterns)


def extract_proof_status(report_content: str) -> str:
    match = re.search(r"(?im)^proofs:\s*(?P<status>[^\n]+)$", report_content)
    if match:
        normalized = match.group("status").strip().lower()
        if "cex" in normalized or "falsified" in normalized:
            return "cex"
        if "proven" in normalized:
            return "proven"
        if "error" in normalized or "fail" in normalized:
            return "error"
        if "undetermined" in normalized or "unknown" in normalized or "inconclusive" in normalized:
            return "inconclusive"
    summary_section = re.search(
        r'==============================================================\nSUMMARY\n==============================================================\n(.*?)\n\n',
        report_content,
        re.DOTALL,
    )
    if not summary_section:
        return "error" if _has_fatal_jasper_error(report_content) else "inconclusive"
    summary_lines = summary_section.group(1).strip().split("\n")
    assertion_section = False
    assertion_statuses: Dict[str, int] = {}
    for line in summary_lines:
        stripped = line.strip()
        if stripped.startswith("assertions"):
            assertion_section = True
            continue
        if assertion_section and stripped.startswith("covers"):
            break
        if assertion_section:
            parts = line.split(":")
            if len(parts) == 2:
                status = parts[0].strip().lower()
                count = int(parts[1].strip().split()[0])
                assertion_statuses[status] = count
    non_zero_statuses = [status for status, count in assertion_statuses.items() if count > 0]
    if "- proven" in non_zero_statuses:
        return "proven"
    if "- cex" in non_zero_statuses or "- ar_cex" in non_zero_statuses:
        return "cex"
    if "- undetermined" in non_zero_statuses or "- unknown" in non_zero_statuses:
        return "inconclusive"
    if _has_fatal_jasper_error(report_content):
        return "error"
    return "inconclusive"


def extract_antecedent_reachability(report_content: str) -> Optional[bool]:
    cover_status_section = _extract_marked_section(
        report_content, REPORT_COVER_STATUS_START, REPORT_COVER_STATUS_END
    )
    if cover_status_section is not None:
        normalized = " ".join(
            line.strip()
            for line in cover_status_section.splitlines()
            if line.strip()
        ).lower()
        if normalized and not normalized.startswith("__af_error__"):
            if "uncoverable" in normalized or "unreachable" in normalized:
                return False
            if "covered" in normalized:
                return True
            if "__af_none__" in normalized:
                return None
            if "undetermined" in normalized or "unknown" in normalized:
                return None
    undetectable = _section_has_meaningful_entries(
        _extract_marked_section(report_content, REPORT_UNDETECTABLE_START, REPORT_UNDETECTABLE_END)
    )
    unprocessed = _section_has_meaningful_entries(
        _extract_marked_section(report_content, REPORT_UNPROCESSED_START, REPORT_UNPROCESSED_END)
    )
    if undetectable is False and unprocessed is False:
        return True
    if undetectable is True or unprocessed is True:
        return False
    if undetectable is not None or unprocessed is not None:
        return None
    legacy_patterns = [
        r"(?im)\b(assert(?:ion)?|property)\b.*\b(unreachable|vacuous|undetectable)\b",
        r"(?im)\b(unreachable|vacuous|undetectable)\b.*\b(assert(?:ion)?|property)\b",
    ]
    if any(re.search(pattern, report_content) for pattern in legacy_patterns):
        return False
    return None


def format_antecedent_reachability_value(value: Optional[bool]) -> str:
    if value is True:
        return "reachable"
    if value is False:
        return "unreachable"
    return "unknown"


def get_effective_proof_status(
    proof_status: str, antecedent_reachability: Optional[bool]
) -> str:
    if proof_status == "proven" and antecedent_reachability is False:
        return "proven_vacuous"
    if proof_status == "proven" and antecedent_reachability is None:
        return "proven_unknown_reachability"
    return proof_status


def read_jasper_results_csv(path: Optional[Path]) -> Dict[str, Dict[str, str]]:
    if path is None or not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {str(row.get("case_name", "")).strip(): row for row in rows if str(row.get("case_name", "")).strip()}


def parse_cached_reachability_row(case_name: str, row: Optional[Dict[str, str]]) -> Dict[str, object]:
    if not row:
        return {
            "jasper_available": False,
            "jasper_ran": False,
            "jasper_report_path": "",
            "jasper_exit_code": "",
            "proof_status": "unknown",
            "antecedent_reachability": None,
            "antecedent_reachability_label": "unknown",
            "effective_proof_status": "unknown",
            "formal_failure_reason": "missing_jasper_result",
        }
    label = str(row.get("antecedent_reachability_label", "")).strip().lower()
    if label == "reachable":
        reachability: Optional[bool] = True
    elif label == "unreachable":
        reachability = False
    else:
        reachability = None
    proof_status = str(row.get("proof_status", "")).strip() or "unknown"
    effective_proof_status = str(row.get("effective_proof_status", "")).strip() or proof_status
    return {
        "jasper_available": True,
        "jasper_ran": str(row.get("jasper_ran", "")).strip().lower() == "true",
        "jasper_report_path": str(row.get("jasper_report_path", "")).strip(),
        "jasper_exit_code": str(row.get("jasper_exit_code", "")).strip(),
        "proof_status": proof_status,
        "antecedent_reachability": reachability,
        "antecedent_reachability_label": str(row.get("antecedent_reachability_label", "")).strip() or "unknown",
        "effective_proof_status": effective_proof_status,
        "formal_failure_reason": str(row.get("formal_failure_reason", "")).strip(),
    }


def run_jasper_on_case(
    case_name: str,
    correct_v: Path,
    assertion_text: str,
    jasper_binary: str,
    report_path: Optional[Path] = None,
    prove_time_limit: str = "1m",
    cover_time_limit: str = "1m",
) -> Dict[str, object]:
    binary_path = shutil.which(jasper_binary)
    if binary_path is None and not Path(jasper_binary).exists():
        return {
            "jasper_available": False,
            "jasper_ran": False,
            "jasper_report_path": str(report_path or ""),
            "jasper_exit_code": "",
            "proof_status": "unknown",
            "antecedent_reachability": None,
            "antecedent_reachability_label": "unknown",
            "effective_proof_status": "unknown",
            "formal_failure_reason": f"Cannot find Jasper binary: {jasper_binary}",
        }

    correct_text = correct_v.read_text(encoding="utf-8")
    top_module_name = parse_module_name(correct_text)
    ports = parse_dut_ports(correct_text)
    clock_signal = infer_clock_signal(ports)
    reset_signal = infer_reset_signal(ports)

    with tempfile.TemporaryDirectory(prefix=f"jasper_case_{case_name}_") as td:
        temp_dir = Path(td)
        bind_path = temp_dir / "af_jg_bind.sv"
        tcl_path = temp_dir / "run_jasper.tcl"
        project_dir = temp_dir / "jgproj"
        bind_path.write_text(
            build_formal_module_text(top_module_name, ports, assertion_text, clock_signal),
            encoding="utf-8",
            newline="\n",
        )
        tcl_path.write_text(
            build_formal_tcl_text(
                correct_v,
                bind_path,
                top_module_name,
                clock_signal,
                reset_signal,
                prove_time_limit=prove_time_limit,
                cover_time_limit=cover_time_limit,
            ),
            encoding="utf-8",
            newline="\n",
        )
        cmd = [
            str(binary_path or jasper_binary),
            "-batch",
            "-proj",
            str(project_dir),
            "-tcl",
            str(tcl_path),
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(correct_v.parent),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        report_content = proc.stdout

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_content, encoding="utf-8", newline="\n")

    proof_status = extract_proof_status(report_content)
    antecedent_reachability = extract_antecedent_reachability(report_content)
    formal_failure_reason = ""
    if proc.returncode != 0 and proof_status in {"unknown", "error"}:
        formal_failure_reason = f"jasper_exit_{proc.returncode}"
    elif proof_status == "error":
        formal_failure_reason = "proof_status_error"
    elif antecedent_reachability is False:
        formal_failure_reason = "antecedent_unreachable"
    elif antecedent_reachability is None:
        formal_failure_reason = "antecedent_reachability_unknown"
    return {
        "jasper_available": True,
        "jasper_ran": True,
        "jasper_report_path": str(report_path or ""),
        "jasper_exit_code": proc.returncode,
        "proof_status": proof_status,
        "antecedent_reachability": antecedent_reachability,
        "antecedent_reachability_label": format_antecedent_reachability_value(antecedent_reachability),
        "effective_proof_status": get_effective_proof_status(proof_status, antecedent_reachability),
        "formal_failure_reason": formal_failure_reason,
    }
