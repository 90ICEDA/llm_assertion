#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "rtl_cases_real_scale210_independent"
TRACKS = (
    ("primary", "tb.v"),
    ("heldout", "tb_holdout.v"),
    ("decoy", "tb_decoy.v"),
)

RESERVED = {
    "and", "or", "not", "posedge", "negedge", "iff", "disable", "if", "else",
    "begin", "end", "true", "false", "assert", "property",
}
MONITOR_CONSTANTS = {"DATA_WIDTH"}


def balanced(text: str, start: int) -> tuple[str, int]:
    assert text[start] == "("
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(": depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0: return text[start + 1:i], i + 1
    raise ValueError("unbalanced parentheses")


def strip_outer(text: str) -> str:
    text = text.strip()
    while text.startswith("("):
        try: inner, end = balanced(text, 0)
        except ValueError: break
        if end != len(text): break
        text = inner.strip()
    return text


def split_top(text: str, token: str) -> tuple[str, str] | None:
    depth = bracket = 0
    i = 0
    while i <= len(text) - len(token):
        ch = text[i]
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        elif ch == "[": bracket += 1
        elif ch == "]": bracket -= 1
        if depth == 0 and bracket == 0 and text.startswith(token, i):
            return text[:i].strip(), text[i + len(token):].strip()
        i += 1
    return None


def qualify(expr: str) -> str:
    """Qualify design identifiers with tb.; keep SV syntax and system functions."""
    token_re = re.compile(r"\$[A-Za-z_]\w*|[A-Za-z_]\w*|\d+'[sS]?[bodhBODH][0-9a-fA-F_xXzZ?]+|\d+")
    out, last = [], 0
    for m in token_re.finditer(expr):
        out.append(expr[last:m.start()])
        tok = m.group(0)
        prev = expr[m.start() - 1] if m.start() else ""
        if tok.startswith("$") or tok[0].isdigit() or tok in RESERVED or tok in MONITOR_CONSTANTS or prev == ".":
            out.append(tok)
        else:
            out.append("tb." + tok)
        last = m.end()
    out.append(expr[last:])
    result = "".join(out)
    hierarchy_workarounds = {
        "tb.s_axis_tready[tb.select]": "tb.s_axis_tready_selected",
        "tb.m_axis_tvalid[tb.select]": "tb.m_axis_tvalid_selected",
        "tb.s_axis_tdata[tb.select*DATA_WIDTH +: DATA_WIDTH]": "tb.s_axis_tdata_selected",
        "tb.m_axis_tdata[tb.select*DATA_WIDTH +: DATA_WIDTH]": "tb.m_axis_tdata_selected",
    }
    for source, alias in hierarchy_workarounds.items():
        result = result.replace(source, alias)
    return result


def extract_properties(text: str) -> list[str]:
    text = re.sub(r"//.*", "", text)
    found, pos = [], 0
    needle = "assert property"
    while True:
        start = text.find(needle, pos)
        if start < 0: break
        p = text.find("(", start + len(needle))
        inner, end = balanced(text, p)
        found.append(inner.strip())
        pos = end
    return found


def parse_property(prop: str) -> dict:
    if not prop.startswith("@"):
        raise ValueError("missing event control")
    p = prop.find("(")
    event, end = balanced(prop, p)
    rest = prop[end:].strip()
    disable = None
    if rest.startswith("disable iff"):
        p = rest.find("(")
        disable, end = balanced(rest, p)
        rest = rest[end:].strip()
    # Generated assertions may wrap the complete sequence expression, e.g.
    # ``(req |-> ack)``.  Remove only balanced full-expression wrappers before
    # looking for a top-level implication operator.
    rest = strip_outer(rest)
    implication = None
    parts = split_top(rest, "|=>")
    if parts:
        implication = "nonoverlap"
    else:
        parts = split_top(rest, "|->")
        if parts: implication = "overlap"
    if parts:
        antecedent, consequent = map(strip_outer, parts)
    else:
        antecedent, consequent = "1'b1", strip_outer(rest)
    return {"event": event.strip(), "disable": strip_outer(disable) if disable else None,
            "antecedent": antecedent, "consequent": consequent, "implication": implication or "invariant"}


def json_candidates(path: Path) -> list[dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    values = doc.get("assertions", doc.get("candidates", []))
    out = []
    for i, item in enumerate(values):
        out.append({
            "name": item.get("name") or item.get("id") or f"weak_{i+1}",
            "kind": item.get("kind") or item.get("weakness_class") or item.get("weakening_type"),
            "declared_nonempty": bool(item.get("nonempty_antecedent", item.get("antecedent_nonempty", False))),
        })
    return out


def case_input_hashes(case_dir: Path) -> dict[str, str]:
    names = ("correct.v", "buggy.v", "tb.v", "tb_holdout.v", "golden.sva", "weak_assertions.sva", "weak_assertions.json")
    return {name: hashlib.sha256((case_dir / name).read_bytes()).hexdigest() for name in names}


def monitor_block(index: int, name: str, parsed: dict) -> tuple[str, dict]:
    event = parsed["event"]
    qevent = qualify(event)
    disable = qualify(parsed["disable"]) if parsed["disable"] else "1'b0"
    ant, cons = parsed["antecedent"], parsed["consequent"]
    prefix = f"af_{index}"
    declarations = [f"integer {prefix}_hits = 0;", f"integer {prefix}_fails = 0;"]
    setup: list[str] = []
    body: list[str] = []
    final_extra = ""

    # Consecutive antecedent: A[*N] |-> C.
    repeat = re.fullmatch(r"\(?(.+?)\)?\s*\[\*(\d+)\]", ant)
    consequent_repeat = re.fullmatch(
        r"\(?(.+?)\)?\s*\[\*(\d+)\]\s*##1\s*(.+)", cons
    )
    seq = split_top(ant, "##1")
    eventual = re.fullmatch(r"##\[(\d+):(\d+|\$)\]\s*(.+)", cons)
    exact_delay = re.fullmatch(r"##(\d+)\s+(.+)", cons)
    sampled = re.findall(r"\$(?:past|stable|rose|fell)\(\s*([^()]+?)\s*\)", ant + " " + cons)
    history = {}
    for n, signal in enumerate(dict.fromkeys(x.strip() for x in sampled)):
        value, valid = f"{prefix}_hist_{n}", f"{prefix}_hist_valid_{n}"
        # Avoid an Icarus 12 vvp width crash caused by $bits(hierarchical_ref).
        # Dataset sampled expressions are <=64 bits; zero extension preserves
        # their Boolean/equality semantics in these monitors.
        declarations += [f"logic [63:0] {value};", f"logic {valid} = 0;"]
        history[signal] = (value, valid)

    def sampled_expr(expr: str) -> str:
        for signal, (value, valid) in history.items():
            expr = re.sub(rf"\$past\(\s*{re.escape(signal)}\s*\)", value, expr)
            expr = re.sub(rf"\$stable\(\s*{re.escape(signal)}\s*\)", f"({valid} && (({signal}) == {value}))", expr)
            expr = re.sub(rf"\$rose\(\s*{re.escape(signal)}\s*\)", f"({valid} && ({signal}) && !{value})", expr)
            expr = re.sub(rf"\$fell\(\s*{re.escape(signal)}\s*\)", f"({valid} && !({signal}) && {value})", expr)
        result = qualify(expr)
        for value, valid in history.values():
            result = result.replace("tb." + value, value).replace("tb." + valid, valid)
        return result

    qcons = sampled_expr(cons)
    qant = sampled_expr(ant)
    combinational_event = not re.search(r"\b(?:posedge|negedge)\b", event)
    if event == "*":
        # Use an explicit design-signal sensitivity list.  always @* would
        # include the monitor counters and self-trigger; a free-running sample
        # clock can explode when a TB lacks an explicit timescale.
        refs = sorted(set(re.findall(r"tb\.[A-Za-z_]\w*(?:\[[^]]+\])?", " ".join((qant, qcons, disable)))))
        if not refs: raise ValueError("cannot derive combinational sensitivity list")
        qevent = " or ".join(refs)

    if consequent_repeat:
        base = strip_outer(consequent_repeat.group(1))
        count = int(consequent_repeat.group(2))
        tail = strip_outer(consequent_repeat.group(3))
        if count < 1 or count > 32:
            raise ValueError("consequent repetition must be in 1..32")
        declarations.append(f"logic [{count-1}:0] {prefix}_repeat_pipe = '0;")
        body += [
            f"if ({qant}) begin {prefix}_hits <= {prefix}_hits + 1; "
            f"if ((|({sampled_expr(base)})) !== 1'b1) {prefix}_fails <= {prefix}_fails + 1; end"
        ]
        for stage in range(max(count - 1, 0)):
            body.append(
                f"if ({prefix}_repeat_pipe[{stage}] && "
                f"((|({sampled_expr(base)})) !== 1'b1)) {prefix}_fails <= {prefix}_fails + 1;"
            )
        body.append(
            f"if ({prefix}_repeat_pipe[{count-1}] && "
            f"((|({sampled_expr(tail)})) !== 1'b1)) {prefix}_fails <= {prefix}_fails + 1;"
        )
        if count > 1:
            body.append(
                f"{prefix}_repeat_pipe <= "
                f"{{{prefix}_repeat_pipe[{count-2}:0], ({qant})}};"
            )
        else:
            body.append(f"{prefix}_repeat_pipe[0] <= ({qant});")
    elif repeat:
        base, count = strip_outer(repeat.group(1)), int(repeat.group(2))
        declarations.append(f"integer {prefix}_streak = 0;")
        body += [f"if ({sampled_expr(base)}) begin", f"  {prefix}_streak <= {prefix}_streak + 1;",
                 f"  if ({prefix}_streak + 1 >= {count}) begin {prefix}_hits <= {prefix}_hits + 1; if ((|({qcons})) !== 1'b1) {prefix}_fails <= {prefix}_fails + 1; end",
                 f"end else {prefix}_streak <= 0;"]
    elif seq and parsed["implication"] == "nonoverlap":
        a, b = map(strip_outer, seq)
        declarations += [f"logic {prefix}_prev_a = 0;", f"logic {prefix}_pending = 0;"]
        body += [f"if ({prefix}_pending && ((|({qcons})) !== 1'b1)) {prefix}_fails <= {prefix}_fails + 1;",
                 f"{prefix}_pending <= {prefix}_prev_a && ({sampled_expr(b)});",
                 f"if ({prefix}_prev_a && ({sampled_expr(b)})) {prefix}_hits <= {prefix}_hits + 1;",
                 f"{prefix}_prev_a <= ({sampled_expr(a)});"]
    elif exact_delay:
        delay, target = int(exact_delay.group(1)), strip_outer(exact_delay.group(2))
        if delay < 1 or delay > 32: raise ValueError("exact delay must be in 1..32")
        declarations.append(f"logic [{delay-1}:0] {prefix}_delay_pipe = '0;")
        body += [f"if ({prefix}_delay_pipe[{delay-1}] && ((|({sampled_expr(target)})) !== 1'b1)) {prefix}_fails <= {prefix}_fails + 1;",
                 f"{prefix}_delay_pipe <= {{{prefix}_delay_pipe[{max(delay-2,0)}:0], ({qant})}};" if delay > 1 else f"{prefix}_delay_pipe[0] <= ({qant});",
                 f"if ({qant}) {prefix}_hits <= {prefix}_hits + 1;"]
    elif eventual:
        lo, hi, target = int(eventual.group(1)), eventual.group(2), strip_outer(eventual.group(3))
        if lo != 1: raise ValueError("only eventual windows starting at 1 are supported")
        declarations += [f"logic {prefix}_pending = 0;", f"integer {prefix}_age = 0;"]
        body += [f"if ({prefix}_pending) begin",
                 f"  if ({sampled_expr(target)}) begin {prefix}_pending <= 0; {prefix}_age <= 0; end",
                 f"  else begin {prefix}_age <= {prefix}_age + 1;" + (f" if ({prefix}_age >= {int(hi)-1}) begin {prefix}_fails <= {prefix}_fails + 1; {prefix}_pending <= 0; end" if hi != "$" else "") + " end",
                 "end", f"if ({qant}) begin {prefix}_hits <= {prefix}_hits + 1; {prefix}_pending <= 1; {prefix}_age <= 0; end"]
        final_extra = f"if ({prefix}_pending) {prefix}_fails = {prefix}_fails + 1;"
    elif parsed["implication"] == "nonoverlap":
        declarations.append(f"logic {prefix}_pending = 0;")
        body += [f"if ({prefix}_pending && ((|({qcons})) !== 1'b1)) {prefix}_fails <= {prefix}_fails + 1;",
                 f"{prefix}_pending <= ({qant});", f"if ({qant}) {prefix}_hits <= {prefix}_hits + 1;"]
    else:
        body += [f"if ({qant}) begin {prefix}_hits <= {prefix}_hits + 1; if ((|({qcons})) !== 1'b1) {prefix}_fails <= {prefix}_fails + 1; end"]

    for signal, (value, valid) in history.items():
        body += [f"{value} <= {qualify(signal)};", f"{valid} <= 1'b1;"]

    # disable iff cancels in-flight temporal obligations.  It must not erase
    # hits or failures already observed earlier in the same simulation.
    reset: list[str] = []
    history_names = {name for pair in history.values() for name in pair}
    for decl in declarations[2:]:
        m = re.search(r"\b(" + re.escape(prefix) + r"_[A-Za-z0-9_]+)\s*(?:=\s*[^;]+)?;", decl)
        if m and not m.group(1).endswith("_sample_clk") and m.group(1) not in history_names:
            reset.append(f"{m.group(1)} <= '0;")
    # disable iff cancels obligations but sampled-value functions still retain
    # clock history; otherwise $rose(reset_release) can never become true.
    for signal, (value, valid) in history.items():
        reset += [f"{value} <= {qualify(signal)};", f"{valid} <= 1'b1;"]
    settle = "  #0.001;\n" if combinational_event else ""
    code = "\n".join(declarations + setup) + f"\nalways @({qevent}) begin\n{settle}  if ({disable}) begin\n    " + "\n    ".join(reset) + "\n  end else begin\n    " + "\n    ".join(body) + f"\n  end\nend\nfinal begin {final_extra} $display(\"AFMON|{name}|%0d|%0d\", {prefix}_hits, {prefix}_fails); end\n"
    return code, {"supported": True, "parsed": parsed}


def generate_monitor(case_dir: Path) -> tuple[str, list[dict]]:
    weak_props = extract_properties((case_dir / "weak_assertions.sva").read_text(encoding="utf-8"))
    candidates = json_candidates(case_dir / "weak_assertions.json")
    if len(weak_props) != len(candidates): raise ValueError(f"weak JSON/SVA count mismatch: {len(candidates)} != {len(weak_props)}")
    golden_props = extract_properties((case_dir / "golden.sva").read_text(encoding="utf-8"))
    if len(golden_props) != 1: raise ValueError(f"expected one golden property, found {len(golden_props)}")
    entries = [{"name": "golden", "kind": "golden", "declared_nonempty": True, "property": golden_props[0]}]
    entries += [{**c, "property": p} for c, p in zip(candidates, weak_props)]
    blocks, status = [], []
    for i, entry in enumerate(entries):
        try:
            block, detail = monitor_block(i, entry["name"], parse_property(entry["property"]))
            blocks.append(block); status.append({**entry, **detail})
        except Exception as exc:
            status.append({**entry, "supported": False, "error": str(exc)})
    return "`timescale 1ns/1ps\nmodule assertionforge_monitor;\nlocalparam integer DATA_WIDTH = 8;\n" + "\n".join(blocks) + "\nendmodule\n", status


def run(args: argparse.Namespace) -> None:
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        raise SystemExit("ERROR: run inside WSL with iverilog and vvp on PATH")
    dataset, out = args.root.resolve(), args.output.resolve()
    (out / "work").mkdir(parents=True, exist_ok=True); (out / "logs").mkdir(parents=True, exist_ok=True)
    all_case_dirs = sorted(
        p for p in dataset.iterdir() if p.is_dir() and re.match(r"^case\d+_", p.name)
    )
    cases = list(all_case_dirs)
    if args.case:
        cases = [dataset / args.case]
        if not cases[0].is_dir(): raise SystemExit(f"unknown case: {args.case}")
    elif args.resume:
        remaining = []
        for case_dir in cases:
            path = case_dir / "hardness_evaluation.json"
            if not path.is_file():
                remaining.append(case_dir); continue
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
                items = [previous.get("golden", {}), *previous.get("weak_assertions", [])]
                definitions = previous.get("monitor_definitions", [])
                combinational_sampling = any(
                    str(item.get("parsed", {}).get("event", "")) == "*"
                    or not re.search(r"\b(?:posedge|negedge)\b", str(item.get("parsed", {}).get("event", "")))
                    for item in definitions
                )
                revision_ok = int(previous.get("evaluator_revision", 0)) >= 6
                hashes_ok = previous.get("input_hashes") == case_input_hashes(case_dir)
                metrics_complete = all(
                    item.get(track, {}).get("good_failure_count") is not None
                    and item.get(track, {}).get("bad_failure_count") is not None
                    for item in items for track, _ in TRACKS
                )
                complete = bool(previous.get("evaluation_complete")) and metrics_complete and revision_ok and hashes_ok
            except (OSError, json.JSONDecodeError): complete = False
            if not complete: remaining.append(case_dir)
        cases = remaining
    repo = ROOT
    compat = [repo / "rtl_cases/iverilog_compat/cc_pkg_iverilog.sv", repo / "rtl_cases/iverilog_compat/cc_clk_mux_tb_deps.sv",
              repo / "external/opentitan/hw/ip/prim/rtl/prim_util_pkg.sv", repo / "external/opentitan/hw/ip/prim/rtl/prim_count_pkg.sv"]
    include_dirs = [dataset, repo / "external/common_cells/include", repo / "external/common_cells/src", repo / "external/opentitan",
                    repo / "external/opentitan/hw/ip/prim/rtl", repo / "external/verilog-axis/rtl"]
    for number, case_dir in enumerate(cases, 1):
        monitor, definitions = generate_monitor(case_dir)
        monitor_path = out / "work" / f"{case_dir.name}.monitor.sv"
        monitor_path.write_text(monitor, encoding="utf-8")
        result = {"schema_version": 1, "evaluator_revision": 6, "case_name": case_dir.name,
                  "input_hashes": case_input_hashes(case_dir), "monitor_definitions": definitions,
                  "golden": {}, "weak_assertions": []}
        raw: dict[tuple[str, str], dict] = {}
        for track, tb_name in TRACKS:
            for rtl_kind in ("correct", "buggy"):
                key = (track, rtl_kind); log = out / "logs" / f"{case_dir.name}.{track}.{rtl_kind}.log"
                exe = out / "work" / f"{case_dir.name}.{track}.{rtl_kind}.vvp"
                if exe.exists():
                    exe.unlink()
                defs = ["-DCC_CLK_MUX_TB_DEPS"] if case_dir.name.startswith(("case417_", "case418_", "case419_", "case420_")) else []
                cmd = ["iverilog", "-g2012", "-gno-assertions", "-DSYNTHESIS", "-DCOMMON_CELLS_ASSERTS_OFF", *defs, "-i"]
                for inc in [case_dir, *include_dirs]: cmd += ["-I", str(inc)]
                cmd += ["-o", str(exe), *map(str, compat), str(case_dir / f"{rtl_kind}.v"), str(case_dir / tb_name), str(monitor_path)]
                cp = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                text = cp.stdout
                if cp.returncode == 0:
                    vp = subprocess.run(["vvp", str(exe)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    text += vp.stdout; runtime_ok = vp.returncode == 0
                else: runtime_ok = False
                log.write_text(text, encoding="utf-8")
                values = {m.group(1): {"antecedent_hits": int(m.group(2)), "failures": int(m.group(3))}
                          for m in re.finditer(r"AFMON\|([^|]+)\|(\d+)\|(\d+)", text)}
                raw[key] = {"compile_ok": cp.returncode == 0, "runtime_ok": runtime_ok, "values": values}
        for definition in definitions:
            name = definition["name"]
            def track_result(track: str) -> dict:
                good, bad = raw[(track, "correct")], raw[(track, "buggy")]
                gv, bv = good["values"].get(name, {}), bad["values"].get(name, {})
                supported = bool(definition.get("supported"))
                metrics_present = name in good["values"] and name in bad["values"]
                return {"compile_ok": supported and metrics_present and good["compile_ok"] and bad["compile_ok"] and good["runtime_ok"] and bad["runtime_ok"],
                        "good_pass": gv.get("failures", 1) == 0, "bad_fail": bv.get("failures", 0) > 0,
                        "antecedent_hit_good": gv.get("antecedent_hits", 0) > 0, "antecedent_hit_bad": bv.get("antecedent_hits", 0) > 0,
                        "non_vacuous_bad": definition.get("declared_nonempty", False) and bv.get("antecedent_hits", 0) > 0,
                        "good_antecedent_hits": gv.get("antecedent_hits", 0), "bad_antecedent_hits": bv.get("antecedent_hits", 0),
                        "good_failure_count": gv.get("failures"), "bad_failure_count": bv.get("failures")}
            item = {"name": name, "kind": definition["kind"],
                    "declared_nonempty_antecedent": definition.get("declared_nonempty", False),
                    "supported": definition.get("supported", False)}
            item.update({track: track_result(track) for track, _ in TRACKS})
            if name == "golden": result["golden"] = item
            else: result["weak_assertions"].append(item)
        all_items = [result["golden"], *result["weak_assertions"]]
        result["evaluation_complete"] = all(
            item.get("supported", False)
            and all(item[track].get("compile_ok", False) for track, _ in TRACKS)
            for item in all_items
        )
        (case_dir / "hardness_evaluation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"[{number:02d}/{len(cases):02d}] {case_dir.name}")
    evaluations = []
    for case_dir in sorted(
        p for p in dataset.iterdir() if p.is_dir() and re.match(r"^case\d+_", p.name)
    ):
        path = case_dir / "hardness_evaluation.json"
        if path.is_file(): evaluations.append(json.loads(path.read_text(encoding="utf-8")))
    flat = []
    for evaluation in evaluations:
        for item in [evaluation.get("golden", {}), *evaluation.get("weak_assertions", [])]:
            if not item: continue
            row = {"case_name": evaluation["case_name"], "evaluation_complete": evaluation.get("evaluation_complete", False),
                   "assertion_name": item.get("name"), "kind": item.get("kind"), "supported": item.get("supported"),
                   "declared_nonempty_antecedent": item.get("declared_nonempty_antecedent")}
            for track, _ in TRACKS:
                for key, value in item.get(track, {}).items(): row[f"{track}_{key}"] = value
            flat.append(row)
    if flat:
        with (out / "weak_monitor_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(flat[0])); writer.writeheader(); writer.writerows(flat)
    version = subprocess.run(["iverilog", "-V"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT).stdout.splitlines()[0]
    def record_complete(evaluation: dict) -> bool:
        items = [evaluation.get("golden", {}), *evaluation.get("weak_assertions", [])]
        return bool(evaluation.get("evaluation_complete")) and all(
            item.get(track, {}).get("good_failure_count") is not None
            and item.get(track, {}).get("bad_failure_count") is not None
            for item in items for track, _ in TRACKS
        )
    def digest(path: Path) -> str | None:
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    expected_case_count = len(all_case_dirs)
    expected_simulation_count = expected_case_count * len(TRACKS) * 2
    semantic_summary = args.semantic_summary or (ROOT / "outputs/scale210_semantic_validation/semantic_validation_summary.json")
    summary = {"schema_version": 1, "tool": version, "expected_case_count": expected_case_count,
               "evaluated_case_count": len(evaluations), "complete_case_count": sum(record_complete(x) for x in evaluations),
               "all_complete": len(evaluations) == expected_case_count and all(record_complete(x) for x in evaluations),
               "expected_simulation_count": expected_simulation_count, "assertion_result_count": len(flat),
               "input_hashes": {"semantic_validation_summary": digest(semantic_summary),
                                "weak_assertion_schema_summary": digest(dataset / "weak_assertion_schema_summary.json")}}
    (out / "weak_monitor_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"raw monitor logs: {out}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--output", type=Path, default=ROOT / "outputs/scale210_weak_monitor_validation")
    ap.add_argument("--case")
    ap.add_argument("--semantic-summary", type=Path)
    ap.add_argument("--resume", action="store_true", help="skip cases with a complete hardness_evaluation.json")
    run(ap.parse_args())


if __name__ == "__main__": main()
