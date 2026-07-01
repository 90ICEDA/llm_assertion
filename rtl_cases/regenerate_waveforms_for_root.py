#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    root = Path(args.root).resolve()
    converter = Path(args.converter).resolve()

    if shutil.which(args.iverilog) is None:
        raise RuntimeError(f"Cannot find iverilog binary: {args.iverilog}")
    if shutil.which(args.vvp) is None:
        raise RuntimeError(f"Cannot find vvp binary: {args.vvp}")
    if not converter.exists():
        raise FileNotFoundError(f"Missing converter script: {converter}")

    for case_dir in sorted(root.glob("case*")):
        if not case_dir.is_dir():
            continue
        tb_v = case_dir / "tb.v"
        tb_holdout_v = case_dir / "tb_holdout.v"
        if not tb_v.exists():
            print(f"[SKIP] {case_dir.name}: missing tb.v")
            continue

        case_id = case_dir.name.split("_", 1)[0]
        print(f"[INFO] {case_dir.name}")

        run([args.iverilog, "-g2012", "-o", "sim_good", "./correct.v", "./tb.v"], case_dir)
        run([args.vvp, "./sim_good"], case_dir)
        (case_dir / f"{case_id}.vcd").replace(case_dir / "waveform_good.vcd")
        run(["python3", str(converter), "waveform_good.vcd", "waveform_good.csv"], case_dir)

        run([args.iverilog, "-g2012", "-o", "sim_bad", "./buggy.v", "./tb.v"], case_dir)
        run([args.vvp, "./sim_bad"], case_dir)
        (case_dir / f"{case_id}.vcd").replace(case_dir / "waveform_bad.vcd")
        run(["python3", str(converter), "waveform_bad.vcd", "waveform_bad.csv"], case_dir)

        if tb_holdout_v.exists():
            holdout_vcd = f"{case_id}_holdout.vcd"
            run(
                [args.iverilog, "-g2012", "-o", "sim_good_holdout", "./correct.v", "./tb_holdout.v"],
                case_dir,
            )
            run([args.vvp, "./sim_good_holdout"], case_dir)
            (case_dir / holdout_vcd).replace(case_dir / "waveform_good_holdout.vcd")
            run(["python3", str(converter), "waveform_good_holdout.vcd", "waveform_good_holdout.csv"], case_dir)

            run(
                [args.iverilog, "-g2012", "-o", "sim_bad_holdout", "./buggy.v", "./tb_holdout.v"],
                case_dir,
            )
            run([args.vvp, "./sim_bad_holdout"], case_dir)
            (case_dir / holdout_vcd).replace(case_dir / "waveform_bad_holdout.vcd")
            run(["python3", str(converter), "waveform_bad_holdout.vcd", "waveform_bad_holdout.csv"], case_dir)

        for sim_name in [
            "sim_good",
            "sim_bad",
            "sim_good_holdout",
            "sim_bad_holdout",
        ]:
            sim_path = case_dir / sim_name
            if sim_path.exists():
                sim_path.unlink()

    print(f"[DONE] Waveform regeneration completed for {root}")


if __name__ == "__main__":
    main()
