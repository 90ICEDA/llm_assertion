from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any

from rtl_context_slicing import extract_automatic_small_slice as automatic_small_slice

from run_multi_model_small_eval import (
    MODEL_SPECS,
    aggregate_and_write_outputs,
    build_case_bundles,
    classify_failure,
    collect_candidates,
    make_generation_prompt,
    probe_property_support,
    resolve_selected_case_ids,
    run_case_eval,
    str_to_bool,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_ROOT = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "scale120_rtl_context_ablation_data"

METHOD_SPECS: list[dict[str, str]] = [
    {
        "method": "spec_only",
        "context_label": "Specification only",
    },
    {
        "method": "spec_rtl_full",
        "context_label": "Spec + full RTL",
    },
    {
        "method": "spec_rtl_interface",
        "context_label": "Spec + interface",
    },
    {
        "method": "spec_rtl_signal_list",
        "context_label": "Spec + signal list",
    },
    {
        "method": "spec_rtl_sliced",
        "context_label": "Spec + sliced RTL",
    },
    {
        "method": "spec_rtl_signal_list_small_slice",
        "context_label": "Spec + signal list + automatic small slice",
    },
    {"method": "spec_rtl_one_hop_slice", "context_label": "Spec + one-hop RTL slice"},
    {"method": "spec_rtl_two_hop_slice", "context_label": "Spec + two-hop RTL slice"},
    {"method": "spec_rtl_signal_list_two_hop_slice", "context_label": "Spec + signal list + two-hop RTL slice"},
    {"method": "spec_rtl_random_slice", "context_label": "Spec + budget-matched random RTL slice"},
    {"method": "spec_rtl_wrong_signal_list", "context_label": "Spec + wrong-case signal list"},
]

METHOD_LABELS = {item["method"]: item["context_label"] for item in METHOD_SPECS}


def normalize_base_signal(sig: str) -> str:
    return str(sig).split("[", 1)[0].strip()


def extract_module_blocks(rtl_text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?ms)^module\s+([A-Za-z_][A-Za-z0-9_]*)\b.*?^endmodule\b")
    return [(match.group(1), match.group(0).strip()) for match in pattern.finditer(rtl_text)]


def extract_module_signature(module_block: str) -> str:
    lines = module_block.splitlines()
    collected: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started and stripped.startswith("module "):
            started = True
        if started:
            collected.append(line.rstrip())
            if stripped.endswith(");"):
                break
    return "\n".join(collected).strip()


def extract_wrapper_block(full_rtl: str) -> str:
    blocks = extract_module_blocks(full_rtl)
    return blocks[0][1] if blocks else full_rtl.strip()


def extract_source_signature(full_rtl: str) -> str:
    blocks = extract_module_blocks(full_rtl)
    if len(blocks) >= 2:
        return extract_module_signature(blocks[-1][1])
    if blocks:
        return extract_module_signature(blocks[0][1])
    return ""


def extract_interface_context(full_rtl: str) -> str:
    wrapper = extract_wrapper_block(full_rtl)
    source_sig = extract_source_signature(full_rtl)
    parts = []
    if wrapper:
        parts.append("// Wrapper module and instance bindings\n" + wrapper)
    if source_sig:
        parts.append("// Source module interface\n" + source_sig)
    return "\n\n".join(part for part in parts if part).strip()


def parse_wrapper_ports(wrapper_block: str) -> list[dict[str, str]]:
    sig = extract_module_signature(wrapper_block)
    port_lines = []
    for raw_line in sig.splitlines():
        line = raw_line.strip().rstrip(",")
        if line.startswith(("input ", "output ", "inout ")):
            port_lines.append(line)
    ports: list[dict[str, str]] = []
    pattern = re.compile(
        r"^(input|output|inout)\s+(?:logic|wire|reg)?\s*(\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)$"
    )
    for line in port_lines:
        match = pattern.match(line)
        if not match:
            continue
        direction, width, name = match.groups()
        ports.append(
            {
                "direction": direction,
                "width": width or "",
                "name": name,
            }
        )
    return ports


def extract_instance_bindings(wrapper_block: str) -> list[str]:
    lines = wrapper_block.splitlines()
    bindings: list[str] = []
    in_instance = False
    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not in_instance and re.search(r"\bu_dut\s*\($", stripped):
            in_instance = True
            continue
        if in_instance:
            bindings.append(stripped.rstrip(","))
            if stripped == ");":
                break
    return [line for line in bindings if line and line != ");"]


def extract_signal_list_context(
    *,
    full_rtl: str,
    allowed_signals: list[str],
    additional_guidance: str,
) -> str:
    wrapper = extract_wrapper_block(full_rtl)
    ports = parse_wrapper_ports(wrapper)
    allowed_base = {normalize_base_signal(sig) for sig in allowed_signals}
    port_map = {port["name"]: port for port in ports}
    binding_lines = extract_instance_bindings(wrapper)

    parts = ["Signal inventory derived from wrapper RTL:"]
    for sig in allowed_signals:
        base = normalize_base_signal(sig)
        port = port_map.get(base)
        if port:
            width = f" {port['width']}" if port["width"] else ""
            parts.append(f"- {sig}: {port['direction']}{width}")
        else:
            parts.append(f"- {sig}: allowed signal")

    matched_bindings = []
    for line in binding_lines:
        if any(re.search(rf"\b{re.escape(sig)}\b", line) for sig in allowed_base):
            matched_bindings.append(line)
    if matched_bindings:
        parts.append("")
        parts.append("Relevant instance bindings:")
        parts.extend(f"- {line}" for line in matched_bindings)

    if additional_guidance.strip():
        parts.append("")
        parts.append("Waveform / naming hints:")
        for line in additional_guidance.splitlines():
            if line.strip():
                parts.append(f"- {line.strip()}")

    return "\n".join(parts).strip()


def extract_sliced_rtl_context(full_rtl: str, allowed_signals: list[str], *, radius: int = 2, max_lines: int = 180) -> str:
    wrapper = extract_wrapper_block(full_rtl)
    source_blocks = extract_module_blocks(full_rtl)
    source_module = source_blocks[-1][1] if source_blocks else full_rtl
    source_lines = source_module.splitlines()
    signal_bases = sorted({normalize_base_signal(sig) for sig in allowed_signals if sig.strip()})

    hit_idxs: list[int] = []
    for idx, line in enumerate(source_lines):
        if any(re.search(rf"\b{re.escape(sig)}\b", line) for sig in signal_bases):
            hit_idxs.append(idx)

    spans: list[tuple[int, int]] = []
    for idx in hit_idxs:
        start = max(0, idx - radius)
        end = min(len(source_lines), idx + radius + 1)
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))

    kept_lines: list[str] = []
    for start, end in spans:
        if kept_lines:
            kept_lines.append("")
        kept_lines.extend(line.rstrip() for line in source_lines[start:end])
        if len(kept_lines) >= max_lines:
            kept_lines = kept_lines[:max_lines]
            break

    parts = []
    if wrapper:
        parts.append("// Wrapper module\n" + wrapper)
    source_sig = extract_source_signature(source_module)
    if source_sig:
        parts.append("// Source module signature\n" + source_sig)
    if kept_lines:
        parts.append("// Source RTL slices touching allowed signals\n" + "\n".join(kept_lines).strip())
    return "\n\n".join(part for part in parts if part).strip()


def _strip_sv_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    out = []
    i = 0
    while i < len(line):
        if in_block_comment:
            end = line.find("*/", i)
            if end < 0:
                return "".join(out), True
            i = end + 2
            in_block_comment = False
        elif line.startswith("//", i):
            break
        elif line.startswith("/*", i):
            in_block_comment = True
            i += 2
        else:
            out.append(line[i])
            i += 1
    return "".join(out), in_block_comment


def extract_always_assign_blocks(module_text: str) -> list[dict[str, Any]]:
    """Lexically extract complete always/assign blocks without semantic hints.

    This intentionally does not accept spec, golden SVA, traces, or mutation
    metadata. Selection is performed later using only the supplied signal list.
    """
    lines = module_text.splitlines()
    clean_lines = []
    in_comment = False
    for line in lines:
        clean, in_comment = _strip_sv_comments(line, in_comment)
        clean_lines.append(clean)
    blocks: list[dict[str, Any]] = []
    i = 0
    start_re = re.compile(r"^\s*(always(?:_ff|_comb|_latch)?\b|assign\b)")
    token_re = re.compile(r"\b(begin|end)\b")
    while i < len(lines):
        match = start_re.match(clean_lines[i])
        if not match:
            i += 1
            continue
        kind = "assign" if match.group(1) == "assign" else "always"
        start = i
        if kind == "assign":
            while i < len(lines) and ";" not in clean_lines[i]:
                i += 1
            end = min(i + 1, len(lines))
            i = end
        else:
            depth = 0
            saw_begin = False
            while i < len(lines):
                for token in token_re.findall(clean_lines[i]):
                    if token == "begin":
                        depth += 1
                        saw_begin = True
                    elif saw_begin:
                        depth -= 1
                if saw_begin and depth <= 0:
                    i += 1
                    break
                if not saw_begin and ";" in clean_lines[i] and i > start:
                    i += 1
                    break
                i += 1
            end = min(i, len(lines))
        blocks.append({
            "kind": kind,
            "start_line": start + 1,
            "end_line": end,
            "text": "\n".join(lines[start:end]).strip(),
        })
    return blocks


def extract_automatic_small_slice(full_rtl: str, relevant_signals: list[str], *, max_blocks: int = 12) -> tuple[str, dict[str, Any]]:
    source_blocks = extract_module_blocks(full_rtl)
    source_module = source_blocks[-1][1] if source_blocks else full_rtl
    signals = sorted({normalize_base_signal(sig) for sig in relevant_signals if str(sig).strip()})
    all_blocks = extract_always_assign_blocks(source_module)
    selected = []
    for block in all_blocks:
        touched = [sig for sig in signals if re.search(rf"\b{re.escape(sig)}\b", block["text"])]
        if touched:
            selected.append({**block, "matched_signals": touched})
    selected = selected[:max_blocks]
    parts = []
    signature = extract_module_signature(source_module)
    if signature:
        parts.append("// Source module interface\n" + signature)
    for block in selected:
        parts.append(
            f"// AUTO-SLICE {block['kind']} lines {block['start_line']}-{block['end_line']} "
            f"signals={','.join(block['matched_signals'])}\n{block['text']}"
        )
    metadata = {
        "policy": "relevant_signal_lexical_always_assign_blocks_v1",
        "input_signal_count": len(signals),
        "available_block_count": len(all_blocks),
        "selected_block_count": len(selected),
        "selected_blocks": [
            {k: block[k] for k in ["kind", "start_line", "end_line", "matched_signals"]}
            for block in selected
        ],
        "uses_golden_sva": False,
        "uses_trace": False,
        "uses_mutation_diff": False,
    }
    return "\n\n".join(parts).strip(), metadata


SV_IDENTIFIERS = re.compile(r"\b[A-Za-z_][A-Za-z0-9_$]*\b")
SV_KEYWORDS = {
    "always", "always_ff", "always_comb", "assign", "begin", "end", "if", "else",
    "case", "endcase", "logic", "wire", "reg", "input", "output", "module", "endmodule",
    "posedge", "negedge", "or", "parameter", "integer", "localparam",
}


def block_identifiers(text: str) -> set[str]:
    return {token for token in SV_IDENTIFIERS.findall(text) if token not in SV_KEYWORDS}


def dependency_slice(full_rtl: str, relevant_signals: list[str], *, hops: int) -> tuple[str, dict[str, Any]]:
    source_blocks = extract_module_blocks(full_rtl)
    source_module = source_blocks[-1][1] if source_blocks else full_rtl
    blocks = extract_always_assign_blocks(source_module)
    frontier = {normalize_base_signal(sig) for sig in relevant_signals if str(sig).strip()}
    selected: set[int] = set()
    for _ in range(hops):
        newly_selected = {
            idx for idx, block in enumerate(blocks)
            if idx not in selected and frontier.intersection(block_identifiers(block["text"]))
        }
        if not newly_selected:
            break
        selected |= newly_selected
        for idx in newly_selected:
            frontier |= block_identifiers(blocks[idx]["text"])
    ordered = [blocks[idx] for idx in sorted(selected)]
    parts = []
    signature = extract_module_signature(source_module)
    if signature:
        parts.append("// Source module interface\n" + signature)
    for block in ordered:
        parts.append(f"// {hops}-HOP SLICE {block['kind']} lines {block['start_line']}-{block['end_line']}\n{block['text']}")
    metadata = {
        "policy": f"lexical_block_dependency_{hops}_hop_v1",
        "selected_block_count": len(ordered),
        "selected_line_count": sum(int(b["end_line"]) - int(b["start_line"]) + 1 for b in ordered),
        "uses_golden_sva": False, "uses_trace": False, "uses_mutation_diff": False,
    }
    return "\n\n".join(parts).strip(), metadata


def random_budget_matched_slice(full_rtl: str, *, case_id: str, target_blocks: int) -> tuple[str, dict[str, Any]]:
    source_blocks = extract_module_blocks(full_rtl)
    source_module = source_blocks[-1][1] if source_blocks else full_rtl
    blocks = extract_always_assign_blocks(source_module)
    seed = int(hashlib.sha256(f"mechanism-random-slice-v1|{case_id}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)
    chosen = sorted(rng.sample(range(len(blocks)), min(target_blocks, len(blocks)))) if blocks else []
    parts = []
    signature = extract_module_signature(source_module)
    if signature:
        parts.append("// Source module interface\n" + signature)
    for idx in chosen:
        block = blocks[idx]
        parts.append(f"// RANDOM CONTROL {block['kind']} lines {block['start_line']}-{block['end_line']}\n{block['text']}")
    return "\n\n".join(parts).strip(), {
        "policy": "deterministic_budget_matched_random_blocks_v1", "seed": seed,
        "selected_block_count": len(chosen), "selected_block_indices": chosen,
        "uses_golden_sva": False, "uses_trace": False, "uses_mutation_diff": False,
    }


def build_context_payloads(bundle: dict[str, Any]) -> dict[str, str]:
    full_rtl = str(bundle["rtl_text"]).strip()
    allowed_signals = list(bundle["allowed_signals"])
    additional_guidance = str(bundle.get("additional_guidance", "") or "")
    signal_list = extract_signal_list_context(
        full_rtl=full_rtl,
        allowed_signals=allowed_signals,
        additional_guidance=additional_guidance,
    )
    clean_signal_list = extract_signal_list_context(
        full_rtl=full_rtl,
        allowed_signals=allowed_signals,
        additional_guidance="",
    )
    small_slice, small_slice_metadata = automatic_small_slice(full_rtl, allowed_signals)
    wrapper_ports = parse_wrapper_ports(extract_wrapper_block(full_rtl))
    output_seeds = [
        port["name"] for port in wrapper_ports
        if port["direction"] == "output" and port["name"] in {normalize_base_signal(sig) for sig in allowed_signals}
    ]
    if not output_seeds:
        allowed_bases = {normalize_base_signal(sig) for sig in allowed_signals}
        output_seeds = [
            name for name in re.findall(
                r"\boutput\s+(?:logic|wire|reg)?\s*(?:\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)",
                extract_module_signature(extract_wrapper_block(full_rtl)),
            ) if name in allowed_bases
        ]
    slice_seeds = output_seeds or allowed_signals
    one_hop, one_hop_metadata = dependency_slice(full_rtl, slice_seeds, hops=1)
    two_hop, two_hop_metadata = dependency_slice(full_rtl, slice_seeds, hops=2)
    random_slice, random_slice_metadata = random_budget_matched_slice(
        full_rtl, case_id=str(bundle["case_id"]), target_blocks=int(one_hop_metadata["selected_block_count"])
    )
    one_hop_metadata["seed_signals"] = slice_seeds
    two_hop_metadata["seed_signals"] = slice_seeds
    random_slice_metadata["budget_reference"] = "one_hop_selected_block_count"
    wrong_signals = list(bundle.get("wrong_allowed_signals", []))
    wrong_signal_list = extract_signal_list_context(
        full_rtl=full_rtl, allowed_signals=wrong_signals, additional_guidance=""
    )
    bundle["small_slice_metadata"] = small_slice_metadata
    bundle["mechanism_slice_metadata"] = {
        "one_hop": one_hop_metadata, "two_hop": two_hop_metadata, "random": random_slice_metadata,
        "wrong_signal_source_case": bundle.get("wrong_signal_source_case", ""),
    }
    return {
        "spec_only": "",
        "spec_rtl_full": full_rtl,
        "spec_rtl_interface": extract_interface_context(full_rtl),
        "spec_rtl_signal_list": signal_list,
        "spec_rtl_sliced": extract_sliced_rtl_context(full_rtl, allowed_signals),
        "spec_rtl_signal_list_small_slice": clean_signal_list + "\n\n" + small_slice,
        "spec_rtl_one_hop_slice": one_hop,
        "spec_rtl_two_hop_slice": two_hop,
        "spec_rtl_signal_list_two_hop_slice": clean_signal_list + "\n\n" + two_hop,
        "spec_rtl_random_slice": random_slice,
        "spec_rtl_wrong_signal_list": wrong_signal_list,
    }


def make_method_prompt(bundle: dict[str, Any], method: str, target_count: int) -> tuple[str, str]:
    context_payloads = bundle["context_payloads"]
    if method not in context_payloads:
        raise ValueError(f"Unsupported method: {method}")

    rtl_text = context_payloads[method]
    if method == "spec_only":
        trace_section = (
            "No waveform trace is provided for this run.\n"
            "Infer a strong but general property only from the specification.\n"
            "Still prefer a relation that should distinguish correct from buggy behavior."
        )
    else:
        trace_section = (
            "No waveform trace is provided for this run.\n"
            "Infer a strong but general property only from the specification and the provided RTL context.\n"
            "Treat the RTL context as implementation evidence, but prefer a reusable relation rather than a brittle literal."
        )
    prompt = make_generation_prompt(
        allowed_signals=bundle["allowed_signals"],
        spec=bundle["spec"],
        rtl_text=rtl_text,
        trace_section=trace_section,
        additional_guidance=bundle["additional_guidance"],
        target_count=target_count,
    )
    return prompt, rtl_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run RTL-context ablation over selected real-RTL cases. "
            "Compares spec-only against progressively richer RTL context variants."
        )
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("RTL_ABLATION_CASES_ROOT", str(DEFAULT_CASES_ROOT)),
        help="Dataset root containing case directories and case_manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("RTL_ABLATION_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)),
        help="Directory to store prompts, raw results, summaries, and per-model shards.",
    )
    parser.add_argument("--case", action="append", default=[], help="Case id to include. Repeat to select multiple.")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        default=str_to_bool(os.environ.get("RTL_ABLATION_ALL_CASES", "")),
        help="Select every case from case_manifest.json under --root.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=int(os.environ.get("RTL_ABLATION_MAX_CASES", "0") or "0"),
        help="Optional cap after case selection/sharding. 0 means no cap.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=int(os.environ.get("RTL_ABLATION_SHARD_INDEX", "0") or "0"),
        help="0-based shard index for splitting a large case list.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=int(os.environ.get("RTL_ABLATION_SHARD_COUNT", "1") or "1"),
        help="Number of shards for splitting a large case list.",
    )
    parser.add_argument("--model", action="append", default=[], help="Model label to include. Repeat to select multiple.")
    parser.add_argument(
        "--method",
        action="append",
        default=[],
        help=(
            "Method to include. Supported: spec_only, spec_rtl_full, spec_rtl_interface, "
            "spec_rtl_signal_list, spec_rtl_sliced, spec_rtl_signal_list_small_slice, "
            "spec_rtl_one_hop_slice, spec_rtl_two_hop_slice, spec_rtl_signal_list_two_hop_slice, "
            "spec_rtl_random_slice, spec_rtl_wrong_signal_list."
        ),
    )
    parser.add_argument(
        "--candidates-per-cell",
        type=int,
        default=int(os.environ.get("RTL_ABLATION_CANDIDATES_PER_CELL", "2") or "2"),
        help="How many distinct candidate assertions to request for each model/case/method cell.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=str_to_bool(os.environ.get("RTL_ABLATION_DRY_RUN", "")),
        help="Prepare prompts and metadata only; skip model calls and WSL evaluation.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=str_to_bool(os.environ.get("RTL_ABLATION_RESUME", "")),
        help="Skip a model/case/method cell only when all requested candidate indices already exist.",
    )
    return parser.parse_args()


def load_complete_cells(output_dir: Path, candidates_per_cell: int) -> set[tuple[str, str, str, str, str]]:
    """Return cells that already contain every candidate index from 1..k."""
    path = output_dir / "multi_model_results_raw.csv"
    if not path.exists():
        return set()
    indices: dict[tuple[str, str, str, str, str], set[int]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                str(row.get("model_label", "")),
                str(row.get("provider", "")),
                str(row.get("model_name", "")),
                str(row.get("case_id", "")),
                str(row.get("method", "")),
            )
            try:
                candidate_index = int(float(str(row.get("candidate_index", ""))))
            except ValueError:
                continue
            indices.setdefault(key, set()).add(candidate_index)
    required = set(range(1, candidates_per_cell + 1))
    return {key for key, found in indices.items() if required.issubset(found)}


def main() -> None:
    args = parse_args()

    cases_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    env_model_filter = {
        item.strip()
        for item in os.environ.get("RTL_ABLATION_MODEL_FILTER", "").split(",")
        if item.strip()
    }
    env_method_filter = {
        item.strip()
        for item in os.environ.get("RTL_ABLATION_METHOD_FILTER", "").split(",")
        if item.strip()
    }
    env_case_filter = {
        item.strip()
        for item in os.environ.get("RTL_ABLATION_CASE_FILTER", "").split(",")
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

    bundles = build_case_bundles(
        cases_root=cases_root,
        case_ids=selected_case_ids,
        abstracted_summary_lookup={},
    )
    manifest_path = cases_root / "case_manifest.json"
    parent_lookup: dict[str, str] = {}
    if manifest_path.exists():
        manifest_cases = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
        parent_lookup = {
            str(item["name"]): str(item.get("parent_bug_id") or item.get("seed_case_name") or item["name"])
            for item in manifest_cases
        }
    for idx, bundle in enumerate(bundles):
        wrong = bundles[(idx + 1) % len(bundles)]
        bundle["wrong_allowed_signals"] = list(wrong["allowed_signals"])
        bundle["wrong_signal_source_case"] = wrong["case_id"]
        bundle["parent_bug_id"] = parent_lookup.get(bundle["case_id"], bundle["case_id"])
        bundle["context_payloads"] = build_context_payloads(bundle)

    model_specs = [
        model_spec
        for model_spec in MODEL_SPECS
        if not requested_model_labels or model_spec["model_label"] in requested_model_labels
    ]
    if requested_methods:
        for method_name in requested_methods:
            if method_name not in METHOD_LABELS:
                raise ValueError(f"Unsupported --method: {method_name}")
        method_specs = [
            {
                "method": method_name,
                "trace_input_label": METHOD_LABELS[method_name],
                "context_label": METHOD_LABELS[method_name],
            }
            for method_name in requested_methods
        ]
    else:
        method_specs = [
            {
                "method": item["method"],
                "trace_input_label": item["context_label"],
                "context_label": item["context_label"],
            }
            for item in METHOD_SPECS
        ]

    if not bundles:
        raise RuntimeError("No cases selected for RTL context ablation.")
    if not model_specs:
        raise RuntimeError("No models selected for RTL context ablation.")
    if not method_specs:
        raise RuntimeError("No methods selected for RTL context ablation.")

    use_property = False
    if not args.dry_run:
        use_property = probe_property_support(
            bundles[0]["case_id"],
            cases_root=cases_root,
            runtime_dir=output_dir / "_probe",
        )

    all_results: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    complete_cells = load_complete_cells(output_dir, args.candidates_per_cell) if args.resume else set()

    for model_spec in model_specs:
        for bundle in bundles:
            for method_spec in method_specs:
                method = method_spec["method"]
                print(
                    f"[INFO] {model_spec['model_label']} | {bundle['case_id']} | {method}",
                    file=sys.stderr,
                )
                prompt_text, rtl_context_text = make_method_prompt(
                    bundle,
                    method,
                    args.candidates_per_cell,
                )
                prompt_dir = output_dir / "prompts" / model_spec["model_label"] / bundle["case_id"]
                prompt_path = prompt_dir / f"{method}.txt"
                write_text(prompt_path, prompt_text + "\n")

                cell_key = (
                    str(model_spec["model_label"]),
                    str(model_spec["provider"]),
                    str(model_spec["model_name"]),
                    str(bundle["case_id"]),
                    str(method),
                )
                if cell_key in complete_cells:
                    print(f"[SKIP complete] {model_spec['model_label']} | {bundle['case_id']} | {method}", file=sys.stderr)
                    continue

                method_prompt_rows: list[dict[str, Any]] = []
                method_result_rows: list[dict[str, Any]] = []
                candidates: list[str] = []
                raw_responses: list[str] = []
                if not args.dry_run:
                    candidates, raw_responses = collect_candidates(
                        model_spec=model_spec,
                        prompt=prompt_text,
                        target_count=args.candidates_per_cell,
                    )

                method_prompt_rows.append(
                    {
                        "model_label": model_spec["model_label"],
                        "provider": model_spec["provider"],
                        "model_name": model_spec["model_name"],
                        "case_id": bundle["case_id"],
                        "parent_bug_id": bundle["parent_bug_id"],
                        "selection_tags": bundle["selection_tags"],
                        "selection_reason": bundle["selection_reason"],
                        "method": method,
                        "trace_input_label": method_spec["trace_input_label"],
                        "context_label": method_spec["context_label"],
                        "prompt_path": str(prompt_path.resolve()),
                        "prompt_text": prompt_text,
                        "rtl_context_text": rtl_context_text,
                        "rtl_context_char_count": len(rtl_context_text),
                        "rtl_context_line_count": len(rtl_context_text.splitlines()) if rtl_context_text else 0,
                        "context_extraction_policy": (
                            bundle.get("small_slice_metadata", {}).get("policy", "")
                            if method == "spec_rtl_signal_list_small_slice" else ""
                        ),
                        "small_slice_selected_block_count": (
                            bundle.get("small_slice_metadata", {}).get("selected_block_count", 0)
                            if method == "spec_rtl_signal_list_small_slice" else 0
                        ),
                        "small_slice_uses_golden_sva": (
                            bundle.get("small_slice_metadata", {}).get("uses_golden_sva", False)
                            if method == "spec_rtl_signal_list_small_slice" else False
                        ),
                        "generalization_axis": "primary_context_to_heldout_trace_within_parent",
                        "overlap_status": "overlap",
                        "relevant_signal_source": "allowed_signals_from_spec_prompt",
                        "relevant_signals_json": json.dumps(bundle["allowed_signals"], ensure_ascii=False),
                        "small_slice_metadata_json": (
                            json.dumps(bundle.get("small_slice_metadata", {}), ensure_ascii=False)
                            if method == "spec_rtl_signal_list_small_slice" else ""
                        ),
                        "mechanism_control_metadata_json": json.dumps(
                            bundle.get("mechanism_slice_metadata", {}), ensure_ascii=False
                        ) if method in {
                            "spec_rtl_one_hop_slice", "spec_rtl_two_hop_slice",
                            "spec_rtl_signal_list_two_hop_slice", "spec_rtl_random_slice",
                            "spec_rtl_wrong_signal_list",
                        } else "",
                        "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
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
                    row = {
                        "model_label": model_spec["model_label"],
                        "provider": model_spec["provider"],
                        "model_name": model_spec["model_name"],
                        "case_id": bundle["case_id"],
                        "parent_bug_id": bundle["parent_bug_id"],
                        "selection_tags": bundle["selection_tags"],
                        "selection_reason": bundle["selection_reason"],
                        "method": method,
                        "trace_input_label": method_spec["trace_input_label"],
                        "context_label": method_spec["context_label"],
                        "mechanism_control_metadata_json": json.dumps(
                            bundle.get("mechanism_slice_metadata", {}), ensure_ascii=False
                        ) if method in {
                            "spec_rtl_one_hop_slice", "spec_rtl_two_hop_slice",
                            "spec_rtl_signal_list_two_hop_slice", "spec_rtl_random_slice",
                            "spec_rtl_wrong_signal_list",
                        } else "",
                        "generalization_axis": "primary_context_to_heldout_trace_within_parent",
                        "overlap_status": "overlap",
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
                        "literal_hardcoding": False,
                        "semantic_reasonable": False,
                        "semantic_reason": "",
                        "seen_good_ant_hits": int(eval_result["seen_good_ant_hits"]),
                        "seen_bad_ant_hits": int(eval_result["seen_bad_ant_hits"]),
                        "heldout_bad_ant_hits": int(eval_result["heldout_bad_ant_hits"]),
                        "seen_good_fail_hits": int(eval_result["seen_good_fail_hits"]),
                        "seen_bad_fail_hits": int(eval_result["seen_bad_fail_hits"]),
                        "heldout_good_fail_hits": int(eval_result["heldout_good_fail_hits"]),
                        "heldout_bad_fail_hits": int(eval_result["heldout_bad_fail_hits"]),
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
