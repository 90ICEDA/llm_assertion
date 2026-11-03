from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import time
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
THREAD_ID = "019ed9f6-87cf-7830-adb8-595fe2ae140d"
CASES_ROOT = Path(os.environ.get("TRACEABS_CASES_ROOT", str(ROOT / "rtl_cases_real_active"))).resolve()
OUTPUT_DIR = Path(
    os.environ.get("TRACEABS_OUTPUT_DIR", str(ROOT / "outputs" / THREAD_ID / "trace_abstraction_data"))
).resolve()
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL_NAME = "qwen2.5-coder:7b-instruct"


SELECTED_CASES: list[dict[str, Any]] = [
    {
        "case_id": "case101_prim_onehot_multihot_suppressed",
        "selection_tags": "trace_overfit;raw_vs_summary_opposite;literal_hardcoding",
        "selection_reason": "raw trace 候选明显出现 literal 枚举和 antecedent_not_triggered，summary 又过于保守，适合检验 abstraction 是否能保留‘多 hot -> err’关系而不抄字面值。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - The bug is triggered when enable is active and more than one bit of oh_i is high in the same sampled cycle.
            - Good behavior asserts err_o immediately on that enabled multi-hot cycle. Buggy behavior suppresses err_o even though the onehot legality rule is violated.
            - The first good/bad divergence is the first enabled multi-hot input pattern; before that, legal onehot patterns keep err_o low in both traces.
            - Preserve the relation "enabled multi-hot request implies same-cycle error". Do not hardcode the observed multi-hot literal from the seen trace, because held-out uses a different pair of asserted bits.
            """
        ).strip(),
    },
    {
        "case_id": "case104_prim_fifo_full_early",
        "selection_tags": "raw_vs_summary_opposite;tradeoff;summary_loses_info",
        "selection_reason": "summary 侧把 first divergence 的具体 depth/full 值抄得很重，raw 侧又容易退化成局部字面边界；这个 case 很适合检验 abstraction 能否保住‘Depth-1 不能 full’而不写死 3/4。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - Repeated writes fill the FIFO toward the full boundary without intervening reads.
            - The bug is triggered on the last pre-full write: good behavior keeps full_o low while the FIFO still has exactly one slot remaining, but bad behavior asserts full_o one cycle too early and also reports maximum depth too soon.
            - The first divergence is the first boundary approach cycle where good is still "not full" and bad already claims "full".
            - Preserve the boundary relation between write progression, depth tracking, and full_o. Avoid hardcoding the initial pointer state or the observed literal depth values from the seen trace.
            """
        ).strip(),
    },
    {
        "case_id": "case112_prim_intr_test_pulse_dropped",
        "selection_tags": "antecedent_not_triggered;tradeoff;summary_weakened_trigger",
        "selection_reason": "现有 summary 候选经常把 antecedent 写窄，导致 test pulse 根本不触发；适合检验 abstraction 是否能把‘qe 单拍脉冲 -> next-cycle capture’讲清楚。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - A one-cycle software test pulse is issued through reg2hw_intr_test_qe_i while the interrupt path is enabled.
            - Good behavior captures that test pulse and reflects it in the stored interrupt-test state on the next sampled cycle. Buggy behavior drops the one-cycle pulse, so the next-cycle state update never appears.
            - The first divergence occurs immediately after the trigger pulse: good updates the stored state, bad leaves it unchanged.
            - Preserve the cross-cycle trigger/effect relation between the qe pulse and the next-cycle state update. Do not hardcode the observed cycle number or any one-time literal state value.
            """
        ).strip(),
    },
    {
        "case_id": "case124_prim_fifo_clear_ignored",
        "selection_tags": "antecedent_not_triggered;raw_better;summary_loses_info",
        "selection_reason": "clear 路径在现有 summary 里经常被弱化成普通 empty/full 观察，导致 antecedent 不触发；很适合测 abstraction 是否能显式保留‘clear 后下一拍复位占用和指针’。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - The FIFO is first driven to a non-empty occupancy, then an operational clear pulse is asserted.
            - Good behavior resets occupancy and pointers on the next sampled cycle after clear, so the FIFO returns to the empty/reset state immediately. Buggy behavior ignores the clear pulse and retains stale occupancy for at least one extra cycle.
            - The first divergence is the first post-clear cycle where good is already empty/reset but bad still looks occupied.
            - Preserve the relation "clear pulse implies next-cycle reset of occupancy-derived outputs". Avoid hardcoding the seen pointer pair or the exact occupancy literal observed before the clear.
            """
        ).strip(),
    },
    {
        "case_id": "case125_prim_fifo_wrap_late",
        "selection_tags": "trace_overfit;raw_vs_summary_opposite;summary_improves_bug_detection",
        "selection_reason": "raw 侧特别容易写死 wrap 边界附近的数值，summary 侧又容易丢掉‘下一拍 wrap’这层时序，正好适合做 abstraction 对照。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - Consecutive writes advance the write pointer to the wrap boundary, and then one more write attempts to cross that boundary.
            - Good behavior wraps the pointer immediately on the next state update after the boundary write. Buggy behavior delays that wrap by one cycle, temporarily exposing an out-of-range or otherwise inconsistent post-boundary state.
            - The first divergence is the boundary-crossing write: good performs the wrap on time, bad preserves the pre-wrap progression for one cycle too long.
            - Preserve the cross-cycle relation between the boundary write and the next-cycle wrapped pointer/depth behavior. Do not hardcode the observed pointer literal or one specific boundary depth value from the seen trace.
            """
        ).strip(),
    },
    {
        "case_id": "case126_prim_regwe_enable_gap",
        "selection_tags": "trace_overfit;raw_vs_summary_opposite;same_cycle_context_case",
        "selection_reason": "这个 case 的错误并不是 onehot 本身，而是 enable gating；raw trace 容易让模型抄某个 bit 位置，适合看 abstraction 是否能把‘disabled nonzero write-enable illegal’抽出来。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - The checker observes a legal onehot write-enable vector while the global enable is low.
            - Good behavior treats any nonzero write-enable vector as illegal when enable is low and asserts err_o in the same cycle. Buggy behavior ignores that enable mismatch and keeps err_o low.
            - The first divergence is the first disabled-but-nonzero write-enable observation; zero-valued disabled samples are not the bug trigger.
            - Preserve the relation "enable low plus nonzero write-enable implies same-cycle error". Avoid hardcoding the specific onehot bit position seen in the observed trace.
            """
        ).strip(),
    },
    {
        "case_id": "case130_prim_fifo_empty_early",
        "selection_tags": "antecedent_not_triggered;raw_better;summary_more_conservative",
        "selection_reason": "summary 侧在这个 case 上非常容易退化成 vacuous/保守断言；abstracted 版本可以直接强调‘还剩 1 项时 empty 仍必须为 0’。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - The FIFO is drained down to exactly one remaining entry before the final read.
            - Good behavior keeps empty_o low while that last entry is still present. Buggy behavior raises empty_o one cycle too early, before the FIFO is actually empty.
            - The first divergence is the one-entry boundary: good still reports "not empty", bad already reports "empty".
            - Preserve the relation between occupancy-one and empty_o staying low. Do not memorize the observed cycle index, pointer literal, or the exact refill history used to reach the one-entry state.
            """
        ).strip(),
    },
    {
        "case_id": "case135_prim_intr_enable_mask_ignored",
        "selection_tags": "tradeoff;raw_vs_summary_opposite;antecedent_not_triggered",
        "selection_reason": "这个 case 很典型地体现了 correct_pass 和 fail_on_buggy 的 tradeoff：summary 容易更保守，但把真正的 masked corner 弱化掉。",
        "abstracted_summary": textwrap.dedent(
            """
            Abstracted trace summary:
            - Interrupt state has already been raised, and then the enable mask is dropped while the state remains high.
            - Good behavior suppresses intr_o whenever the enable mask is low, even though the stored interrupt state is still set. Buggy behavior ignores the mask and leaves intr_o high.
            - The first divergence is the first masked cycle after the interrupt state is already active: good drives intr_o low, bad keeps it asserted.
            - Preserve the same-cycle masking relation between a low enable and a high stored interrupt state. Avoid hardcoding the exact event prelude or one observed cycle number from the seen trace.
            """
        ).strip(),
    },
]


@dataclass
class PromptBundle:
    case_id: str
    spec: str
    raw_trace_input: str
    normal_trace_summary: str
    abstracted_trace_summary: str
    raw_prompt: str
    normal_summary_prompt: str
    abstracted_summary_prompt: str
    selection_tags: str
    selection_reason: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sanitize_for_doc(text: str) -> str:
    return text.replace("\r\n", "\n").strip()


def collapse_ws(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    return text


def extract_sva_candidates(response: str) -> list[str]:
    cleaned = response.replace("```systemverilog", "").replace("```", "")
    pattern = re.compile(r"assert\s+property\s*\([^;]+;\s*", flags=re.IGNORECASE | re.DOTALL)
    found = []
    for match in pattern.findall(cleaned):
        line = collapse_ws(match)
        line = line.rstrip(";") + ";"
        if line not in found:
            found.append(line)
    if not found:
        for raw_line in cleaned.splitlines():
            line = collapse_ws(raw_line)
            if line.lower().startswith("assert property"):
                if not line.endswith(";"):
                    line += ";"
                if line not in found:
                    found.append(line)
    return found


def post_ollama(prompt: str, *, temperature: float) -> str:
    payload = {
        "model": MODEL_NAME,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert hardware verification engineer. "
                    "Follow the requested output format exactly and stay faithful to the spec, RTL, and traces."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "options": {
            "temperature": temperature,
            "num_ctx": 16384,
            "num_gpu": 0,
            "num_predict": 384,
        },
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTPError {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Ollama URLError: {exc}") from exc
    return (data.get("message") or {}).get("content", "").strip()


def collect_five_candidates(prompt: str, *, case_id: str, variant: str) -> tuple[list[str], list[str]]:
    collected: list[str] = []
    raw_responses: list[str] = []
    temperatures = [0.6, 0.8, 1.0]
    for attempt, temp in enumerate(temperatures, start=1):
        attempt_prompt = prompt
        if collected:
            attempt_prompt += (
                "\n\nDo not repeat any previous candidate. Already seen:\n- "
                + "\n- ".join(collected)
            )
        response = post_ollama(attempt_prompt, temperature=temp)
        raw_responses.append(response)
        for cand in extract_sva_candidates(response):
            if cand not in collected:
                collected.append(cand)
            if len(collected) >= 5:
                return collected[:5], raw_responses
    return collected[:5], raw_responses


def parse_allowed_signals(prompt_text: str) -> list[str]:
    lines = prompt_text.splitlines()
    try:
        start_idx = next(i for i, line in enumerate(lines) if line.strip() == "Allowed signals:")
    except StopIteration as exc:
        raise ValueError("Could not find 'Allowed signals:' header.") from exc

    collected: list[str] = []
    for line in lines[start_idx + 1 :]:
        stripped = line.strip()
        if not stripped:
            if collected:
                break
            continue
        if stripped.startswith("Specification:"):
            break
        collected.append(stripped)

    if not collected:
        raise ValueError("Could not parse allowed signals payload.")
    signals = [sig.strip() for sig in " ".join(collected).split(",") if sig.strip()]
    return signals


def extract_rtl_from_prompt(prompt_text: str) -> str:
    start = prompt_text.find("RTL:\n")
    if start < 0:
        raise ValueError("RTL section not found.")
    tail = prompt_text[start + len("RTL:\n") :]
    cut_markers = ["\n\nGood trace (posedge cycles):", "\n\nTrace divergence summary:"]
    cut_positions = [tail.find(marker) for marker in cut_markers if tail.find(marker) >= 0]
    if not cut_positions:
        return tail.strip()
    cut = min(cut_positions)
    return tail[:cut].strip()


def extract_waveform_guidance(prompt_text: str) -> str:
    match = re.search(
        r"Additional guidance:\s*(.*?)\n\nRTL:",
        prompt_text,
        flags=re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


def make_generation_prompt(
    *,
    allowed_signals: list[str],
    spec: str,
    rtl_text: str,
    trace_section: str,
    additional_guidance: str,
) -> str:
    guidance_block = f"\nAdditional guidance:\n{additional_guidance}\n" if additional_guidance else ""
    return textwrap.dedent(
        f"""
        You are a formal verification engineer.
        Generate exactly five distinct SystemVerilog Assertions in this strict format, one assertion per line:
        assert property (@(posedge clk) disable iff (!rst_n) (<ANTECEDENT>) |-> (<CONSEQUENT>));

        Rules:
        1) Output exactly five assertion lines total. No explanation. No markdown. No numbering.
        2) Use only allowed signals listed below.
        3) Keep antecedent and consequent purely boolean (no ##, no $past, no sequence operators).
        4) No helper/internal names such as next_state, count_next, count_prev, old(...), S_*.
        5) Each candidate must contain exactly one implication operator total: either one |-> or one |=>.
        6) Prefer candidates that pass on good behavior and fail on bad behavior.
        7) Avoid vacuous antecedents: choose conditions that actually appear in the observed traces.
        8) Infer a reusable relation, not a one-off witnessed cycle.
        9) Do not hard-code observed literals such as initial addresses, specific state encodings, or one-off values unless the spec or RTL independently justifies them.
        10) Make the five candidates meaningfully different in antecedent/consequent structure, while staying semantically faithful.

        Allowed signals:
        {", ".join(allowed_signals)}

        Specification:
        {spec}
        {guidance_block}
        RTL:
        {rtl_text}

        {trace_section}
        """
    ).strip()


def make_prompt_bundle(case_meta: dict[str, Any], cases_root: Path | None = None) -> PromptBundle:
    use_cases_root = (cases_root or CASES_ROOT).resolve()
    case_id = case_meta["case_id"]
    case_dir = use_cases_root / case_id / "experiment"
    raw_prompt_src = read_text(case_dir / "prompts" / "prompt_3_spec_rtl_raw_trace.txt")
    summary_prompt_src = read_text(case_dir / "prompts" / "prompt_4_spec_rtl_trace_summary.txt")
    allowed_signals = parse_allowed_signals(raw_prompt_src)
    rtl_text = extract_rtl_from_prompt(raw_prompt_src)
    additional_guidance = extract_waveform_guidance(raw_prompt_src)
    spec = read_text(case_dir / "spec.txt").strip()
    raw_good = read_text(case_dir / "trace_good.txt").strip()
    raw_bad = read_text(case_dir / "trace_bad.txt").strip()
    normal_summary = read_text(case_dir / "trace_summary.txt").strip()
    raw_trace_input = f"Good trace (posedge cycles):\n{raw_good}\n\nBad trace (posedge cycles):\n{raw_bad}"
    raw_prompt = make_generation_prompt(
        allowed_signals=allowed_signals,
        spec=spec,
        rtl_text=rtl_text,
        trace_section=raw_trace_input,
        additional_guidance=additional_guidance,
    )
    normal_prompt = make_generation_prompt(
        allowed_signals=allowed_signals,
        spec=spec,
        rtl_text=rtl_text,
        trace_section=(
            "Normal trace summary (existing summary-style input):\n"
            + normal_summary
            + "\n\nSummary-driven checklist:\n"
            + "- Use the first divergence as observational evidence, not as a literal to memorize.\n"
            + "- Keep the property general across held-out traces.\n"
        ),
        additional_guidance=additional_guidance,
    )
    abstract_prompt = make_generation_prompt(
        allowed_signals=allowed_signals,
        spec=spec,
        rtl_text=rtl_text,
        trace_section=case_meta["abstracted_summary"],
        additional_guidance=additional_guidance,
    )
    return PromptBundle(
        case_id=case_id,
        spec=spec,
        raw_trace_input=raw_trace_input,
        normal_trace_summary=normal_summary,
        abstracted_trace_summary=case_meta["abstracted_summary"],
        raw_prompt=raw_prompt,
        normal_summary_prompt=normal_prompt,
        abstracted_summary_prompt=abstract_prompt,
        selection_tags=case_meta["selection_tags"],
        selection_reason=case_meta["selection_reason"],
    )


ASSERTION_RE = re.compile(
    r"assert\s+property\s*\(\s*@\([^)]*\)\s*disable\s+iff\s*\([^)]*\)\s*(.*)\)\s*;\s*$",
    flags=re.IGNORECASE | re.DOTALL,
)


def split_assertion(assertion_text: str) -> tuple[str, str, str]:
    match = ASSERTION_RE.match(assertion_text.strip())
    if not match:
        raise ValueError(f"Unsupported assertion format: {assertion_text}")
    body = match.group(1).strip()
    for token in ("|->", "|=>"):
        if token in body:
            ant, cons = body.split(token, 1)
            ant = ant.strip()
            cons = cons.strip()
            if ant.startswith("(") and ant.endswith(")"):
                ant = ant[1:-1].strip()
            if cons.startswith("(") and cons.endswith(")"):
                cons = cons[1:-1].strip()
            return ant, token, cons
    # A clocked SVA invariant is a valid candidate even though it has no
    # implication operator, for example:
    #   assert property (@(posedge clk) disable iff (!rst_n) (!full_o));
    # Evaluate it procedurally as ``1'b1 |-> body``.  This also gives the
    # invariant an explicit, non-vacuous monitor antecedent on every sampled
    # cycle instead of aborting the whole experiment batch.
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1].strip()
    if not body:
        raise ValueError(f"Empty assertion body in: {assertion_text}")
    return "1'b1", "|->", body


def first_module_name(tb_text: str) -> str:
    match = re.search(r"module\s+([A-Za-z_][A-Za-z0-9_]*)", tb_text)
    if not match:
        raise ValueError("Could not parse testbench module name.")
    return match.group(1)


def first_module_name_from_file(tb_path: Path, seen: set[Path] | None = None) -> str:
    resolved = tb_path.resolve()
    visited = seen or set()
    if resolved in visited:
        raise ValueError(f"Include cycle while finding testbench module: {resolved}")
    visited.add(resolved)
    text = read_text(resolved)
    match = re.search(r"module\s+([A-Za-z_][A-Za-z0-9_]*)", text)
    if match:
        return match.group(1)
    for include_name in re.findall(r'`include\s+"([^"]+)"', text):
        include_path = resolved.parent / include_name
        if include_path.exists():
            try:
                return first_module_name_from_file(include_path, visited)
            except ValueError:
                pass
    raise ValueError(f"Could not parse testbench module name from {resolved} or its local includes.")


def checker_text(
    *,
    tb_module_name: str,
    signal_names: list[str],
    assertion_text: str,
    antecedent: str,
    implication: str,
    consequent: str,
    use_property: bool,
) -> str:
    def qualify_expr(text: str) -> str:
        replacements: dict[str, str] = {}
        for sig in signal_names:
            replacements[sig] = f"{tb_module_name}.{sig}"
            if "[" in sig:
                base = sig.split("[", 1)[0].strip()
                if base and base not in replacements:
                    replacements[base] = f"{tb_module_name}.{base}"
        out = text
        for sig in sorted(replacements, key=len, reverse=True):
            out = out.replace(sig, replacements[sig])
        return out

    antecedent_q = qualify_expr(antecedent)
    consequent_q = qualify_expr(consequent)
    assertion_q = qualify_expr(assertion_text)
    signal_bases = {sig.split("[", 1)[0].strip() for sig in signal_names}
    if "rst_n" in signal_bases:
        reset_active_q = f"!{tb_module_name}.rst_n"
    elif "rst_ni" in signal_bases:
        reset_active_q = f"!{tb_module_name}.rst_ni"
    elif "rst" in signal_bases:
        reset_active_q = f"{tb_module_name}.rst"
    else:
        reset_active_q = "1'b0"
    if "clk" in signal_bases:
        monitor_event = f"posedge {tb_module_name}.clk"
    elif "clk_i" in signal_bases:
        monitor_event = f"posedge {tb_module_name}.clk_i"
    else:
        monitor_event = "*"

    property_line = (
        f"  ASSERT_USER: {assertion_q}"
        if use_property
        else "  // property assertion disabled after compiler probe"
    )
    # A combinational harness has no sampling clock. Evaluate either implication
    # as a same-event relation; retaining ant_d for |=> would self-trigger an
    # always @(*) monitor in zero simulation time.
    if implication == "|->" or monitor_event == "*":
        monitor_body = textwrap.dedent(
            f"""
              if ({reset_active_q}) begin
                ant_d <= 1'b0;
              end else begin
                if (({antecedent_q})) ant_hits = ant_hits + 1;
                if (({antecedent_q}) && !(({consequent_q}))) fail_hits = fail_hits + 1;
                ant_d <= ({antecedent_q});
              end
            """
        ).strip()
    else:
        monitor_body = textwrap.dedent(
            f"""
              if ({reset_active_q}) begin
                ant_d <= 1'b0;
              end else begin
                if (({antecedent_q})) ant_hits = ant_hits + 1;
                if (ant_d && !(({consequent_q}))) fail_hits = fail_hits + 1;
                ant_d <= ({antecedent_q});
              end
            """
        ).strip()

    return textwrap.dedent(
        f"""
        module traceabs_checker;
          integer ant_hits = 0;
          integer fail_hits = 0;
          reg ant_d = 1'b0;

        {property_line}

          always @({monitor_event}) begin
        {textwrap.indent(monitor_body, '    ')}
          end

          final begin
            $display("TRACEABS_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
          end
        endmodule
        """
    ).strip() + "\n"


def to_wsl_path(path: Path) -> str:
    drive = path.drive.rstrip(":").lower()
    tail = str(path).replace("\\", "/").split(":", 1)[1]
    return f"/mnt/{drive}{tail}"


def run_wsl_bash(command: str, *, timeout_sec: int = 120) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["wsl.exe", "bash", "-lc", command],
        check=False,
        capture_output=True,
        timeout=timeout_sec,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    return subprocess.CompletedProcess(
        args=proc.args,
        returncode=proc.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def run_case_eval(
    *,
    case_id: str,
    assertion_text: str,
    signal_names: list[str],
    use_property: bool,
    runtime_dir: Path,
    cases_root: Path | None = None,
) -> dict[str, Any]:
    use_cases_root = (cases_root or CASES_ROOT).resolve()
    case_dir = use_cases_root / case_id
    correct_v = case_dir / "correct.v"
    buggy_v = case_dir / "buggy.v"
    tb_v = case_dir / "tb.v"
    tb_holdout_v = case_dir / "tb_holdout.v"
    tb_module = first_module_name_from_file(tb_v)
    antecedent, implication, consequent = split_assertion(assertion_text)
    checker_file = runtime_dir / "traceabs_checker.sv"
    write_text(
        checker_file,
        checker_text(
            tb_module_name=tb_module,
            signal_names=signal_names,
            assertion_text=assertion_text,
            antecedent=antecedent,
            implication=implication,
            consequent=consequent,
            use_property=use_property,
        ),
    )

    def run_one(rtl_path: Path, tb_path: Path, tag: str) -> dict[str, Any]:
        build_dir = runtime_dir / tag
        build_dir.mkdir(parents=True, exist_ok=True)
        simv = build_dir / "simv.out"
        compile_cmd = (
            f"cd '{to_wsl_path(build_dir)}' && "
            f"iverilog -g2012 -I '{to_wsl_path(case_dir)}' -o simv.out "
            f"'{to_wsl_path(rtl_path)}' '{to_wsl_path(tb_path)}' '{to_wsl_path(checker_file)}'"
        )
        compile_started = time.perf_counter()
        compile_proc = run_wsl_bash(compile_cmd, timeout_sec=180)
        compile_duration_sec = time.perf_counter() - compile_started
        compile_stdout = compile_proc.stdout or ""
        compile_stderr = compile_proc.stderr or ""
        if compile_proc.returncode != 0:
            return {
                "compile_ok": False,
                "sim_ok": False,
                "ant_hits": 0,
                "fail_hits": 0,
                "compile_stdout": compile_stdout,
                "compile_stderr": compile_stderr,
                "sim_stdout": "",
                "sim_stderr": "",
                "compile_duration_sec": compile_duration_sec,
                "verification_duration_sec": 0.0,
            }

        sim_cmd = f"cd '{to_wsl_path(build_dir)}' && vvp simv.out"
        verify_started = time.perf_counter()
        sim_proc = run_wsl_bash(sim_cmd, timeout_sec=180)
        verification_duration_sec = time.perf_counter() - verify_started
        sim_stdout = sim_proc.stdout or ""
        sim_stderr = sim_proc.stderr or ""
        metric_match = re.search(r"TRACEABS_METRIC ant_hits=(\d+) fail_hits=(\d+)", sim_stdout + "\n" + sim_stderr)
        ant_hits = int(metric_match.group(1)) if metric_match else 0
        fail_hits = int(metric_match.group(2)) if metric_match else 0
        return {
            "compile_ok": True,
            "sim_ok": sim_proc.returncode == 0,
            "ant_hits": ant_hits,
            "fail_hits": fail_hits,
            "compile_stdout": compile_stdout,
            "compile_stderr": compile_stderr,
            "sim_stdout": sim_stdout,
            "sim_stderr": sim_stderr,
            "compile_duration_sec": compile_duration_sec,
            "verification_duration_sec": verification_duration_sec,
        }

    seen_good = run_one(correct_v, tb_v, "seen_good")
    seen_bad = run_one(buggy_v, tb_v, "seen_bad")
    holdout_good = run_one(correct_v, tb_holdout_v, "holdout_good")
    holdout_bad = run_one(buggy_v, tb_holdout_v, "holdout_bad")

    compile_ok = all([seen_good["compile_ok"], seen_bad["compile_ok"], holdout_good["compile_ok"], holdout_bad["compile_ok"]])
    correct_pass = compile_ok and seen_good["fail_hits"] == 0
    buggy_fail = compile_ok and seen_bad["fail_hits"] > 0
    antecedent_hit = compile_ok and seen_bad["ant_hits"] > 0
    non_vacuous = antecedent_hit
    heldout_correct_pass = compile_ok and holdout_good["fail_hits"] == 0
    heldout_buggy_fail = compile_ok and holdout_bad["fail_hits"] > 0
    heldout_antecedent_hit = compile_ok and holdout_bad["ant_hits"] > 0
    heldout_non_vacuous = heldout_antecedent_hit
    trace_overfit = (
        compile_ok
        and correct_pass
        and buggy_fail
        and (
            not heldout_correct_pass
            or not heldout_buggy_fail
            or not heldout_antecedent_hit
        )
    )
    return {
        "compile_ok": compile_ok,
        "correct_pass": correct_pass,
        "buggy_fail": buggy_fail,
        "antecedent_hit": antecedent_hit,
        "non_vacuous": non_vacuous,
        "heldout_correct_pass": heldout_correct_pass,
        "heldout_buggy_fail": heldout_buggy_fail,
        "heldout_antecedent_hit": heldout_antecedent_hit,
        "heldout_non_vacuous": heldout_non_vacuous,
        "trace_overfit": trace_overfit,
        "seen_good_ant_hits": seen_good["ant_hits"],
        "seen_bad_ant_hits": seen_bad["ant_hits"],
        "heldout_good_ant_hits": holdout_good["ant_hits"],
        "heldout_bad_ant_hits": holdout_bad["ant_hits"],
        "seen_good_fail_hits": seen_good["fail_hits"],
        "seen_bad_fail_hits": seen_bad["fail_hits"],
        "heldout_good_fail_hits": holdout_good["fail_hits"],
        "heldout_bad_fail_hits": holdout_bad["fail_hits"],
        "compile_stderr_seen_good": seen_good["compile_stderr"],
        "compile_stderr_seen_bad": seen_bad["compile_stderr"],
        "compile_stderr_holdout_good": holdout_good["compile_stderr"],
        "compile_stderr_holdout_bad": holdout_bad["compile_stderr"],
        "sim_stdout_seen_good": seen_good["sim_stdout"],
        "sim_stdout_seen_bad": seen_bad["sim_stdout"],
        "sim_stdout_holdout_good": holdout_good["sim_stdout"],
        "sim_stdout_holdout_bad": holdout_bad["sim_stdout"],
        "compile_duration_sec": sum(x["compile_duration_sec"] for x in (seen_good, seen_bad, holdout_good, holdout_bad)),
        "verification_duration_sec": sum(x["verification_duration_sec"] for x in (seen_good, seen_bad, holdout_good, holdout_bad)),
    }


def probe_property_support(
    sample_case_id: str,
    *,
    cases_root: Path | None = None,
    runtime_dir: Path | None = None,
) -> bool:
    use_cases_root = (cases_root or CASES_ROOT).resolve()
    use_runtime_dir = (runtime_dir or (OUTPUT_DIR / "_probe")).resolve()
    case_dir = use_cases_root / sample_case_id / "experiment"
    prompt_src = read_text(case_dir / "prompts" / "prompt_3_spec_rtl_raw_trace.txt")
    signal_names = parse_allowed_signals(prompt_src)
    use_runtime_dir.mkdir(parents=True, exist_ok=True)
    sample_assert = "assert property (@(posedge clk) disable iff (!rst_n) (rst_n) |-> (rst_n));"
    try:
        result = run_case_eval(
            case_id=sample_case_id,
            assertion_text=sample_assert,
            signal_names=signal_names,
            use_property=True,
            runtime_dir=use_runtime_dir,
            cases_root=use_cases_root,
        )
    except Exception:
        return False
    return bool(result["compile_ok"])


def judge_semantic_reasonable(
    *,
    spec: str,
    case_id: str,
    candidates: list[str],
) -> dict[str, dict[str, Any]]:
    def heuristic_reason(candidate_text: str) -> dict[str, Any]:
        text = candidate_text.lower()
        literal_patterns = [
            r"\b\d+'[bdho][0-9a-f_xz?]+\b",
            r"\b\d+\b",
            r"\b0x[0-9a-f]+\b",
        ]
        literal_hits = sum(bool(re.search(pat, text)) for pat in literal_patterns)
        suspicious_terms = ["cycle", "observed", "trace", "sample", "captured"]
        suspicious = any(term in text for term in suspicious_terms)
        if "rst_n" in text and len(re.findall(r"\b[a-z_][a-z0-9_]*\b", text)) <= 4:
            return {
                "semantic_reasonable": False,
                "semantic_reason": "Heuristic fallback: reset-only or trivial relation.",
            }
        if literal_hits >= 2 or suspicious:
            return {
                "semantic_reasonable": False,
                "semantic_reason": "Heuristic fallback: likely literal-specific or trace-specific relation.",
            }
        return {
            "semantic_reasonable": True,
            "semantic_reason": "Heuristic fallback: relation appears plausibly aligned with the spec.",
        }

    joined = "\n".join([f"{idx+1}. {cand}" for idx, cand in enumerate(candidates)])
    prompt = textwrap.dedent(
        f"""
        You are reviewing SVA candidates for semantic reasonableness.
        Case: {case_id}
        Specification:
        {spec}

        For each candidate, decide whether it is semantically reasonable:
        - true if it encodes a meaningful relation consistent with the spec
        - false if it is trivial, clearly unrelated, or obviously overfit to one observed literal

        Output JSON only, as an array of objects:
        [{{"candidate_index":1,"semantic_reasonable":true,"reason":"..."}}]

        Candidates:
        {joined}
        """
    ).strip()
    response = post_ollama(prompt, temperature=0.0)
    start = response.find("[")
    end = response.rfind("]")
    out: dict[str, dict[str, Any]] = {}
    if start >= 0 and end >= 0:
        try:
            parsed = json.loads(response[start : end + 1])
            for item in parsed:
                key = str(item["candidate_index"])
                out[key] = {
                    "semantic_reasonable": bool(item["semantic_reasonable"]),
                    "semantic_reason": str(item.get("reason", "")),
                }
        except json.JSONDecodeError:
            out = {}

    if len(out) == len(candidates):
        return out

    for idx, cand in enumerate(candidates, start=1):
        if str(idx) in out:
            continue
        single_prompt = textwrap.dedent(
            f"""
            You are reviewing one SVA candidate for semantic reasonableness.
            Case: {case_id}
            Specification:
            {spec}

            Candidate:
            {cand}

            Decide whether it is semantically reasonable:
            - true if it encodes a meaningful relation consistent with the spec
            - false if it is trivial, clearly unrelated, or obviously overfit to one observed literal

            Output JSON only:
            {{"candidate_index":{idx},"semantic_reasonable":true,"reason":"..."}}
            """
        ).strip()
        try:
            single_resp = post_ollama(single_prompt, temperature=0.0)
            obj_start = single_resp.find("{")
            obj_end = single_resp.rfind("}")
            if obj_start >= 0 and obj_end >= 0:
                item = json.loads(single_resp[obj_start : obj_end + 1])
                out[str(idx)] = {
                    "semantic_reasonable": bool(item["semantic_reasonable"]),
                    "semantic_reason": str(item.get("reason", "")),
                }
                continue
        except Exception:
            pass
        out[str(idx)] = heuristic_reason(cand)
    return out


def persist_progress(all_results: list[dict[str, Any]], prompt_rows: list[dict[str, Any]]) -> None:
    if all_results:
        pd.DataFrame(all_results).to_csv(
            OUTPUT_DIR / "trace_abstraction_results_raw.csv",
            index=False,
            encoding="utf-8-sig",
        )
    if prompt_rows:
        pd.DataFrame(prompt_rows).to_csv(
            OUTPUT_DIR / "trace_abstraction_prompts.csv",
            index=False,
            encoding="utf-8-sig",
        )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    case_filter = {
        item.strip()
        for item in os.environ.get("TRACEABS_CASE_FILTER", "").split(",")
        if item.strip()
    }
    variant_filter = {
        item.strip()
        for item in os.environ.get("TRACEABS_VARIANT_FILTER", "").split(",")
        if item.strip()
    }
    max_cases = int(os.environ.get("TRACEABS_MAX_CASES", "0") or "0")
    candidates_per_variant = int(os.environ.get("TRACEABS_CANDIDATES_PER_VARIANT", "5") or "5")

    selected_cases = [
        case_meta
        for case_meta in SELECTED_CASES
        if not case_filter or case_meta["case_id"] in case_filter
    ]
    if max_cases > 0:
        selected_cases = selected_cases[:max_cases]
    if not selected_cases:
        raise RuntimeError("No cases selected after TRACEABS_CASE_FILTER / TRACEABS_MAX_CASES.")

    bundles = [make_prompt_bundle(case_meta) for case_meta in selected_cases]
    write_text(
        OUTPUT_DIR / "selected_cases.json",
        json.dumps(
            [
                {
                    "case_id": bundle.case_id,
                    "selection_tags": bundle.selection_tags,
                    "selection_reason": bundle.selection_reason,
                    "spec": bundle.spec,
                    "raw_trace_input": bundle.raw_trace_input,
                    "normal_trace_summary": bundle.normal_trace_summary,
                    "abstracted_trace_summary": bundle.abstracted_trace_summary,
                }
                for bundle in bundles
            ],
            indent=2,
            ensure_ascii=False,
        ),
    )

    prompt_rows: list[dict[str, Any]] = []
    all_results: list[dict[str, Any]] = []
    results_csv = OUTPUT_DIR / "trace_abstraction_results_raw.csv"
    if results_csv.exists():
        existing_df = pd.read_csv(results_csv)
        if not existing_df.empty:
            all_results = existing_df.to_dict(orient="records")
    use_property = probe_property_support(bundles[0].case_id)

    for bundle in bundles:
        prompt_dir = OUTPUT_DIR / "prompts" / bundle.case_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_map = {
            "raw_trace": bundle.raw_prompt,
            "normal_trace_summary": bundle.normal_summary_prompt,
            "abstracted_trace_summary": bundle.abstracted_summary_prompt,
        }
        if variant_filter:
            prompt_map = {
                variant: prompt_text
                for variant, prompt_text in prompt_map.items()
                if variant in variant_filter
            }
        if not prompt_map:
            raise RuntimeError(
                f"{bundle.case_id}: no prompt variants selected after TRACEABS_VARIANT_FILTER."
            )
        write_text(prompt_dir / "raw_trace_prompt.txt", bundle.raw_prompt)
        write_text(prompt_dir / "normal_trace_summary_prompt.txt", bundle.normal_summary_prompt)
        write_text(prompt_dir / "abstracted_trace_summary_prompt.txt", bundle.abstracted_summary_prompt)

        signal_names = parse_allowed_signals(bundle.raw_prompt)

        for variant, prompt_text in prompt_map.items():
            existing_variant_rows = [
                row
                for row in all_results
                if row.get("case_id") == bundle.case_id and row.get("prompt_variant") == variant
            ]
            if len(existing_variant_rows) >= candidates_per_variant:
                prompt_rows.append(
                    {
                        "case_id": bundle.case_id,
                        "selection_tags": bundle.selection_tags,
                        "selection_reason": bundle.selection_reason,
                        "prompt_variant": variant,
                        "spec": bundle.spec,
                        "trace_input_text": {
                            "raw_trace": bundle.raw_trace_input,
                            "normal_trace_summary": bundle.normal_trace_summary,
                            "abstracted_trace_summary": bundle.abstracted_trace_summary,
                        }[variant],
                        "full_prompt_path": str(
                            (
                                prompt_dir
                                / {
                                    "raw_trace": "raw_trace_prompt.txt",
                                    "normal_trace_summary": "normal_trace_summary_prompt.txt",
                                    "abstracted_trace_summary": "abstracted_trace_summary_prompt.txt",
                                }[variant]
                            ).resolve()
                        ),
                    }
                )
                continue
            if 0 < len(existing_variant_rows) < candidates_per_variant:
                all_results = [
                    row
                    for row in all_results
                    if not (row.get("case_id") == bundle.case_id and row.get("prompt_variant") == variant)
                ]

            candidates, raw_responses = collect_five_candidates(
                prompt_text,
                case_id=bundle.case_id,
                variant=variant,
            )
            candidates = candidates[:candidates_per_variant]
            if len(candidates) < candidates_per_variant:
                raise RuntimeError(
                    f"{bundle.case_id}/{variant}: only collected {len(candidates)} candidates."
                )
            judge_map = judge_semantic_reasonable(
                spec=bundle.spec,
                case_id=bundle.case_id,
                candidates=candidates,
            )
            for candidate_idx, assertion_text in enumerate(candidates, start=1):
                runtime_dir = OUTPUT_DIR / "runtime" / bundle.case_id / variant / f"cand_{candidate_idx:02d}"
                eval_result = run_case_eval(
                    case_id=bundle.case_id,
                    assertion_text=assertion_text,
                    signal_names=signal_names,
                    use_property=use_property,
                    runtime_dir=runtime_dir,
                )
                judge_info = judge_map.get(
                    str(candidate_idx),
                    {"semantic_reasonable": False, "semantic_reason": "judge_missing"},
                )
                row = {
                    "case_id": bundle.case_id,
                    "selection_tags": bundle.selection_tags,
                    "prompt_variant": variant,
                    "candidate_index": candidate_idx,
                    "assertion_text": assertion_text,
                    "compile_ok": eval_result["compile_ok"],
                    "correct_pass": eval_result["correct_pass"],
                    "buggy_fail": eval_result["buggy_fail"],
                    "antecedent_hit": eval_result["antecedent_hit"],
                    "non_vacuous": eval_result["non_vacuous"],
                    "heldout_correct_pass": eval_result["heldout_correct_pass"],
                    "heldout_buggy_fail": eval_result["heldout_buggy_fail"],
                    "trace_overfit": eval_result["trace_overfit"],
                    "semantic_reasonable": judge_info["semantic_reasonable"],
                    "semantic_reason": judge_info["semantic_reason"],
                    "heldout_antecedent_hit": eval_result["heldout_antecedent_hit"],
                    "heldout_non_vacuous": eval_result["heldout_non_vacuous"],
                    "seen_good_ant_hits": eval_result["seen_good_ant_hits"],
                    "seen_bad_ant_hits": eval_result["seen_bad_ant_hits"],
                    "heldout_bad_ant_hits": eval_result["heldout_bad_ant_hits"],
                    "seen_good_fail_hits": eval_result["seen_good_fail_hits"],
                    "seen_bad_fail_hits": eval_result["seen_bad_fail_hits"],
                    "heldout_good_fail_hits": eval_result["heldout_good_fail_hits"],
                    "heldout_bad_fail_hits": eval_result["heldout_bad_fail_hits"],
                    "use_property_compile_mode": use_property,
                    "raw_generation_responses": "\n\n===== NEXT RESPONSE =====\n\n".join(raw_responses),
                }
                all_results.append(row)
                persist_progress(all_results, prompt_rows)

            prompt_rows.append(
                {
                    "case_id": bundle.case_id,
                    "selection_tags": bundle.selection_tags,
                    "selection_reason": bundle.selection_reason,
                    "prompt_variant": variant,
                    "spec": bundle.spec,
                    "trace_input_text": {
                        "raw_trace": bundle.raw_trace_input,
                        "normal_trace_summary": bundle.normal_trace_summary,
                        "abstracted_trace_summary": bundle.abstracted_trace_summary,
                    }[variant],
                    "full_prompt_path": str(
                        (
                            prompt_dir
                            / {
                                "raw_trace": "raw_trace_prompt.txt",
                                "normal_trace_summary": "normal_trace_summary_prompt.txt",
                                "abstracted_trace_summary": "abstracted_trace_summary_prompt.txt",
                            }[variant]
                        ).resolve()
                    ),
                }
            )
            persist_progress(all_results, prompt_rows)

    results_df = pd.DataFrame(all_results)
    results_df.to_csv(OUTPUT_DIR / "trace_abstraction_results_raw.csv", index=False, encoding="utf-8-sig")

    prompt_df = pd.DataFrame(prompt_rows)
    prompt_df.to_csv(OUTPUT_DIR / "trace_abstraction_prompts.csv", index=False, encoding="utf-8-sig")

    summary_rows = []
    for (case_id, variant), sub in results_df.groupby(["case_id", "prompt_variant"], dropna=False):
        summary_rows.append(
            {
                "case_id": case_id,
                "prompt_variant": variant,
                "candidate_count": int(len(sub)),
                "compile_ok_count": int(sub["compile_ok"].sum()),
                "correct_pass_count": int(sub["correct_pass"].sum()),
                "buggy_fail_count": int(sub["buggy_fail"].sum()),
                "antecedent_hit_count": int(sub["antecedent_hit"].sum()),
                "non_vacuous_count": int(sub["non_vacuous"].sum()),
                "heldout_correct_pass_count": int(sub["heldout_correct_pass"].sum()),
                "heldout_buggy_fail_count": int(sub["heldout_buggy_fail"].sum()),
                "trace_overfit_count": int(sub["trace_overfit"].sum()),
                "semantic_reasonable_count": int(sub["semantic_reasonable"].sum()),
            }
        )
    summary_df = pd.DataFrame(summary_rows).sort_values(["case_id", "prompt_variant"]).reset_index(drop=True)
    summary_df.to_csv(OUTPUT_DIR / "trace_abstraction_summary.csv", index=False, encoding="utf-8-sig")

    write_text(
        OUTPUT_DIR / "trace_abstraction_run_meta.json",
        json.dumps(
            {
                "model_name": MODEL_NAME,
                "ollama_url": OLLAMA_URL,
                "selected_case_count": len(bundles),
                "candidates_per_variant": candidates_per_variant,
                "prompt_variants": ["raw_trace", "normal_trace_summary", "abstracted_trace_summary"],
                "use_property_compile_mode": use_property,
                "case_filter": sorted(case_filter),
                "variant_filter": sorted(variant_filter),
                "max_cases": max_cases,
                "argv": sys.argv,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )

    print(OUTPUT_DIR / "trace_abstraction_results_raw.csv")
    print(OUTPUT_DIR / "trace_abstraction_summary.csv")


if __name__ == "__main__":
    main()
