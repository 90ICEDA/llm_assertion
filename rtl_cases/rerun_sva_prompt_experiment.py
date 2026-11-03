#!/usr/bin/env python3
import argparse
import shlex
import subprocess
from pathlib import Path
from typing import List


def run_cmd(cmd: List[str], cwd: Path) -> None:
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"[RUN] {printable}")
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild prompt assets, regenerate SVA, run strict eval, and compare against a baseline report."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument(
        "--baseline-report",
        default="strict_eval_report.csv",
        help="Baseline strict eval CSV to compare against.",
    )
    parser.add_argument(
        "--new-report",
        default="strict_eval_report_rerun.csv",
        help="Output path for the new strict eval CSV.",
    )
    parser.add_argument(
        "--comparison-prefix",
        default="strict_eval_comparison_rerun",
        help="Output prefix for comparison CSV/MD.",
    )
    parser.add_argument("--case", help="Optional single case to rerun.")
    parser.add_argument(
        "--methods",
        help="Optional comma-separated method filter. Example: 3,4 or spec_rtl_raw_trace,spec_rtl_trace_summary.",
    )
    parser.add_argument(
        "--llm-command",
        help="LLM command template passed through to generate_sva_from_prompts.py.",
    )
    parser.add_argument(
        "--ollama-model",
        help="Ollama model passed through to generate_sva_from_prompts.py.",
    )
    parser.add_argument(
        "--ollama-base-url",
        help="Optional Ollama base URL passed through to generate_sva_from_prompts.py.",
    )
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--num-candidates", type=int, default=5)
    parser.add_argument("--iverilog", default="iverilog")
    parser.add_argument("--vvp", default="vvp")
    parser.add_argument(
        "--skip-compare",
        action="store_true",
        help="Skip before/after comparison and only produce the new full report plus method summary.",
    )
    args = parser.parse_args()

    if not args.ollama_model and not args.llm_command:
        parser.error("Provide either --ollama-model or --llm-command.")
    if args.ollama_model and args.llm_command:
        parser.error("Use only one of --ollama-model or --llm-command.")

    root = Path(args.root).resolve()
    baseline_report = (root / args.baseline_report).resolve()
    new_report = (root / args.new_report).resolve()
    comparison_prefix = (root / args.comparison_prefix).resolve()

    prepare_cmd = ["python3", "prepare_prompt_assets.py", "--root", str(root)]
    summary_cmd = ["python3", "summarize_trace_divergence.py", "--root", str(root)]
    generate_cmd = [
        "python3",
        "generate_sva_from_prompts.py",
        "--root",
        str(root),
        "--max-attempts",
        str(args.max_attempts),
        "--num-candidates",
        str(args.num_candidates),
    ]
    eval_cmd = [
        "python3",
        "evaluate_generated_sva.py",
        "--root",
        str(root),
        "--output-csv",
        str(new_report),
        "--iverilog",
        args.iverilog,
        "--vvp",
        args.vvp,
    ]
    postprocess_cmd = [
        "python3",
        "postprocess_strict_eval_report.py",
        "--report",
        str(new_report),
    ]
    compare_cmd = [
        "python3",
        "compare_strict_eval_reports.py",
        "--before",
        str(baseline_report),
        "--after",
        str(new_report),
        "--output-prefix",
        str(comparison_prefix),
    ]
    method_summary_cmd = [
        "python3",
        "summarize_strict_eval_by_method.py",
        "--report",
        str(new_report),
        "--output-prefix",
        str(comparison_prefix) + "_by_method",
    ]

    if args.case:
        generate_cmd.extend(["--case", args.case])
        eval_cmd.extend(["--case", args.case])
    if args.methods:
        generate_cmd.extend(["--methods", args.methods])
        eval_cmd.extend(["--methods", args.methods])

    if args.ollama_model:
        generate_cmd.extend(["--ollama-model", args.ollama_model])
        if args.ollama_base_url:
            generate_cmd.extend(["--ollama-base-url", args.ollama_base_url])
    else:
        generate_cmd.extend(["--llm-command", args.llm_command])

    run_cmd(summary_cmd, root)
    run_cmd(prepare_cmd, root)
    run_cmd(generate_cmd, root)
    run_cmd(eval_cmd, root)
    if (root / "postprocess_strict_eval_report.py").exists():
        run_cmd(postprocess_cmd, root)
    run_cmd(method_summary_cmd, root)
    if not args.skip_compare:
        run_cmd(compare_cmd, root)


if __name__ == "__main__":
    main()
