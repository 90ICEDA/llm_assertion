#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from sva_eval_grammar import (
    GRAMMAR_VERSION,
    extract_single_assertion as shared_extract_single_assertion,
)


ASSERT_COUNT_RE = re.compile(r"\bassert\s+property\b", re.IGNORECASE)
IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")
NUMBER_RE = re.compile(r"\b\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+\b")
BITSEL_RE = re.compile(r"\b([A-Za-z_]\w*)\[(\d+(?::\d+)?)\]")

KEYWORDS = {
    "assert",
    "property",
    "posedge",
    "disable",
    "iff",
    "clk",
    "rst_n",
    "and",
    "or",
    "not",
    "past",
    "true",
    "false",
}

ACTIVE_RESET_PATTERNS = [
    re.compile(r"!\s*rst_n"),
    re.compile(r"\brst_n\s*==\s*(?:1'b0|1'b0|0)\b"),
    re.compile(r"\brst_n\s*!=\s*(?:1'b1|1)\b"),
    re.compile(r"\brst_n\s*===\s*(?:1'b0|0)\b"),
]


def normalize_expr(expr: str) -> str:
    return re.sub(r"\s+", "", expr.strip())


def strip_outer_parens(expr: str) -> str:
    text = expr.strip()
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        balanced = True
        for idx, ch in enumerate(text):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and idx != len(text) - 1:
                    balanced = False
                    break
        if not balanced or depth != 0:
            break
        text = text[1:-1].strip()
    return text


def strip_sv_number_literals(text: str) -> str:
    return NUMBER_RE.sub("0", text)


def extract_identifiers(text: str) -> List[str]:
    return IDENT_RE.findall(strip_sv_number_literals(text))


def split_top_level(expr: str, sep: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and expr.startswith(sep, i):
            parts.append(expr[start:i].strip())
            i += len(sep)
            start = i
            continue
        i += 1
    parts.append(expr[start:].strip())
    return [p for p in parts if p]


def extract_single_assertion(sva_text: str) -> Tuple[str, str, str, str]:
    _full, disable_expr, ante, op, cons = shared_extract_single_assertion(sva_text)
    return disable_expr, ante, op, cons


def find_top_level_operator(expr: str, operators: Sequence[str]) -> Optional[Tuple[str, str, str]]:
    depth = 0
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0:
            for op in operators:
                if expr.startswith(op, i):
                    return expr[:i].strip(), op, expr[i + len(op) :].strip()
        i += 1
    return None


def is_true_literal(expr: str) -> bool:
    return normalize_expr(expr).lower() in {"1", "1'b1", "true"}


def is_false_literal(expr: str) -> bool:
    return normalize_expr(expr).lower() in {"0", "1'b0", "false"}


def is_reflexive_compare(expr: str) -> bool:
    parsed = find_top_level_operator(strip_outer_parens(expr), ["===", "!==", "==", "!="])
    if not parsed:
        return False
    left, op, right = parsed
    if normalize_expr(left) != normalize_expr(right):
        return False
    return op in {"===", "=="} or op in {"!=", "!=="}


def has_boolean_tautology(expr: str) -> bool:
    text = strip_outer_parens(expr)
    if is_true_literal(text):
        return True
    if is_reflexive_compare(text):
        return True

    for sep in ["||", "|"]:
        parts = split_top_level(text, sep)
        if len(parts) == 2:
            lhs = strip_outer_parens(parts[0])
            rhs = strip_outer_parens(parts[1])
            if normalize_expr(lhs) == normalize_expr(rhs):
                return True
            if normalize_expr(lhs) == normalize_expr(f"!({rhs})") or normalize_expr(rhs) == normalize_expr(f"!({lhs})"):
                return True
            cmp_l = find_top_level_operator(lhs, ["===", "!==", "==", "!="])
            cmp_r = find_top_level_operator(rhs, ["===", "!==", "==", "!="])
            if cmp_l and cmp_r:
                ll, lop, lr = cmp_l
                rl, rop, rr = cmp_r
                same_pair = normalize_expr(ll) == normalize_expr(rl) and normalize_expr(lr) == normalize_expr(rr)
                swapped_pair = normalize_expr(ll) == normalize_expr(rr) and normalize_expr(lr) == normalize_expr(rl)
                if (same_pair or swapped_pair) and {lop, rop} == {"==", "!="}:
                    return True
                if (same_pair or swapped_pair) and {lop, rop} == {"===", "!=="}:
                    return True
    return False


def has_same_cycle_self_update(expr: str, op: str) -> bool:
    if op != "|->":
        return False
    text = strip_outer_parens(expr)
    parsed = find_top_level_operator(text, ["===", "=="])
    if not parsed:
        return False
    left, _cmp, right = parsed
    nleft = normalize_expr(left)
    nright = normalize_expr(right)
    if nleft == nright:
        return False
    add_patterns = [
        rf"^{re.escape(nleft)}[\+\-].+$",
        rf"^.+[\+\-]{re.escape(nleft)}$",
    ]
    for pat in add_patterns:
        if re.match(pat, nright):
            return True
    for pat in [
        rf"^{re.escape(nright)}[\+\-].+$",
        rf"^.+[\+\-]{re.escape(nright)}$",
    ]:
        if re.match(pat, nleft):
            return True
    return False


def has_control_signal_misuse(expr: str) -> bool:
    if re.search(r"@\s*\(", expr):
        return True
    if re.search(r"\bclk\b", expr):
        return True
    return False


def infer_vector_signals(columns: Sequence[str]) -> List[str]:
    vectors = set()
    for col in columns:
        m = re.match(r"^([A-Za-z_]\w*)\[\d+(?::\d+)?\]$", col)
        if m:
            vectors.add(m.group(1))
    return sorted(vectors)


def analyze_sva(
    sva_text: str,
    allowed_signals: Sequence[str],
    vector_signals: Sequence[str] | None = None,
) -> Dict[str, object]:
    reasons: List[str] = []
    warning_reasons: List[str] = []
    vector_set = set(vector_signals or [])
    text = sva_text.strip()

    if not text:
        reasons.append("empty_assertion")
        return {
            "pass": False,
            "reasons": reasons,
            "warnings": warning_reasons,
            "grammar_version": GRAMMAR_VERSION,
        }

    if len(ASSERT_COUNT_RE.findall(text)) != 1:
        reasons.append("multiple_assertions")

    try:
        disable_expr, ante, op, cons = extract_single_assertion(text)
    except Exception:
        reasons.append("format_mismatch_or_unparsable_assertion")
        return {
            "pass": False,
            "reasons": reasons,
            "warnings": warning_reasons,
            "grammar_version": GRAMMAR_VERSION,
        }

    if "|->" in ante or "|=>" in ante or "|->" in cons or "|=>" in cons:
        reasons.append("nested_implication")

    if has_control_signal_misuse(ante) or has_control_signal_misuse(cons):
        reasons.append("reset_or_clock_condition_misuse")

    if normalize_expr(ante) == normalize_expr(cons):
        reasons.append("tautology_identical_antecedent_consequent")

    if has_boolean_tautology(cons):
        reasons.append("tautology_in_consequent")
    elif has_boolean_tautology(ante):
        warning_reasons.append("tautology_in_antecedent")

    if is_false_literal(ante):
        reasons.append("never_triggering_antecedent")

    if has_same_cycle_self_update(cons, op):
        reasons.append("same_cycle_self_update_compare")

    if has_same_cycle_self_update(ante, op):
        warning_reasons.append("same_cycle_self_update_in_antecedent")

    allowed = set(allowed_signals) | {"clk", "rst_n"}
    expr_text = " ".join(part for part in [disable_expr, ante, cons] if part)
    unknown = sorted(
        {
            tok
            for tok in extract_identifiers(expr_text)
            if tok not in KEYWORDS and tok not in allowed
        }
    )
    if unknown:
        reasons.append("uses_nonexistent_signal:" + ",".join(unknown))

    bad_indexed = sorted(
        {
            f"{name}[{sel}]"
            for name, sel in BITSEL_RE.findall(expr_text)
            if name in allowed and name not in vector_set
        }
    )
    if bad_indexed:
        reasons.append("scalar_bit_select:" + ",".join(bad_indexed))

    return {
        "pass": len(reasons) == 0,
        "reasons": reasons,
        "warnings": warning_reasons,
        "grammar_version": GRAMMAR_VERSION,
        "disable_expr": disable_expr,
        "antecedent": ante,
        "op": op,
        "consequent": cons,
    }


def load_case_meta(root: Path, case_name: str) -> Dict[str, object]:
    manifest = json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        if case["name"] == case_name:
            return case
    raise KeyError(f"Unknown case: {case_name}")


def collect_vector_signals(case_dir: Path) -> List[str]:
    columns: List[str] = []
    for name in ["waveform_good.csv", "waveform_bad.csv"]:
        path = case_dir / name
        if not path.exists():
            continue
        header = path.read_text(encoding="utf-8").splitlines()[0].strip()
        if header:
            columns.extend(part.strip() for part in header.split(","))
    return infer_vector_signals(columns)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Static SVA filter for low-level format and semantics errors."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument("--case", help="Case name to load allowed signals from manifest.")
    parser.add_argument("--sva-file", help="Path to an SVA file to check.")
    parser.add_argument("--sva-text", help="Inline SVA text to check.")
    parser.add_argument(
        "--allowed-signals",
        help="Comma-separated allowed signals; overrides manifest case signals when provided.",
    )
    args = parser.parse_args()

    if not args.sva_file and not args.sva_text:
        parser.error("Provide either --sva-file or --sva-text.")

    root = Path(args.root).resolve()
    case_meta: Dict[str, object] = {}
    allowed_signals: List[str] = []
    vector_signals: List[str] = []

    if args.case:
        case_meta = load_case_meta(root, args.case)
        allowed_signals = list(case_meta.get("key_signals", []))
        vector_signals = collect_vector_signals(root / args.case)

    if args.allowed_signals:
        allowed_signals = [item.strip() for item in args.allowed_signals.split(",") if item.strip()]

    if not allowed_signals:
        parser.error("Allowed signals are required via --case or --allowed-signals.")

    if args.sva_file:
        sva_text = Path(args.sva_file).resolve().read_text(encoding="utf-8")
    else:
        sva_text = args.sva_text or ""

    result = analyze_sva(sva_text, allowed_signals, vector_signals)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
