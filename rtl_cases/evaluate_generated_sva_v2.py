#!/usr/bin/env python3
import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def run_cmd(cmd: List[str], cwd: Path) -> None:
    printable = " ".join(shlex.quote(part) for part in cmd)
    print(f"[RUN] {printable}")
    result = subprocess.run(cmd, cwd=str(cwd), check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def can_run_sim(iverilog_bin: str, vvp_bin: str) -> bool:
    return shutil.which(iverilog_bin) is not None and shutil.which(vvp_bin) is not None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V2 evaluator: run strict simulation eval (optional) and regenerate deliverable tables/docs."
    )
    parser.add_argument("--root", default=".", help="Path to rtl_cases root.")
    parser.add_argument(
        "--output-csv",
        default="strict_eval_report_rerun.csv",
        help="Strict evaluation CSV output path.",
    )
    parser.add_argument("--iverilog", default="iverilog")
    parser.add_argument("--vvp", default="vvp")
    parser.add_argument("--case", help="Optional single case to evaluate.")
    parser.add_argument(
        "--skip-sim-eval",
        action="store_true",
        help="Skip simulation evaluation and only regenerate deliverable docs from --output-csv.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    out_csv = (root / args.output_csv).resolve()

    if not args.skip_sim_eval:
        if not can_run_sim(args.iverilog, args.vvp):
            raise SystemExit(
                f"Simulation tools not found (iverilog={args.iverilog}, vvp={args.vvp}). "
                "Use --skip-sim-eval to regenerate docs from an existing strict report."
            )
        eval_cmd = [
            sys.executable,
            "evaluate_generated_sva.py",
            "--root",
            str(root),
            "--output-csv",
            str(out_csv),
            "--iverilog",
            args.iverilog,
            "--vvp",
            args.vvp,
        ]
        if args.case:
            eval_cmd.extend(["--case", args.case])
        run_cmd(eval_cmd, root)
    elif not out_csv.exists():
        raise SystemExit(
            f"--skip-sim-eval was set but report does not exist: {out_csv}"
        )

    summarize_cmd = [
        sys.executable,
        "generate_eval_deliverables.py",
        "--root",
        str(root),
        "--strict-report",
        str(out_csv),
    ]
    run_cmd(summarize_cmd, root)
    print(f"[DONE] V2 flow complete. strict report: {out_csv}")


if __name__ == "__main__":
    main()
