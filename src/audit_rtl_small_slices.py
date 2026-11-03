#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from pathlib import Path

import pandas as pd

from rtl_context_slicing import extract_always_assign_blocks, extract_module_blocks, normalize_signal


IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_$]*\b")
DECL = re.compile(r"\b(?:input|output|inout|logic|wire|reg|integer|genvar)\b[^;()]*?\b([A-Za-z_][A-Za-z0-9_$]*)\b")
KEYWORDS = {
    "module", "endmodule", "input", "output", "inout", "logic", "wire", "reg", "always", "always_ff",
    "always_comb", "always_latch", "assign", "begin", "end", "if", "else", "case", "endcase", "for",
    "generate", "endgenerate", "posedge", "negedge", "or", "and", "not", "int", "integer", "parameter",
    "localparam", "function", "endfunction", "return", "default", "signed", "unsigned",
}


def compact(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def changed_buggy_lines(correct: str, buggy: str) -> list[str]:
    lines = []
    for line in difflib.ndiff(correct.splitlines(), buggy.splitlines()):
        if line.startswith("+ "):
            text = compact(line[2:])
            if text:
                lines.append(text)
    return lines


def declared_identifiers(rtl: str) -> set[str]:
    declared = set()
    for match in DECL.finditer(rtl):
        declared.add(match.group(1))
    # ANSI port declarations and comma-separated declarations need a broader
    # token pass within module signatures.
    for _, module in extract_module_blocks(rtl):
        signature = module.split(");", 1)[0]
        for line in signature.splitlines():
            if re.search(r"\b(input|output|inout)\b", line):
                tokens = [t for t in IDENT.findall(line) if t not in KEYWORDS]
                if tokens:
                    declared.add(tokens[-1])
    return declared


def balanced_parse(slice_text: str) -> bool:
    modules = len(re.findall(r"(?m)^module\b", slice_text))
    endmodules = len(re.findall(r"(?m)^endmodule\b", slice_text))
    begins = len(re.findall(r"\bbegin\b", re.sub(r"//.*", "", slice_text)))
    ends = len(re.findall(r"\bend\b", re.sub(r"//.*", "", slice_text)))
    blocks = extract_always_assign_blocks(slice_text)
    return modules == 1 and endmodules in {0, 1} and begins == ends and bool(blocks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt_log", type=Path)
    parser.add_argument("cases_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    df = pd.read_csv(args.prompt_log, encoding="utf-8-sig")
    small = df.loc[df["method"] == "spec_rtl_signal_list_small_slice"].copy()
    full_lookup = {
        (str(row.model_label), str(row.case_id)): str(row.rtl_context_text)
        for row in df.loc[df["method"] == "spec_rtl_full"].itertuples()
    }
    manifest = json.loads((args.cases_root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]
    meta = {str(item["name"]): item for item in manifest}
    rows, review_docs = [], []
    for row in small.itertuples():
        case_id = str(row.case_id)
        slice_text = str(row.rtl_context_text)
        code_marker = slice_text.find("// Source module interface")
        slice_code = slice_text[code_marker:] if code_marker >= 0 else slice_text
        full_rtl = full_lookup.get((str(row.model_label), case_id), "")
        case_dir = args.cases_root / case_id
        correct = (case_dir / "correct.v").read_text(encoding="utf-8") if (case_dir / "correct.v").exists() else ""
        buggy = (case_dir / "buggy.v").read_text(encoding="utf-8") if (case_dir / "buggy.v").exists() else ""
        metadata = meta.get(case_id, {})
        golden = metadata.get("golden_sva") or {}
        forbidden = changed_buggy_lines(correct, buggy)
        forbidden.extend([compact(golden.get("sva")), compact(golden.get("expected_behavior")), compact(metadata.get("expected_behavior"))])
        forbidden = [text for text in forbidden if len(text) >= 12]
        compact_slice = compact(slice_text)
        leaks = [text for text in forbidden if text and text in compact_slice]
        signals = json.loads(str(row.relevant_signals_json))
        bases = {normalize_signal(sig) for sig in signals}
        declared = declared_identifiers(full_rtl)
        nonexistent = sorted(sig for sig in bases if sig not in declared and not re.search(rf"\b{re.escape(sig)}\b", full_rtl))
        all_blocks = extract_always_assign_blocks(extract_module_blocks(full_rtl)[-1][1] if extract_module_blocks(full_rtl) else full_rtl)
        relevant_blocks = [b for b in all_blocks if any(re.search(rf"\b{re.escape(sig)}\b", b["text"]) for sig in bases)]
        retained = [b for b in relevant_blocks if compact(b["text"]) in compact_slice]
        logic_retention_ok = len(retained) == len(relevant_blocks) or len(relevant_blocks) > 12 and len(retained) == 12
        slice_ids = {tok for tok in IDENT.findall(slice_code) if tok not in KEYWORDS and not tok.isupper()}
        unknown_refs = sorted(tok for tok in slice_ids if tok not in declared and tok not in bases and not re.match(r"^(AUTO|SLICE)$", tok))
        # Unknown references are reported for review; many are parameters or
        # package symbols, so the hard nonexistence check is limited to the
        # requested relevant signals.
        metadata_payload = json.loads(str(row.small_slice_metadata_json))
        result = {
            "model": row.model_label,
            "case_id": case_id,
            "parent_bug_id": row.parent_bug_id,
            "leak_free": not leaks,
            "leak_matches": ";".join(leaks),
            "relevant_signal_count": len(bases),
            "nonexistent_relevant_signals": ";".join(nonexistent),
            "all_relevant_signals_exist": not nonexistent,
            "relevant_block_count": len(relevant_blocks),
            "retained_relevant_block_count": len(retained),
            "related_logic_retained": logic_retention_ok,
            "balanced_parse_ok": balanced_parse(slice_code),
            "selected_blocks_are_exact_source_blocks": all(compact(b["text"]) in compact(full_rtl) for b in retained),
            "selected_block_count": metadata_payload.get("selected_block_count", 0),
            "uses_golden_sva": metadata_payload.get("uses_golden_sva"),
            "uses_trace": metadata_payload.get("uses_trace"),
            "uses_mutation_diff": metadata_payload.get("uses_mutation_diff"),
            "unknown_reference_review": ";".join(unknown_refs[:50]),
        }
        result["automatic_audit_ok"] = (
            result["leak_free"] and result["all_relevant_signals_exist"]
            and result["related_logic_retained"] and result["balanced_parse_ok"]
            and result["selected_blocks_are_exact_source_blocks"]
            and result["uses_golden_sva"] is False and result["uses_trace"] is False
            and result["uses_mutation_diff"] is False
        )
        rows.append(result)
        review_docs.append(
            f"## {case_id}\n\n"
            f"- Parent: `{row.parent_bug_id}`\n- Signals: `{', '.join(sorted(bases))}`\n"
            f"- Relevant blocks: `{len(relevant_blocks)}`; retained: `{len(retained)}`\n"
            f"- Automatic audit: `{'PASS' if result['automatic_audit_ok'] else 'FAIL'}`\n"
            f"- Exact source blocks: `{result['selected_blocks_are_exact_source_blocks']}`\n"
            f"- Unknown-reference review: `{result['unknown_reference_review']}`\n\n"
            f"```systemverilog\n{slice_text}\n```\n"
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.output_dir / "rtl_small_slice_audit.csv", index=False, encoding="utf-8-sig")
    (args.output_dir / "manual_review_20cases.md").write_text("# RTL Small Slice Manual Review\n\n" + "\n".join(review_docs), encoding="utf-8")
    summary = {
        "audited_rows": len(rows),
        "unique_cases": len({r["case_id"] for r in rows}),
        "automatic_pass_rows": sum(r["automatic_audit_ok"] for r in rows),
        "automatic_fail_rows": sum(not r["automatic_audit_ok"] for r in rows),
    }
    (args.output_dir / "rtl_small_slice_audit_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
