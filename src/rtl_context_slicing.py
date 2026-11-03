from __future__ import annotations

import re
from typing import Any


def normalize_signal(signal: str) -> str:
    return str(signal).split("[", 1)[0].strip()


def extract_module_blocks(rtl_text: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?ms)^module\s+([A-Za-z_][A-Za-z0-9_]*)\b.*?^endmodule\b")
    return [(match.group(1), match.group(0).strip()) for match in pattern.finditer(rtl_text)]


def extract_module_signature(module_block: str) -> str:
    collected = []
    for line in module_block.splitlines():
        if not collected and not line.strip().startswith("module "):
            continue
        collected.append(line.rstrip())
        if line.strip().endswith(");"):
            break
    return "\n".join(collected).strip()


def strip_comments(line: str, in_block_comment: bool) -> tuple[str, bool]:
    out, i = [], 0
    while i < len(line):
        if in_block_comment:
            end = line.find("*/", i)
            if end < 0:
                return "".join(out), True
            i, in_block_comment = end + 2, False
        elif line.startswith("//", i):
            break
        elif line.startswith("/*", i):
            i, in_block_comment = i + 2, True
        else:
            out.append(line[i])
            i += 1
    return "".join(out), in_block_comment


def extract_always_assign_blocks(module_text: str) -> list[dict[str, Any]]:
    lines = module_text.splitlines()
    clean_lines, in_comment = [], False
    for line in lines:
        clean, in_comment = strip_comments(line, in_comment)
        clean_lines.append(clean)
    blocks, i = [], 0
    start_re = re.compile(r"^\s*(always(?:_ff|_comb|_latch)?\b|assign\b)")
    token_re = re.compile(r"\b(begin|end)\b")
    while i < len(lines):
        match = start_re.match(clean_lines[i])
        if not match:
            i += 1
            continue
        kind, start = ("assign" if match.group(1) == "assign" else "always"), i
        if kind == "assign":
            while i < len(lines) and ";" not in clean_lines[i]:
                i += 1
            end = min(i + 1, len(lines))
            i = end
        else:
            depth, saw_begin = 0, False
            while i < len(lines):
                for token in token_re.findall(clean_lines[i]):
                    if token == "begin":
                        depth, saw_begin = depth + 1, True
                    elif saw_begin:
                        depth -= 1
                if saw_begin and depth <= 0:
                    i += 1
                    break
                if not saw_begin and ";" in clean_lines[i] and i > start:
                    i += 1
                    break
                i += 1
            end = min(i, len(lines))
        blocks.append({"kind": kind, "start_line": start + 1, "end_line": end,
                       "text": "\n".join(lines[start:end]).strip()})
    return blocks


def extract_automatic_small_slice(full_rtl: str, relevant_signals: list[str], *, max_blocks: int = 12) -> tuple[str, dict[str, Any]]:
    modules = extract_module_blocks(full_rtl)
    source_module = modules[-1][1] if modules else full_rtl
    signals = sorted({normalize_signal(sig) for sig in relevant_signals if str(sig).strip()})
    all_blocks = extract_always_assign_blocks(source_module)
    selected = []
    for block in all_blocks:
        touched = [sig for sig in signals if re.search(rf"\b{re.escape(sig)}\b", block["text"])]
        if touched:
            selected.append({**block, "matched_signals": touched})
    selected = selected[:max_blocks]
    # Preserve the real compilation context (declarations, localparams,
    # generate/ifdef structure and module signature) while masking every
    # unselected procedural/continuous block.  Copying blocks into a synthetic
    # module loses generate variables and internal declarations and therefore
    # cannot be independently elaborated.
    selected_spans = {(block["start_line"], block["end_line"]) for block in selected}
    selected_by_span = {
        (block["start_line"], block["end_line"]): block for block in selected
    }
    lines = source_module.splitlines()
    masked = list(lines)
    for block in all_blocks:
        span = (block["start_line"], block["end_line"])
        start = block["start_line"] - 1
        end = block["end_line"]
        if span in selected_spans:
            selected_block = selected_by_span[span]
            masked[start] = (
                f"// AUTO-SLICE KEEP {block['kind']} lines {block['start_line']}-{block['end_line']} "
                f"signals={','.join(selected_block['matched_signals'])}\n" + masked[start]
            )
        else:
            masked[start] = (
                f"// AUTO-SLICE OMIT {block['kind']} lines {block['start_line']}-{block['end_line']}"
            )
            for index in range(start + 1, end):
                masked[index] = ""
    slice_text = "\n".join(masked).strip()
    metadata = {
        "policy": "relevant_signal_masked_module_v2",
        "input_signal_count": len(signals),
        "available_block_count": len(all_blocks),
        "selected_block_count": len(selected),
        "omitted_block_count": len(all_blocks) - len(selected),
        "preserves_module_declarations": True,
        "preserves_generate_context": True,
        "selected_blocks": [{k: block[k] for k in ["kind", "start_line", "end_line", "matched_signals"]}
                            for block in selected],
        "uses_golden_sva": False,
        "uses_trace": False,
        "uses_mutation_diff": False,
    }
    return slice_text, metadata
