from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import time
import random
from pathlib import Path
from typing import Any

from run_multi_model_small_eval import (
    MODEL_SPECS,
    aggregate_and_write_outputs,
    build_case_bundles,
    classify_failure,
    collect_candidates,
    collect_candidates_with_metrics,
    heuristic_semantic_reason,
    literal_hardcoding_flag,
    make_generation_prompt,
    probe_property_support,
    resolve_selected_case_ids,
    run_case_eval,
    str_to_bool,
    write_text,
)
from trace_representation_contract import (
    case_contract_inputs,
    validate_temporal_relation_abstraction,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_ROOT = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "scale120_trace_representation_ablation_data"
DEFAULT_TEMPORAL_SUMMARY_JSON = (
    ROOT
    / "outputs"
    / "scale120_abstracted_summary_inputs"
    / "scale120_abstracted_summaries_combined.json"
)

METHOD_SPECS: list[dict[str, str]] = [
    {
        "method": "spec_rtl_raw_trace",
        "trace_input_label": "Raw trace",
        "representation_label": "raw_trace",
    },
    {
        "method": "spec_rtl_naive_summary",
        "trace_input_label": "Naive summary",
        "representation_label": "naive_summary",
    },
    {
        "method": "spec_rtl_event_abstraction",
        "trace_input_label": "Event abstraction",
        "representation_label": "event_abstraction",
    },
    {
        "method": "spec_rtl_temporal_relation_abstraction",
        "trace_input_label": "Temporal-relation abstraction",
        "representation_label": "temporal_relation_abstraction",
    },
    {"method": "spec_rtl_trace_good_only", "trace_input_label": "Good trace only", "representation_label": "good_only"},
    {"method": "spec_rtl_trace_bad_only", "trace_input_label": "Bad trace only", "representation_label": "bad_only"},
    {"method": "spec_rtl_trace_local_window", "trace_input_label": "Local good/bad trace window", "representation_label": "local_window"},
    {"method": "spec_rtl_trace_signal_subset", "trace_input_label": "Trigger/divergence signal subset", "representation_label": "signal_subset"},
    {"method": "spec_rtl_trace_noise_signals", "trace_input_label": "Good/bad trace with distractor signals", "representation_label": "noise_signals"},
    {"method": "spec_rtl_trace_format_perturbed", "trace_input_label": "Format-perturbed good/bad trace", "representation_label": "format_perturbed"},
    {"method": "spec_rtl_trace_wrong_pairing", "trace_input_label": "Misaligned good/bad trace pairing", "representation_label": "wrong_pairing"},
    {"method": "spec_rtl_temporal_no_trigger", "trace_input_label": "Temporal abstraction without trigger", "representation_label": "temporal_no_trigger"},
    {"method": "spec_rtl_temporal_no_delay", "trace_input_label": "Temporal abstraction without delay", "representation_label": "temporal_no_delay"},
    {"method": "spec_rtl_temporal_no_polarity", "trace_input_label": "Temporal abstraction without polarity", "representation_label": "temporal_no_polarity"},
    {"method": "spec_rtl_temporal_no_duration", "trace_input_label": "Temporal abstraction without duration", "representation_label": "temporal_no_duration"},
    {"method": "spec_rtl_temporal_strict_no_trigger", "trace_input_label": "Temporal abstraction with all trigger references removed", "representation_label": "temporal_strict_no_trigger"},
    {"method": "spec_rtl_temporal_strict_no_delay", "trace_input_label": "Temporal abstraction with all delay references removed", "representation_label": "temporal_strict_no_delay"},
    {"method": "spec_rtl_temporal_strict_no_polarity", "trace_input_label": "Temporal abstraction with all polarity references removed", "representation_label": "temporal_strict_no_polarity"},
    {"method": "spec_rtl_temporal_strict_no_duration", "trace_input_label": "Temporal abstraction with all duration references removed", "representation_label": "temporal_strict_no_duration"},
]

METHOD_LABELS = {item["method"]: item["trace_input_label"] for item in METHOD_SPECS}


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def load_temporal_summary_lookup(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists():
        raise FileNotFoundError(f"Temporal summary json not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list in temporal summary json: {path}")

    out: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        summary = str(item.get("abstracted_summary", "")).strip()
        if case_id and summary:
            out[case_id] = summary
    return out


def load_manifest_lookup(cases_root: Path) -> dict[str, dict[str, Any]]:
    manifest_path = cases_root / "case_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    return {
        str(item["name"]): dict(item)
        for item in cases
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }


def parse_trace_summary_text(trace_summary_text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in str(trace_summary_text or "").splitlines():
        line = raw_line.strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        parsed[key.strip().lower()] = value.strip()
    return parsed


def classify_signal_role(signal_name: str) -> str:
    base = str(signal_name).split("[", 1)[0].strip().lower()
    if base.startswith(("err", "error", "alert", "fault", "fail")):
        return "error/status output"
    if base.endswith(("_o", "_q", "_d")) or base.startswith(("intr", "valid", "ready", "full", "empty", "depth")):
        return "observed output/state"
    return "observed signal"


def compact_signal_list(signals_text: str) -> str:
    items = [item.strip() for item in str(signals_text or "").split(",") if item.strip()]
    if not items:
        return "the observed outputs"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def split_raw_trace(raw: str) -> tuple[list[str], list[str]]:
    marker = "\n\nBad trace (posedge cycles):\n"
    if marker not in raw:
        raise ValueError("Raw trace is missing the good/bad separator")
    good_text, bad_text = raw.split(marker, 1)
    good_text = good_text.removeprefix("Good trace (posedge cycles):\n")
    return good_text.splitlines(), bad_text.splitlines()


def cycle_number(line: str) -> int | None:
    match = re.match(r"\s*cycle\s+(\d+)\s*:", line)
    return int(match.group(1)) if match else None


def first_divergence_cycle(bundle: dict[str, Any]) -> int | None:
    text = str(bundle.get("normal_trace_summary", ""))
    match = re.search(r"first divergence(?: cycle| at cycle|:)\s*(\d+)", text, re.I)
    if match:
        return int(match.group(1))
    temporal = str(bundle.get("abstracted_trace_summary", ""))
    match = re.search(r"first good/bad divergence.*?cycle\s+(\d+)", temporal, re.I)
    return int(match.group(1)) if match else None


def render_pair(good: list[str], bad: list[str], good_label: str = "Good trace", bad_label: str = "Bad trace") -> str:
    return f"{good_label} (posedge cycles):\n" + "\n".join(good) + f"\n\n{bad_label} (posedge cycles):\n" + "\n".join(bad)


def temporal_without(summary: str, field: str) -> str:
    prefix = f"- {field.lower()}:"
    kept = [line for line in summary.splitlines() if not line.strip().lower().startswith(prefix)]
    kept.append(f"- Ablation notice: the {field.lower()} relation was intentionally removed; do not reconstruct it from hidden information.")
    return "\n".join(kept).strip()


def temporal_strict_without(summary: str, field: str) -> str:
    keyword = field.lower().replace("observed ", "")
    aliases = {
        "trigger": ("trigger", "ordering"),
        "delay": ("delay",),
        "polarity": ("polarity",),
        "duration": ("duration", "holds", "consecutive"),
    }[keyword]
    kept = [
        line for line in summary.splitlines()
        if not any(alias in line.lower() for alias in aliases)
        and not line.strip().lower().startswith("- generalization boundary:")
    ]
    kept.append("- Generalization boundary: infer only from the relations explicitly retained above.")
    kept.append(f"- Strict ablation notice: every explicit reference to {keyword} information was removed.")
    return "\n".join(kept).strip()


def signal_subset_names(bundle: dict[str, Any]) -> set[str]:
    allowed = {str(sig).split("[", 1)[0].strip() for sig in bundle["allowed_signals"]}
    evidence = str(bundle.get("normal_trace_summary", "")) + "\n" + str(bundle.get("abstracted_trace_summary", ""))
    selected = {sig for sig in allowed if re.search(rf"\b{re.escape(sig)}\b", evidence)}
    selected |= {sig for sig in allowed if sig.lower().startswith(("clk", "rst"))}
    return selected or allowed


def filter_trace_signals(lines: list[str], selected: set[str]) -> list[str]:
    out = []
    for line in lines:
        if ":" not in line:
            continue
        head, payload = line.split(":", 1)
        fields = []
        for item in payload.split(","):
            name = item.split("=", 1)[0].strip().split("[", 1)[0]
            if name in selected:
                fields.append(item.strip())
        out.append(head.strip() + ": " + ", ".join(fields))
    return out


def add_noise(case_id: str, lines: list[str], width: int = 8) -> list[str]:
    out = []
    for line in lines:
        cyc = cycle_number(line) or 0
        rng = random.Random(f"mechanism-v1|{case_id}|{cyc}")
        noise = ", ".join(f"distractor_{idx}={rng.randint(0, 1)}" for idx in range(width))
        out.append(line + (", " if line else "") + noise)
    return out


def perturb_format(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        cyc = cycle_number(line)
        payload = line.split(":", 1)[1] if ":" in line else line
        fields = [item.strip() for item in payload.split(",") if item.strip()]
        out.append(f"sample[{cyc}] {{ " + "; ".join(reversed(fields)) + " }")
    return out


def build_event_abstraction(
    *,
    bundle: dict[str, Any],
    case_meta: dict[str, Any],
) -> str:
    trace_summary = parse_trace_summary_text(bundle.get("normal_trace_summary", ""))
    trace_summary_json = bundle.get("trace_summary_json") or {}
    differing_signals = trace_summary.get("differing signals at first divergence", "")
    bug_class = str(case_meta.get("bug_class", "")).strip()
    first_signal = ""
    if differing_signals:
        first_signal = differing_signals.split(",", 1)[0].strip()
    elif trace_summary_json.get("differing_signals"):
        first_signal = str(trace_summary_json["differing_signals"][0]).strip()
    signal_role = classify_signal_role(first_signal) if first_signal else "observed signal"

    bullets = [
        "- Focus on the first bug-revealing event rather than the exact sampled cycle number or a memorized waveform prefix.",
        (
            f"- The first good/bad mismatch shows up on {compact_signal_list(differing_signals)}; "
            f"treat this as the key {signal_role} difference to explain."
            if differing_signals
            else "- The first good/bad mismatch is the key observed event to explain."
        ),
        "- Contrast the good and buggy outcomes at the event level instead of replaying exact signal literals from the witnessed trace.",
    ]

    if bug_class == "temporal_cross_cycle":
        bullets.append(
            "- Describe the trigger and resulting observation as a compact event pair, but avoid spelling out an explicit multi-cycle rule or exact delay."
        )
    else:
        bullets.append(
            "- Describe the trigger and observed outcome in the same local event context; avoid hard-coding literal cycle positions."
        )

    summary_lines = ["Event abstraction:"] + bullets
    return "\n".join(summary_lines).strip()


def build_trace_payloads(bundle: dict[str, Any], case_meta: dict[str, Any]) -> dict[str, str]:
    temporal_summary = str(bundle.get("abstracted_trace_summary", "") or "").strip()
    if not temporal_summary:
        raise RuntimeError(f"Missing temporal abstracted summary for {bundle['case_id']}")
    raw = str(bundle["raw_trace_input"]).strip()
    good, bad = split_raw_trace(raw)
    div_cycle = first_divergence_cycle(bundle)
    if div_cycle is None:
        div_cycle = cycle_number(good[len(good) // 2]) or 0
    window_good = [line for line in good if (cycle_number(line) is not None and div_cycle - 3 <= int(cycle_number(line)) <= div_cycle + 3)]
    window_bad = [line for line in bad if (cycle_number(line) is not None and div_cycle - 3 <= int(cycle_number(line)) <= div_cycle + 3)]
    selected = signal_subset_names(bundle)
    wrong_bad = bad[1:] + bad[:1]
    return {
        "spec_rtl_raw_trace": str(bundle["raw_trace_input"]).strip(),
        "spec_rtl_naive_summary": (
            "Naive trace summary:\n"
            + str(bundle["normal_trace_summary"]).strip()
            + "\n\nNaive-summary reminder:\n"
            + "- This summary may contain exact divergence-cycle/value evidence; avoid overfitting to it."
        ),
        "spec_rtl_event_abstraction": build_event_abstraction(bundle=bundle, case_meta=case_meta),
        "spec_rtl_temporal_relation_abstraction": temporal_summary,
        "spec_rtl_trace_good_only": "Good trace only (posedge cycles):\n" + "\n".join(good),
        "spec_rtl_trace_bad_only": "Bad trace only (posedge cycles):\n" + "\n".join(bad),
        "spec_rtl_trace_local_window": render_pair(window_good, window_bad, "Good local window", "Bad local window"),
        "spec_rtl_trace_signal_subset": render_pair(filter_trace_signals(good, selected), filter_trace_signals(bad, selected), "Good signal-subset trace", "Bad signal-subset trace"),
        "spec_rtl_trace_noise_signals": render_pair(add_noise(str(bundle["case_id"]), good), add_noise(str(bundle["case_id"]) + "|bad", bad), "Good trace with distractors", "Bad trace with distractors"),
        "spec_rtl_trace_format_perturbed": render_pair(perturb_format(good), perturb_format(bad), "Good trace reformatted", "Bad trace reformatted"),
        "spec_rtl_trace_wrong_pairing": render_pair(good, wrong_bad, "Good trace", "Bad trace shifted by one sample"),
        "spec_rtl_temporal_no_trigger": temporal_without(temporal_summary, "Trigger"),
        "spec_rtl_temporal_no_delay": temporal_without(temporal_summary, "Observed delay"),
        "spec_rtl_temporal_no_polarity": temporal_without(temporal_summary, "Polarity"),
        "spec_rtl_temporal_no_duration": temporal_without(temporal_summary, "Duration"),
        "spec_rtl_temporal_strict_no_trigger": temporal_strict_without(temporal_summary, "Trigger"),
        "spec_rtl_temporal_strict_no_delay": temporal_strict_without(temporal_summary, "Observed delay"),
        "spec_rtl_temporal_strict_no_polarity": temporal_strict_without(temporal_summary, "Polarity"),
        "spec_rtl_temporal_strict_no_duration": temporal_strict_without(temporal_summary, "Duration"),
    }


def make_method_prompt(bundle: dict[str, Any], method: str, target_count: int) -> tuple[str, str]:
    trace_payloads = bundle["trace_payloads"]
    if method not in trace_payloads:
        raise ValueError(f"Unsupported method: {method}")
    trace_text = trace_payloads[method]
    prompt = make_generation_prompt(
        allowed_signals=bundle["allowed_signals"],
        spec=bundle["spec"],
        rtl_text=str(bundle["rtl_text"]).strip(),
        trace_section=trace_text,
        additional_guidance=str(bundle.get("additional_guidance", "") or ""),
        target_count=target_count,
    )
    return prompt, trace_text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run scale120 trace-representation ablation. "
            "Compares raw traces, naive summaries, event abstractions, and temporal-relation abstractions."
        )
    )
    parser.add_argument(
        "--root",
        default=os.environ.get("TRACE_REPR_ABLATION_CASES_ROOT", str(DEFAULT_CASES_ROOT)),
        help="Dataset root containing case directories and case_manifest.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("TRACE_REPR_ABLATION_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)),
        help="Directory to store prompts, raw results, summaries, and per-model shards.",
    )
    parser.add_argument(
        "--temporal-summary-json",
        default=os.environ.get("TRACE_REPR_ABLATION_TEMPORAL_SUMMARY_JSON", str(DEFAULT_TEMPORAL_SUMMARY_JSON)),
        help="Combined abstracted-summary json used as the temporal-relation abstraction arm.",
    )
    parser.add_argument("--case", action="append", default=[], help="Case id to include. Repeat to select multiple.")
    parser.add_argument(
        "--all-cases",
        action="store_true",
        default=str_to_bool(os.environ.get("TRACE_REPR_ABLATION_ALL_CASES", "")),
        help="Select every case from case_manifest.json under --root.",
    )
    parser.add_argument(
        "--max-cases",
        type=int,
        default=int(os.environ.get("TRACE_REPR_ABLATION_MAX_CASES", "0") or "0"),
        help="Optional cap after case selection/sharding. 0 means no cap.",
    )
    parser.add_argument(
        "--shard-index",
        type=int,
        default=int(os.environ.get("TRACE_REPR_ABLATION_SHARD_INDEX", "0") or "0"),
        help="0-based shard index for splitting a large case list.",
    )
    parser.add_argument(
        "--shard-count",
        type=int,
        default=int(os.environ.get("TRACE_REPR_ABLATION_SHARD_COUNT", "1") or "1"),
        help="Number of shards for splitting a large case list.",
    )
    parser.add_argument("--model", action="append", default=[], help="Model label to include. Repeat to select multiple.")
    parser.add_argument(
        "--method",
        action="append",
        default=[],
        help=(
            "Method to include. Supported: spec_rtl_raw_trace, spec_rtl_naive_summary, "
            "spec_rtl_event_abstraction, spec_rtl_temporal_relation_abstraction."
        ),
    )
    parser.add_argument(
        "--candidates-per-cell",
        type=int,
        default=int(os.environ.get("TRACE_REPR_ABLATION_CANDIDATES_PER_CELL", "2") or "2"),
        help="How many distinct candidate assertions to request for each model/case/method cell.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=str_to_bool(os.environ.get("TRACE_REPR_ABLATION_DRY_RUN", "")),
        help="Prepare prompts and metadata only; skip model calls and WSL evaluation.",
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Call models and persist pending candidates, but skip WSL evaluation.",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        default=str_to_bool(os.environ.get("TRACE_REPR_ABLATION_RESUME", "")),
        help="Skip only cells that already contain every requested evaluated candidate index.",
    )
    parser.add_argument("--candidate-index-offset", type=int, default=0, help="Store generated candidates at offset+1..offset+k.")
    parser.add_argument("--exclude-candidates-results", default="", help="Existing result CSV whose same-cell assertions must not be repeated.")
    return parser.parse_args()


def load_complete_cells(output_dir: Path, candidates_per_cell: int, candidate_index_offset: int = 0) -> set[tuple[str, str, str, str, str]]:
    path = output_dir / "multi_model_results_raw.csv"
    if not path.exists():
        return set()
    found: dict[tuple[str, str, str, str, str], set[int]] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (
                str(row.get("model_label", "")), str(row.get("provider", "")),
                str(row.get("model_name", "")), str(row.get("case_id", "")),
                str(row.get("method", "")),
            )
            try:
                index = int(float(str(row.get("candidate_index", ""))))
            except ValueError:
                continue
            found.setdefault(key, set()).add(index)
    required = set(range(candidate_index_offset + 1, candidate_index_offset + candidates_per_cell + 1))
    return {key for key, indices in found.items() if required.issubset(indices)}


def load_cached_candidates(output_dir: Path, model_label: str, case_id: str, method: str) -> list[dict[str, str]]:
    path = output_dir / "pending_candidates.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row["model_label"] == model_label and row["case_id"] == case_id and row["method"] == method
        ]
    rows.sort(key=lambda row: int(row["candidate_index"]))
    return rows


def cache_candidates(
    output_dir: Path, model_spec: dict[str, Any], bundle: dict[str, Any], method_spec: dict[str, str],
    candidates: list[str], candidate_index_offset: int = 0,
) -> None:
    path = output_dir / "pending_candidates.csv"
    existing: list[dict[str, Any]] = []
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as handle:
            existing = list(csv.DictReader(handle))
    by_key = {
        (row["model_label"], row["case_id"], row["method"], str(row["candidate_index"])): row
        for row in existing
    }
    for index, assertion_text in enumerate(candidates, start=candidate_index_offset + 1):
        row = {
            "model_label": model_spec["model_label"], "provider": model_spec["provider"],
            "model_name": model_spec["model_name"], "case_id": bundle["case_id"],
            "method": method_spec["method"], "trace_input_label": method_spec["trace_input_label"],
            "representation_label": method_spec["representation_label"], "candidate_index": index,
            "assertion_text": assertion_text, "selection_tags": bundle["selection_tags"],
            "selection_reason": bundle["selection_reason"], "evaluation_status": "pending",
        }
        by_key[(str(model_spec["model_label"]), str(bundle["case_id"]), str(method_spec["method"]), str(index))] = row
    rows = list(by_key.values())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()

    cases_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    temporal_summary_json = Path(args.temporal_summary_json).resolve()
    temporal_summary_sha256 = hashlib.sha256(temporal_summary_json.read_bytes()).hexdigest()
    output_dir.mkdir(parents=True, exist_ok=True)

    env_model_filter = {
        item.strip()
        for item in os.environ.get("TRACE_REPR_ABLATION_MODEL_FILTER", "").split(",")
        if item.strip()
    }
    env_method_filter = {
        item.strip()
        for item in os.environ.get("TRACE_REPR_ABLATION_METHOD_FILTER", "").split(",")
        if item.strip()
    }
    env_case_filter = {
        item.strip()
        for item in os.environ.get("TRACE_REPR_ABLATION_CASE_FILTER", "").split(",")
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
    temporal_summary_lookup = load_temporal_summary_lookup(temporal_summary_json)
    manifest_lookup = load_manifest_lookup(cases_root)

    bundles = build_case_bundles(
        cases_root=cases_root,
        case_ids=selected_case_ids,
        abstracted_summary_lookup=temporal_summary_lookup,
    )
    for bundle in bundles:
        case_dir = cases_root / bundle["case_id"] / "experiment"
        trace_summary_json_path = case_dir / "trace_summary.json"
        trace_summary_json = {}
        if trace_summary_json_path.exists():
            trace_summary_json = json.loads(trace_summary_json_path.read_text(encoding="utf-8"))
        bundle["trace_summary_json"] = trace_summary_json
        case_meta = manifest_lookup.get(bundle["case_id"], {})
        temporal_errors = validate_temporal_relation_abstraction(
            str(bundle.get("abstracted_trace_summary", "")),
            **case_contract_inputs(cases_root / bundle["case_id"], case_meta),
        )
        if temporal_errors:
            raise RuntimeError(
                f"Temporal abstraction contract failed for {bundle['case_id']}: {temporal_errors}. "
                "Regenerate the temporal-relation abstraction before running the ablation."
            )
        bundle["trace_payloads"] = build_trace_payloads(
            bundle,
            case_meta,
        )

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
                "representation_label": next(
                    item["representation_label"]
                    for item in METHOD_SPECS
                    if item["method"] == method_name
                ),
            }
            for method_name in requested_methods
        ]
    else:
        method_specs = [dict(item) for item in METHOD_SPECS]

    if not bundles:
        raise RuntimeError("No cases selected for trace representation ablation.")
    if not model_specs:
        raise RuntimeError("No models selected for trace representation ablation.")
    if not method_specs:
        raise RuntimeError("No methods selected for trace representation ablation.")

    use_property = False
    if not args.dry_run and not args.generate_only:
        use_property = probe_property_support(
            bundles[0]["case_id"],
            cases_root=cases_root,
            runtime_dir=output_dir / "_probe",
        )

    all_results: list[dict[str, Any]] = []
    prompt_rows: list[dict[str, Any]] = []
    complete_cells = load_complete_cells(output_dir, args.candidates_per_cell, args.candidate_index_offset) if args.resume else set()
    excluded: dict[tuple[str, str, str], list[str]] = {}
    if args.exclude_candidates_results:
        with Path(args.exclude_candidates_results).resolve().open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                key = (str(row.get("model_label", "")), str(row.get("case_id", "")), str(row.get("method", "")))
                assertion = str(row.get("assertion_text", "")).strip()
                if assertion:
                    excluded.setdefault(key, []).append(assertion)

    for model_spec in model_specs:
        for bundle in bundles:
            for method_spec in method_specs:
                method = method_spec["method"]
                print(
                    f"[INFO] {model_spec['model_label']} | {bundle['case_id']} | {method}",
                    file=sys.stderr,
                )
                prompt_text, trace_representation_text = make_method_prompt(
                    bundle,
                    method,
                    args.candidates_per_cell,
                )
                prior_assertions = excluded.get((str(model_spec["model_label"]), str(bundle["case_id"]), str(method)), [])
                if prior_assertions:
                    prompt_text += (
                        "\n\nPortfolio continuation constraint:\n"
                        "The following candidates already occupy earlier portfolio slots. Do not repeat or trivially rephrase them:\n- "
                        + "\n- ".join(prior_assertions)
                    )
                prompt_dir = output_dir / "prompts" / model_spec["model_label"] / bundle["case_id"]
                prompt_path = prompt_dir / f"{method}.txt"
                write_text(prompt_path, prompt_text + "\n")

                cell_key = (
                    str(model_spec["model_label"]), str(model_spec["provider"]),
                    str(model_spec["model_name"]), str(bundle["case_id"]), str(method),
                )
                if cell_key in complete_cells:
                    print(f"[SKIP complete] {model_spec['model_label']} | {bundle['case_id']} | {method}", file=sys.stderr)
                    continue

                method_prompt_rows: list[dict[str, Any]] = []
                method_result_rows: list[dict[str, Any]] = []
                candidates: list[str] = []
                raw_responses: list[str] = []
                generation_metrics: list[dict[str, Any]] = []
                if not args.dry_run:
                    reused_pending = load_cached_candidates(
                        output_dir, model_spec["model_label"], bundle["case_id"], method
                    )
                    if len(reused_pending) >= args.candidates_per_cell:
                        candidates = [row["assertion_text"] for row in reused_pending[: args.candidates_per_cell]]
                        print(f"[INFO] reuse {len(candidates)} pending candidates", file=sys.stderr)
                    else:
                        candidates, raw_responses, generation_metrics = collect_candidates_with_metrics(
                            model_spec=model_spec,
                            prompt=prompt_text,
                            target_count=args.candidates_per_cell,
                        )
                        # Persist immediately, before compilation/elaboration, so a harness
                        # failure cannot discard already-paid model generations.
                        cache_candidates(output_dir, model_spec, bundle, method_spec, candidates, args.candidate_index_offset)

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
                        "representation_label": method_spec["representation_label"],
                        "prompt_path": str(prompt_path.resolve()),
                        "prompt_text": prompt_text,
                        "trace_representation_text": trace_representation_text,
                        "trace_representation_char_count": len(trace_representation_text),
                        "trace_representation_line_count": (
                            len(trace_representation_text.splitlines()) if trace_representation_text else 0
                        ),
                        "temporal_summary_source_path": str(temporal_summary_json),
                        "temporal_summary_source_sha256": temporal_summary_sha256,
                        "temporal_contract_status": "formal_compliant",
                        "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
                        "generation_call_metrics_json": json.dumps(generation_metrics, ensure_ascii=False),
                        "generation_time_sec": sum(float(x.get("duration_sec") or 0.0) for x in generation_metrics),
                        "prompt_tokens_actual": sum(int(x.get("prompt_tokens") or 0) for x in generation_metrics),
                        "output_tokens_actual": sum(int(x.get("output_tokens") or 0) for x in generation_metrics),
                        "total_tokens_actual": sum(int(x.get("total_tokens") or 0) for x in generation_metrics),
                        "usage_call_count": sum(bool(x.get("usage_available")) for x in generation_metrics),
                        "api_call_count": len(generation_metrics),
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

                if args.generate_only:
                    pending_path = output_dir / "pending_candidates.csv"
                    existing = []
                    if pending_path.exists():
                        with pending_path.open(encoding="utf-8-sig", newline="") as handle:
                            existing = list(csv.DictReader(handle))
                    pending_by_key = {
                        (row["model_label"], row["case_id"], row["method"], str(row["candidate_index"])): row
                        for row in existing
                    }
                    for candidate_index, assertion_text in enumerate(candidates, start=args.candidate_index_offset + 1):
                        pending_row = {
                            "model_label": model_spec["model_label"], "provider": model_spec["provider"],
                            "model_name": model_spec["model_name"], "case_id": bundle["case_id"],
                            "method": method, "trace_input_label": method_spec["trace_input_label"],
                            "representation_label": method_spec["representation_label"],
                            "candidate_index": candidate_index, "assertion_text": assertion_text,
                            "selection_tags": bundle["selection_tags"], "selection_reason": bundle["selection_reason"],
                            "evaluation_status": "pending",
                        }
                        pending_by_key[(model_spec["model_label"], bundle["case_id"], method, str(candidate_index))] = pending_row
                    pending_rows = list(pending_by_key.values())
                    with pending_path.open("w", encoding="utf-8-sig", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=list(pending_rows[0]))
                        writer.writeheader(); writer.writerows(pending_rows)
                    aggregate_and_write_outputs(
                        result_rows=[], prompt_rows=method_prompt_rows, model_specs=model_specs,
                        method_specs=method_specs, candidates_per_cell=args.candidates_per_cell,
                        use_property=False, output_dir=output_dir, selected_case_ids=selected_case_ids,
                    )
                    continue

                for candidate_index, assertion_text in enumerate(candidates, start=args.candidate_index_offset + 1):
                    runtime_dir = (
                        output_dir
                        / "runtime"
                        / model_spec["model_label"]
                        / bundle["case_id"]
                        / method
                        / f"cand_{candidate_index:02d}"
                    )
                    validation_started = time.perf_counter()
                    try:
                        eval_result = run_case_eval(
                            case_id=bundle["case_id"],
                            assertion_text=assertion_text,
                            signal_names=bundle["allowed_signals"],
                            use_property=use_property,
                            runtime_dir=runtime_dir,
                            cases_root=cases_root,
                        )
                    except ValueError as exc:
                        # A malformed model candidate is an ordinary compile
                        # failure, not a reason to abort the full experiment.
                        eval_result = {
                            "compile_ok": False, "correct_pass": False,
                            "buggy_fail": False, "antecedent_hit": False,
                            "non_vacuous": False, "heldout_correct_pass": False,
                            "heldout_buggy_fail": False, "heldout_antecedent_hit": False,
                            "heldout_non_vacuous": False, "trace_overfit": False,
                            "seen_good_ant_hits": 0, "seen_bad_ant_hits": 0,
                            "heldout_bad_ant_hits": 0, "seen_good_fail_hits": 0,
                            "seen_bad_fail_hits": 0, "heldout_good_fail_hits": 0,
                            "heldout_bad_fail_hits": 0,
                            "parse_error": str(exc),
                        }
                    validation_time_sec = time.perf_counter() - validation_started
                    semantic_reasonable, semantic_reason = heuristic_semantic_reason(assertion_text)
                    row = {
                        "model_label": model_spec["model_label"],
                        "provider": model_spec["provider"],
                        "model_name": model_spec["model_name"],
                        "validation_time_sec": validation_time_sec,
                        "case_id": bundle["case_id"],
                        "selection_tags": bundle["selection_tags"],
                        "selection_reason": bundle["selection_reason"],
                        "method": method,
                        "trace_input_label": method_spec["trace_input_label"],
                        "representation_label": method_spec["representation_label"],
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
                        "use_property_compile_mode": use_property,
                    }
                    failure_mode, failure_reason = classify_failure(row)
                    row["failure_mode"] = failure_mode
                    row["failure_reason"] = failure_reason
                    method_result_rows.append(row)
                    all_results.append(row)

                aggregate_and_write_outputs(
                    result_rows=method_result_rows,
                    prompt_rows=prompt_rows,
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
    print((output_dir / "multi_model_results_raw.csv").resolve())
    print((output_dir / "multi_model_summary.csv").resolve())


if __name__ == "__main__":
    main()
