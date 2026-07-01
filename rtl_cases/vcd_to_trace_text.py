#!/usr/bin/env python3
import argparse
from pathlib import Path

from vcd_to_csv import parse_vcd


def main():
    parser = argparse.ArgumentParser(description="Convert VCD into per-cycle text trace.")
    parser.add_argument("vcd", help="Input VCD file path.")
    parser.add_argument("out", help="Output text trace path.")
    parser.add_argument(
        "--signals",
        default="",
        help="Comma-separated signal names to keep (example: req,grant,state,valid_i,ready_i).",
    )
    args = parser.parse_args()

    vcd_path = Path(args.vcd).resolve()
    out_path = Path(args.out).resolve()
    keep = [s.strip() for s in args.signals.split(",") if s.strip()]

    name_map, ids, rows = parse_vcd(vcd_path)
    col_names = [name_map[sid].split(".")[1] for sid in ids]
    sid_by_name = {n: sid for sid, n in zip(ids, col_names)}

    if keep:
        sig_names = [s for s in keep if s in sid_by_name]
    else:
        sig_names = col_names

    clk_sid = sid_by_name.get("clk")
    cycle = 0
    lines = []

    if clk_sid is None:
        for _, snap in rows:
            vals = [f"{s}={snap[sid_by_name[s]]}" for s in sig_names]
            lines.append(f"cycle {cycle}: " + ", ".join(vals))
            cycle += 1
    else:
        prev_clk = None
        for _, snap in rows:
            curr_clk = snap.get(clk_sid, "0")
            if prev_clk is not None and prev_clk == "0" and curr_clk == "1":
                vals = [f"{s}={snap[sid_by_name[s]]}" for s in sig_names]
                lines.append(f"cycle {cycle}: " + ", ".join(vals))
                cycle += 1
            prev_clk = curr_clk

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"[DONE] Wrote {out_path}")


if __name__ == "__main__":
    main()
