from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import textwrap
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from run_multi_model_small_eval import (  # noqa: E402
    MODEL_SPECS,
    load_abstracted_summary_lookup,
    post_model_chat,
    read_text,
    resolve_selected_case_ids,
    sanitize_abstracted_summary,
)
from run_trace_abstraction_prototype import SELECTED_CASES as LEGACY_EXAMPLES  # noqa: E402
from trace_representation_contract import (  # noqa: E402
    case_contract_inputs,
    validate_temporal_relation_abstraction,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES_ROOT = ROOT / "rtl_cases_real_scale120"
DEFAULT_OUTPUT_DIR = ROOT / "outputs" / "scale120_abstracted_summary_inputs"


def strip_fences(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = cleaned.replace("```json", "").replace("```text", "").replace("```", "").strip()
    return cleaned


def extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = strip_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        payload = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def coerce_abstracted_summary(raw_response: str) -> str:
    payload = extract_json_object(raw_response)
    if payload and str(payload.get("abstracted_summary", "")).strip():
        summary = str(payload["abstracted_summary"])
    else:
        summary = strip_fences(raw_response)
    summary = summary.strip()
    if not summary:
        raise RuntimeError("Model returned an empty abstracted summary.")
    if not summary.lower().startswith("temporal-relation abstraction:"):
        summary = "Temporal-relation abstraction:\n" + summary
    summary = sanitize_abstracted_summary(summary)
    if not summary:
        raise RuntimeError("Abstracted summary became empty after sanitization.")
    return summary


def load_model_spec(model_label: str) -> dict[str, Any]:
    for spec in MODEL_SPECS:
        if str(spec["model_label"]) == model_label:
            return spec
    raise ValueError(f"Unknown --summary-model: {model_label}")


def build_examples_block() -> str:
    exemplar_ids = {
        "case101_prim_onehot_multihot_suppressed",
        "case104_prim_fifo_full_early",
    }
    blocks: list[str] = []
    for item in LEGACY_EXAMPLES:
        if item["case_id"] not in exemplar_ids:
            continue
        blocks.append(
            textwrap.dedent(
                f"""
                Example case: {item['case_id']}
                Specification:
                {str(item.get('spec', '')).strip()}

                Normal trace summary:
                {str(item.get('normal_trace_summary', '')).strip()}

                Raw trace input:
                {str(item.get('raw_trace_input', '')).strip()}

                Good output:
                {str(item.get('abstracted_summary', '')).strip()}
                """
            ).strip()
        )
    return "\n\n".join(blocks)


def build_prompt(
    *,
    case_id: str,
    spec: str,
    trace_summary: str,
    raw_trace_input: str,
) -> str:
    return textwrap.dedent(
        f"""
        You are writing the "Temporal-relation abstraction" input for an SVA-generation benchmark.

        Task:
        Convert the specification plus paired good/bad waveform traces into a concise abstraction that keeps the bug-relevant relation while removing one-off literals and incidental setup.

        Output rules:
        1) Return JSON only: {{"abstracted_summary":"..."}}
        2) The value must start with the exact line: Temporal-relation abstraction:
        3) Then write exactly these 8 labeled bullets: Trigger, Polarity, Ordering,
           Observed delay, Duration, Reset, Good/bad divergence, Generalization boundary.
        4) Trigger identifies the observed initiating event or condition without stating the golden property.
        5) Polarity preserves rise/fall, asserted/deasserted, high/low, or explicitly says unknown.
        6) Ordering preserves before/same-cycle/after. Observed delay reports the exact delay measured
           in this trace, explicitly scoped as observed evidence; use unknown if it cannot be measured.
        7) Duration records how long the trigger/response persists, or explicitly says unknown/not observable.
        8) Reset records reset polarity and its relationship to the event, or explicitly says not observed.
        9) Good/bad divergence names the first observed difference and both observed outcomes.
        10) Generalization boundary must say not to infer a universal rule from absolute cycle indices
            or one-off literal constants in this trace.
        11) Never include golden SVA, expected-property text, mutation diff, buggy source line, or mutation line.
        12) Do not convert the current trace's fixed cycle number or literal constant into a general rule.
        13) Keep original signal names only when present in the supplied spec/traces.
        14) Do not mention this instruction block.

        Now write the abstracted trace summary for this case.

        Case: {case_id}

        Specification:
        {spec}

        Normal trace summary:
        {trace_summary}

        Raw good/bad traces:
        {raw_trace_input}
        """
    ).strip()


def shard_file_name(shard_index: int, shard_count: int) -> str:
    return f"scale120_abstracted_summaries.shard{shard_index:02d}-of-{shard_count:02d}.json"


def shard_prompt_log_name(shard_index: int, shard_count: int) -> str:
    return f"scale120_abstracted_summaries_prompt_log.shard{shard_index:02d}-of-{shard_count:02d}.csv"


def existing_entry_map(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("case_id", "")).strip()
        if case_id:
            out[case_id] = dict(item)
    return out


def write_json_list(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def write_prompt_log(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate fixed abstracted summaries for scale120 case shards so the abstracted method can be backfilled into the full eval."
    )
    parser.add_argument("--root", default=str(DEFAULT_CASES_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--all-cases", action="store_true", default=True)
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--summary-model", default=os.environ.get("ABSTRACTED_SUMMARY_MODEL_LABEL", "GPT"))
    parser.add_argument("--temperature", type=float, default=float(os.environ.get("ABSTRACTED_SUMMARY_TEMPERATURE", "0.2")))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases_root = Path(args.root).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_case_ids = resolve_selected_case_ids(
        cases_root=cases_root,
        requested_case_ids=[item.strip() for item in args.case if item.strip()],
        all_cases=bool(args.all_cases),
        max_cases=int(args.max_cases),
        shard_index=int(args.shard_index),
        shard_count=int(args.shard_count),
    )
    model_spec = load_model_spec(str(args.summary_model))

    shard_json = output_dir / shard_file_name(int(args.shard_index), int(args.shard_count))
    shard_log_csv = output_dir / shard_prompt_log_name(int(args.shard_index), int(args.shard_count))
    prompt_dir = output_dir / "prompts"
    response_dir = output_dir / "responses"

    existing_rows = existing_entry_map(shard_json)
    prompt_log_rows: list[dict[str, Any]] = []
    manifest = json.loads((cases_root / "case_manifest.json").read_text(encoding="utf-8"))
    manifest_lookup = {item["name"]: item for item in manifest.get("cases", [])}

    legacy_lookup = load_abstracted_summary_lookup(None)
    for case_id in selected_case_ids:
        existing_entry = existing_rows.get(case_id, {})
        existing_source = str(existing_entry.get("source", "")).strip()
        case_meta = manifest_lookup.get(case_id, {})
        contract_inputs = case_contract_inputs(cases_root / case_id, case_meta)
        existing_errors = validate_temporal_relation_abstraction(
            str(existing_entry.get("abstracted_summary", "")), **contract_inputs
        )
        if (
            case_id in existing_rows
            and existing_source != "dry_run_placeholder"
            and str(existing_rows[case_id].get("abstracted_summary", "")).strip()
            and not existing_errors
        ):
            prompt_log_rows.append(
                {
                    "case_id": case_id,
                    "status": "reused_existing_shard_entry",
                    "summary_model": str(existing_rows[case_id].get("summary_model_label", "")),
                    "prompt_path": str((prompt_dir / f"{case_id}.txt").resolve()),
                    "response_path": str((response_dir / f"{case_id}.txt").resolve()),
                }
            )
            continue

        case_dir = cases_root / case_id / "experiment"
        spec = read_text(case_dir / "spec.txt").strip()
        trace_summary = read_text(case_dir / "trace_summary.txt").strip()
        raw_trace_input = (
            "Good trace (posedge cycles):\n"
            + read_text(case_dir / "trace_good.txt").strip()
            + "\n\nBad trace (posedge cycles):\n"
            + read_text(case_dir / "trace_bad.txt").strip()
        )

        legacy_summary = str(legacy_lookup.get(case_id, "")).strip()
        if legacy_summary and not validate_temporal_relation_abstraction(legacy_summary, **contract_inputs):
            summary_text = legacy_summary
            raw_response = json.dumps({"abstracted_summary": summary_text}, ensure_ascii=False)
            status = "reused_legacy_summary"
        else:
            prompt_text = build_prompt(
                case_id=case_id,
                spec=spec,
                trace_summary=trace_summary,
                raw_trace_input=raw_trace_input,
            )
            prompt_path = prompt_dir / f"{case_id}.txt"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt_text + "\n", encoding="utf-8")

            if args.dry_run:
                summary_text = (
                    "Abstracted trace summary:\n"
                    "- Dry-run placeholder.\n"
                    "- Dry-run placeholder.\n"
                    "- Dry-run placeholder.\n"
                    "- Dry-run placeholder."
                )
                raw_response = ""
                status = "dry_run_placeholder"
            else:
                raw_response = post_model_chat(model_spec, prompt_text, temperature=float(args.temperature))
                summary_text = coerce_abstracted_summary(raw_response)
                status = "generated"

            response_path = response_dir / f"{case_id}.txt"
            response_path.parent.mkdir(parents=True, exist_ok=True)
            response_path.write_text(raw_response + ("\n" if raw_response else ""), encoding="utf-8")

            prompt_log_rows.append(
                {
                    "case_id": case_id,
                    "status": status,
                    "summary_model": model_spec["model_label"],
                    "prompt_path": str(prompt_path.resolve()),
                    "response_path": str(response_path.resolve()),
                }
            )

        existing_rows[case_id] = {
            "case_id": case_id,
            "abstracted_summary": summary_text,
            "summary_model_label": model_spec["model_label"],
            "summary_provider": str(model_spec["provider"]),
            "summary_model_name": str(model_spec["model_name"]),
            "source": status,
            "spec": spec,
            "normal_trace_summary": trace_summary,
        }

        contract_errors = validate_temporal_relation_abstraction(
            summary_text,
            **contract_inputs,
        )
        if contract_errors:
            raise RuntimeError(f"Temporal abstraction contract failed for {case_id}: {contract_errors}")

    ordered_rows = [existing_rows[case_id] for case_id in selected_case_ids if case_id in existing_rows]
    write_json_list(shard_json, ordered_rows)
    write_prompt_log(shard_log_csv, prompt_log_rows)

    run_meta = {
        "cases_root": str(cases_root),
        "output_dir": str(output_dir),
        "selected_case_ids": selected_case_ids,
        "summary_model_spec": {
            "model_label": model_spec["model_label"],
            "provider": model_spec["provider"],
            "model_name": model_spec["model_name"],
        },
        "temperature": float(args.temperature),
        "shard_index": int(args.shard_index),
        "shard_count": int(args.shard_count),
        "dry_run": bool(args.dry_run),
        "argv": sys.argv,
        "shard_json": str(shard_json.resolve()),
        "shard_prompt_log_csv": str(shard_log_csv.resolve()),
    }
    (output_dir / "scale120_abstracted_summary_generation_run_meta.json").write_text(
        json.dumps(run_meta, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(shard_json)
    print(shard_log_csv)


if __name__ == "__main__":
    main()
