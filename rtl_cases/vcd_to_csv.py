#!/usr/bin/env python3
import csv
import re
import sys
from pathlib import Path


def parse_vcd(vcd_path: Path):
    id_to_names = {}
    id_to_width = {}
    values = {}
    tracked_ids = []
    times = []
    rows = []

    scope_stack = []
    in_header = True
    current_time = 0

    def is_pulse_sid(sid: str) -> bool:
        names = id_to_names.get(sid, [])
        return any(name.endswith(".q_posedge_pulse_o") or name.endswith(".q_negedge_pulse_o") for name in names)

    def full_name(name: str) -> str:
        if scope_stack:
            return ".".join(scope_stack + [name])
        return name

    with vcd_path.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            if in_header:
                if line.startswith("$scope"):
                    parts = line.split()
                    if len(parts) >= 3:
                        scope_stack.append(parts[2])
                elif line.startswith("$upscope"):
                    if scope_stack:
                        scope_stack.pop()
                elif line.startswith("$var"):
                    # $var wire 1 ! clk $end
                    # $var wire 8 " data [7:0] $end
                    parts = line.split()
                    if len(parts) >= 5:
                        width = int(parts[2])
                        symbol = parts[3]
                        name = parts[4]
                        if "[" in name:
                            clean = name
                        elif width > 1:
                            clean = f"{name}[{width-1}:0]"
                        else:
                            clean = name
                        fq = full_name(clean)
                        if symbol not in id_to_names:
                            id_to_names[symbol] = []
                        id_to_names[symbol].append(fq)
                        if symbol not in id_to_width:
                            id_to_width[symbol] = width
                        if symbol not in values:
                            values[symbol] = "x" if width == 1 else ("x" * width)
                        if symbol not in tracked_ids:
                            tracked_ids.append(symbol)
                elif line.startswith("$enddefinitions"):
                    in_header = False
                continue

            if line.startswith("#"):
                current_time = int(line[1:])
                if not times or times[-1] != current_time:
                    times.append(current_time)
                    snapshot = {sid: values[sid] for sid in tracked_ids}
                    rows.append((current_time, snapshot))
                continue

            # scalar: 1! / 0! / x!
            m_scalar = re.match(r"([01xXzZ])(.+)", line)
            if m_scalar and not line.startswith("b"):
                val = m_scalar.group(1).lower()
                sid = m_scalar.group(2).strip()
                if sid in values:
                    values[sid] = val
                    if times and rows and rows[-1][0] == current_time:
                        if is_pulse_sid(sid):
                            prev_val = rows[-1][1].get(sid, "0")
                            rows[-1][1][sid] = "1" if prev_val == "1" or val == "1" else "0"
                        else:
                            rows[-1][1][sid] = val
                continue

            # vector: b1010 !
            m_vec = re.match(r"b([01xXzZ]+)\s+(.+)", line)
            if m_vec:
                val = m_vec.group(1).lower()
                sid = m_vec.group(2).strip()
                if sid in values:
                    width = id_to_width.get(sid, len(val))
                    if len(val) < width:
                        if re.fullmatch(r"[01]+", val):
                            val = val.zfill(width)
                        else:
                            fill = val[0] if val else "x"
                            val = (fill * (width - len(val))) + val
                    values[sid] = val
                    if times and rows and rows[-1][0] == current_time:
                        if is_pulse_sid(sid):
                            prev_val = rows[-1][1].get(sid, "0" * width)
                            rows[-1][1][sid] = val if "1" in prev_val or "1" in val else prev_val
                        else:
                            rows[-1][1][sid] = val
                continue

    # Keep only top-level tb signals for cleaner CSV.
    # Example: tb_case01.clk, tb_case01.rst_n, ...
    def pick_name(sid: str):
        names = id_to_names.get(sid, [])
        tb_level = [n for n in names if n.count(".") == 1]
        if tb_level:
            return sorted(tb_level, key=lambda x: len(x))[0]
        if names:
            return sorted(names, key=lambda x: (x.count("."), len(x)))[0]
        return sid

    chosen_name = {sid: pick_name(sid) for sid in tracked_ids}

    filtered = []
    for sid in tracked_ids:
        name = chosen_name[sid]
        if name.count(".") == 1:
            filtered.append(sid)

    # Stable ordering: clk first, then rst, then others alphabetically.
    def sort_key(sid: str):
        n = chosen_name[sid].split(".")[1]
        if n == "clk":
            return (0, n)
        if "rst" in n:
            return (1, n)
        return (2, n)

    filtered.sort(key=sort_key)

    return chosen_name, filtered, rows


def write_csv(out_path: Path, id_to_name, ids, rows):
    cols = ["time_ps"] + [id_to_name[sid].split(".")[1] for sid in ids]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for t, snap in rows:
            writer.writerow([t] + [snap[sid] for sid in ids])


def main():
    if len(sys.argv) != 3:
        print("Usage: vcd_to_csv.py <input.vcd> <output.csv>")
        sys.exit(1)
    vcd = Path(sys.argv[1])
    out = Path(sys.argv[2])
    id_to_name, ids, rows = parse_vcd(vcd)
    write_csv(out, id_to_name, ids, rows)


if __name__ == "__main__":
    main()
