#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Command failed in {cwd}:\n{' '.join(cmd)}\n\n{proc.stdout}"
        )


DUMPFILE_RE = re.compile(r'\$dumpfile\("(?P<name>[^"]+)"\);')


def expected_dumpfile(tb_path: Path) -> str:
    tb_text = tb_path.read_text(encoding="utf-8")
    match = DUMPFILE_RE.search(tb_text)
    if not match:
        raise RuntimeError(f"Cannot find $dumpfile(...) in {tb_path}")
    return match.group("name")


def move_dumpfile(case_dir: Path, generated_name: str, target_name: str) -> None:
    generated = case_dir / generated_name
    target = case_dir / target_name
    if not generated.exists():
        raise FileNotFoundError(
            f"Expected generated VCD {generated} was not produced in {case_dir}"
        )
    if target.exists():
        target.unlink()
    generated.replace(target)


def convert_vcd(case_dir: Path, converter: Path, vcd_name: str, csv_name: str) -> None:
    run(["python3", str(converter), vcd_name, csv_name], case_dir)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate waveform VCD/CSV files for any dataset root that follows the caseXX_* layout."
    )
    parser.add_argument("--root", required=True, help="Dataset root.")
    parser.add_argument("--iverilog", default="iverilog", help="iverilog binary name/path.")
    parser.add_argument("--vvp", default="vvp", help="vvp binary name/path.")
    parser.add_argument(
        "--converter",
        default="vcd_to_csv.py",
        help="Path to the VCD->CSV converter script.",
    )
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="Optional case name filter. Repeat to regenerate multiple cases.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    converter = Path(args.converter).resolve()

    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")
    if not converter.exists():
        raise FileNotFoundError(f"Missing converter script: {converter}")

    requested = {name.strip() for name in args.case if name.strip()}
    case_dirs = [case_dir for case_dir in sorted(root.glob("case*")) if case_dir.is_dir()]
    if requested:
        known = {case_dir.name for case_dir in case_dirs}
        unknown = sorted(requested - known)
        if unknown:
            raise RuntimeError(f"Unknown case filters: {', '.join(unknown)}")
        case_dirs = [case_dir for case_dir in case_dirs if case_dir.name in requested]

    for case_dir in case_dirs:
        tb_v = case_dir / "tb.v"
        tb_holdout_v = case_dir / "tb_holdout.v"
        tb_decoy_v = case_dir / "tb_decoy.v"
        if not tb_v.exists():
            print(f"[SKIP] {case_dir.name}: missing tb.v")
            continue

        case_id = case_dir.name.split("_", 1)[0]
        print(f"[INFO] {case_dir.name}")

        primary_dumpfile = expected_dumpfile(tb_v)
        run([args.iverilog, "-g2012", "-o", "sim_good", "./correct.v", "./tb.v"], case_dir)
        run([args.vvp, "./sim_good"], case_dir)
        move_dumpfile(case_dir, primary_dumpfile, "waveform_good.vcd")
        convert_vcd(case_dir, converter, "waveform_good.vcd", "waveform_good.csv")

        run([args.iverilog, "-g2012", "-o", "sim_bad", "./buggy.v", "./tb.v"], case_dir)
        run([args.vvp, "./sim_bad"], case_dir)
        move_dumpfile(case_dir, primary_dumpfile, "waveform_bad.vcd")
        convert_vcd(case_dir, converter, "waveform_bad.vcd", "waveform_bad.csv")

        if tb_holdout_v.exists():
            holdout_dumpfile = expected_dumpfile(tb_holdout_v)
            run(
                [args.iverilog, "-g2012", "-o", "sim_good_holdout", "./correct.v", "./tb_holdout.v"],
                case_dir,
            )
            run([args.vvp, "./sim_good_holdout"], case_dir)
            move_dumpfile(case_dir, holdout_dumpfile, "waveform_good_holdout.vcd")
            convert_vcd(case_dir, converter, "waveform_good_holdout.vcd", "waveform_good_holdout.csv")

            run(
                [args.iverilog, "-g2012", "-o", "sim_bad_holdout", "./buggy.v", "./tb_holdout.v"],
                case_dir,
            )
            run([args.vvp, "./sim_bad_holdout"], case_dir)
            move_dumpfile(case_dir, holdout_dumpfile, "waveform_bad_holdout.vcd")
            convert_vcd(case_dir, converter, "waveform_bad_holdout.vcd", "waveform_bad_holdout.csv")

        if tb_decoy_v.exists():
            decoy_dumpfile = expected_dumpfile(tb_decoy_v)
            run(
                [args.iverilog, "-g2012", "-o", "sim_good_decoy", "./correct.v", "./tb_decoy.v"],
                case_dir,
            )
            run([args.vvp, "./sim_good_decoy"], case_dir)
            move_dumpfile(case_dir, decoy_dumpfile, "waveform_good_decoy.vcd")
            convert_vcd(case_dir, converter, "waveform_good_decoy.vcd", "waveform_good_decoy.csv")

            run(
                [args.iverilog, "-g2012", "-o", "sim_bad_decoy", "./buggy.v", "./tb_decoy.v"],
                case_dir,
            )
            run([args.vvp, "./sim_bad_decoy"], case_dir)
            move_dumpfile(case_dir, decoy_dumpfile, "waveform_bad_decoy.vcd")
            convert_vcd(case_dir, converter, "waveform_bad_decoy.vcd", "waveform_bad_decoy.csv")

        for sim_name in [
            "sim_good",
            "sim_bad",
            "sim_good_holdout",
            "sim_bad_holdout",
            "sim_good_decoy",
            "sim_bad_decoy",
        ]:
            sim_path = case_dir / sim_name
            if sim_path.exists():
                sim_path.unlink()

    print(f"[DONE] Waveform regeneration completed for {root}")


if __name__ == "__main__":
    main()
