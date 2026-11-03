from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import platform
import subprocess
import os
import re
import time
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/behavioral_preference_pilot_v1.json"
UNIVERSE = ROOT / "outputs/formal_group_heldout_splits_v1/parent_held_out.csv"
OUT = ROOT / "outputs/behavioral_preference_pilot_v1"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def stable(value: str) -> str:
    return hashlib.sha256(("behavioral-preference-pilot-v1\x1f" + value).encode()).hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def select_parents(rows: list[dict[str, str]], count: int) -> list[dict[str, str]]:
    train = {r["parent_bug_id"]: r for r in rows if r["split"] == "train"}
    groups: dict[str, list[dict[str, str]]] = {}
    for row in train.values():
        groups.setdefault(row["source_project"], []).append(row)
    for values in groups.values():
        values.sort(key=lambda r: stable(r["parent_bug_id"]))
    selected: list[dict[str, str]] = []
    while len(selected) < count:
        progressed = False
        for project in sorted(groups):
            if groups[project] and len(selected) < count:
                selected.append(groups[project].pop(0))
                progressed = True
        if not progressed:
            break
    if len(selected) != count:
        raise RuntimeError(f"Only {len(selected)} train parents available; need {count}")
    return selected


def freeze_tree(path: Path) -> dict:
    if path.is_file():
        return {
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "file_count": 1,
            "sha256": sha256(path),
        }
    files = sorted(p for p in path.rglob("*") if p.is_file())
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "file_count": len(files),
        "files": {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p) for p in files},
    }


def command_init() -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = load_rows(UNIVERSE)
    selected = select_parents(rows, cfg["train_parent_count"])
    projects = Counter(r["source_project"] for r in selected)
    bug_classes = Counter(r["bug_class"] for r in selected)
    bug_families = Counter(r["bug_family"] for r in selected)
    all_projects = sorted({r["source_project"] for r in rows})
    train_projects = sorted(projects)
    unseen_projects = sorted(set(all_projects) - set(train_projects))
    if len(projects) < cfg["minimum_projects"]:
        raise RuntimeError(f"Project coverage {len(projects)} < {cfg['minimum_projects']}")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "experiment_id": cfg["experiment_id"],
        "status": "pilot_initialized_generation_not_run",
        "config_path": str(CONFIG.relative_to(ROOT)).replace("\\", "/"),
        "config_sha256": sha256(CONFIG),
        "split_source": str(UNIVERSE.relative_to(ROOT)).replace("\\", "/"),
        "split_source_sha256": sha256(UNIVERSE),
        "parent_count": len(selected),
        "project_counts": dict(sorted(projects.items())),
        "bug_class_counts": dict(sorted(bug_classes.items())),
        "bug_family_count": len(bug_families),
        "observed_candidate_failure_modes": {
            "required_minimum": cfg["minimum_observed_candidate_failure_modes"],
            "allowed_vocabulary": cfg["candidate_failure_modes"],
            "status": "pending_candidate_validation"
        },
        "parents": selected,
        "frozen_asset_hashes": [freeze_tree(ROOT / p) for p in cfg["frozen_assets"]],
        "environment": {"platform": platform.platform(), "python": platform.python_version()},
        "joint_ood_feasibility_note": {
            "all_frozen_universe_projects": all_projects,
            "pilot_train_projects": train_projects,
            "unseen_projects_remaining": unseen_projects,
            "status": "not_a_go_no_go_condition",
            "reason": "Parent-, project-, and bug-family-OOD are evaluated as separate frozen dimensions. No joint three-way unseen requirement is imposed." ,
        },
    }
    dump(OUT / "pilot_manifest.json", manifest)
    with (OUT / "selected_train_parents.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(selected[0]))
        writer.writeheader(); writer.writerows(selected)
    evidence_schema = {
        "schema_version": 1,
        "required_candidate_fields": [
            "candidate_id", "parent_bug_id", "prompt_path", "prompt_sha256", "sva_path", "sva_sha256",
            "correct_rtl_sha256", "buggy_rtl_sha256", "mutation_diff_sha256", "stimulus_paths",
            "stimulus_sha256", "seed", "commands", "tool_versions", "raw_log_paths", "raw_log_sha256",
            "compile_ok", "signal_legal", "fixed_safe", "target_detect", "antecedent_hit",
            "non_vacuous", "fp_probe_ids", "tp_mutant_ids", "probe_policy", "wall_clock_seconds"
        ],
        "set_semantics": {"fp_probe_ids": "legal behaviors falsely rejected", "tp_mutant_ids": "same-family buggy mutants detected"},
    }
    dump(OUT / "candidate_evidence_schema.json", evidence_schema)
    dump(OUT / "run_state.json", {"stage": "initialized", "generation_complete": False, "validation_complete": False, "pairs_complete": False, "training_complete": False, "frozen_eval_complete": False})
    print(json.dumps({"out": str(OUT), "parents": len(selected), "projects": projects, "bug_classes": bug_classes, "bug_families": len(bug_families), "joint_ood_required": False}, ensure_ascii=False))


def read_jsonl(path: Path) -> list[dict]:
    result = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try: result.append(json.loads(line))
                except json.JSONDecodeError as e: raise RuntimeError(f"{path}:{n}: {e}") from e
    return result


def make_prompt(case_dir: Path, parent: dict, count: int) -> str:
    spec = (case_dir / "spec.md").read_text(encoding="utf-8")
    correct = (case_dir / "correct.v").read_text(encoding="utf-8")
    diff = (case_dir / "mutation.diff").read_text(encoding="utf-8")
    return f"""You are a formal verification engineer. Generate exactly {count} distinct, executable SystemVerilog assertions for the design below.

Output exactly {count} lines. Each line must begin with `assert property (` and end with `);`. Use the exact SystemVerilog spelling `disable iff` with a space; `disable_iff` is invalid and forbidden. Do not output markdown, numbering, prose, helper logic, assumptions, covers, or multiple properties per line.

Make the {count} properties structurally and behaviorally diverse, rather than changing only a delay literal. The properties must generalize across legal renaming, width/parameter changes, stalls/backpressure, request spacing, reset translations, same-root-cause mutants, and decoy traffic. Use only signals declared in the RTL. Avoid literal trace memorization and vacuous antecedents.

Parent: {parent['parent_bug_id']}
Project: {parent['source_project']}
Bug family: {parent['bug_family']}

Specification:
{spec}

Correct RTL:
{correct}

Bug mutation diff (for understanding only; do not mention it in output):
{diff}
"""


def extract_assertions(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip().strip("`")
        if line.startswith("assert property (") and line.endswith(");"):
            lines.append(line)
    return list(dict.fromkeys(lines))


def rtl_identifiers(rtl_text: str) -> list[str]:
    """Return declared RTL identifiers, excluding language keywords."""
    declared = re.findall(
        r"\b(?:input|output|inout|wire|reg|logic)\b(?:\s+(?:wire|reg|logic|signed|unsigned))*"
        r"(?:\s*\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)",
        re.sub(r"//.*?$|/\*.*?\*/", "", rtl_text, flags=re.MULTILINE | re.DOTALL),
    )
    return list(dict.fromkeys(declared))


def tb_visible_identifiers(tb_text: str) -> list[str]:
    """Return signals declared in the testbench module and therefore bindable as tb.signal."""
    clean = re.sub(r"//.*?$|/\*.*?\*/", "", tb_text, flags=re.MULTILINE | re.DOTALL)
    result: list[str] = []
    for match in re.finditer(r"\b(?:reg|wire|logic)\b([^;]*);", clean):
        declaration = re.sub(r"\[[^\]]+\]", " ", match.group(1))
        declaration = re.sub(r"\b(?:signed|unsigned)\b", " ", declaration)
        for item in declaration.split(","):
            name = item.split("=", 1)[0].strip()
            name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", name)
            if name_match: result.append(name_match.group(1))
    return list(dict.fromkeys(result))


def clock_and_reset(signals: list[str]) -> tuple[str | None, str | None]:
    clock = next((s for s in ("clk_i", "clk", "clock", "i_clk") if s in signals), None)
    reset = next((s for s in ("rst_ni", "rst_n", "reset_n", "aresetn", "rst", "reset") if s in signals), None)
    return clock, reset


def make_sequential_prompt(case_dir: Path, parent: dict, slot: int, attempt: int, signals: list[str]) -> str:
    spec_candidates = [case_dir / "spec.md", case_dir / "experiment/spec.txt"]
    spec_path = next((p for p in spec_candidates if p.exists()), None)
    if spec_path is None: raise RuntimeError(f"No specification source for {case_dir}")
    spec = spec_path.read_text(encoding="utf-8")
    diff_path = case_dir / "mutation.diff"
    if diff_path.exists():
        diff = diff_path.read_text(encoding="utf-8")
    else:
        correct_lines = (case_dir / "correct.v").read_text(encoding="utf-8").splitlines(keepends=True)
        buggy_lines = (case_dir / "buggy.v").read_text(encoding="utf-8").splitlines(keepends=True)
        diff = "".join(difflib.unified_diff(correct_lines, buggy_lines, fromfile="correct.v", tofile="buggy.v"))
    focuses = [
        "direct safety invariant", "same-cycle control priority", "next-cycle state effect",
        "legal idle or decoy traffic", "stall or backpressure behavior", "request spacing",
        "post-reset normal operation; do not reference any reset signal", "data-independent control behavior",
    ]
    return f"""Generate one behaviorally meaningful assertion semantic record for slot {slot}/8 (attempt {attempt}).
Return only the JSON object required by the supplied schema. Do not write SystemVerilog syntax.
The renderer will add the clock, reset, and assertion shell. Use only these declared identifiers: {', '.join(signals)}.
Allowed expression syntax: declared identifiers, bit/part selects, parentheses, !, &&, ||, ==, !=, ===, !==, <, <=, >, >=, and sized constants.
Forbidden: temporal operators, ##, nextcycle, functions, $past, helper variables, prose, and undeclared identifiers.
Make this candidate distinct from simple delay or constant variations. Focus: {focuses[slot - 1]}.

Parent: {parent['parent_bug_id']}
Project: {parent['source_project']}
Bug family: {parent['bug_family']}
Specification:
{spec}
Mutation diff for semantic context:
{diff}
"""


def command_prepare_sequential(limit: int, model: str, attempts_per_slot: int) -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    parents = load_rows(OUT / "selected_train_parents.csv")[:limit or None]
    root = OUT / "sequential_generation_v2"
    schema = {
        "type": "object",
        "properties": {
            "antecedent": {"type": "string"},
            "implication": {"type": "string", "enum": ["|->", "|=>"]},
            "consequent": {"type": "string"},
        },
        "required": ["antecedent", "implication", "consequent"],
        "additionalProperties": False,
    }
    records = []
    for parent in parents:
        case_dir = ROOT / parent["dataset_root"] / parent["case_id"]
        signals = tb_visible_identifiers((case_dir / "tb.v").read_text(encoding="utf-8"))
        clock_and_reset(signals)
        for slot in range(1, 9):
            for attempt in range(1, attempts_per_slot + 1):
                attempt_dir = root / parent["parent_bug_id"] / f"slot_{slot:02d}" / f"attempt_{attempt:02d}"
                attempt_dir.mkdir(parents=True, exist_ok=True)
                prompt = make_sequential_prompt(case_dir, parent, slot, attempt, signals)
                prompt_path = attempt_dir / "prompt.txt"
                request = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "Return only the requested JSON semantic record."},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False, "think": False, "format": schema,
                    "options": {
                        "temperature": cfg["candidate_generation"]["temperature"],
                        "num_predict": cfg["candidate_generation"]["max_new_tokens"],
                        "seed": cfg["candidate_generation"]["seed"], "num_ctx": 8192,
                    },
                }
                request_path = attempt_dir / "request.json"
                # Never overwrite an issued request: failed and rejected attempts
                # are immutable experimental evidence.
                if not request_path.exists():
                    prompt_path.write_text(prompt, encoding="utf-8")
                    dump(request_path, request)
                records.append({
                    "parent_bug_id": parent["parent_bug_id"], "slot": slot, "attempt": attempt,
                    "signals": signals, "prompt_sha256": sha256(prompt_path),
                    "request_sha256": sha256(request_path),
                    "request_path": str(request_path.relative_to(ROOT)).replace("\\", "/"),
                })
    dump(root / "request_index.json", {"protocol_version": "sequential_structured_v2_visible_compile_gate", "records": records})
    print(json.dumps({"parents": len(parents), "requests": len(records), "attempts_per_slot": attempts_per_slot}))


def validate_expression(expr: str, signals: list[str], reset: str | None) -> tuple[bool, str]:
    if not isinstance(expr, str) or not expr.strip():
        return False, "empty_expression"
    if re.search(r"(?:##|\$|nextcycle|\b(?:posedge|negedge|disable|iff|property)\b)", expr, re.IGNORECASE):
        return False, "forbidden_token"
    if not re.fullmatch(r"[A-Za-z0-9_\s\[\]():?'!&|=<>+\-*/.]+", expr):
        return False, "unsupported_character"
    without_constants = re.sub(r"\b\d+'[sS]?[bBoOdDhH][0-9a-fA-FxXzZ?_]+\b", "0", expr)
    identifiers = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", without_constants))
    undeclared = identifiers - set(signals)
    if undeclared:
        return False, "undeclared:" + ",".join(sorted(undeclared))
    if reset and reset in identifiers:
        return False, "reset_in_semantic_expression"
    return True, "ok"


def render_assertion(clock: str | None, reset: str | None, semantic: dict) -> str:
    disable = ""
    if reset:
        reset_active = f"!{reset}" if reset.endswith(("_n", "_ni", "n")) else reset
        disable = f" disable iff ({reset_active})"
    event = f"posedge {clock}" if clock else "*"
    return f"assert property (@({event}){disable} ({semantic['antecedent']}) {semantic['implication']} ({semantic['consequent']}));"


def command_ingest_sequential(limit: int) -> None:
    def evaluate(case_dir: Path, signals: list[str], clock: str | None, reset: str | None, semantic: dict, runtime_dir: Path) -> dict:
        tb_text = (case_dir / "tb.v").read_text(encoding="utf-8")
        module_match = re.search(r"\bmodule\s+([A-Za-z_][A-Za-z0-9_]*)", tb_text)
        if not module_match: raise RuntimeError("testbench module not found")
        tb_module = module_match.group(1)
        def qualify(expr: str) -> str:
            result = expr
            for signal in sorted(signals, key=len, reverse=True):
                result = re.sub(rf"\b{re.escape(signal)}\b", f"{tb_module}.{signal}", result)
            return result
        ant, cons = qualify(semantic["antecedent"]), qualify(semantic["consequent"])
        reset_active = "1'b0" if not reset else (f"!{tb_module}.{reset}" if reset.endswith(("_n", "_ni", "n")) else f"{tb_module}.{reset}")
        fail_test = f"ant_d && !({cons})" if clock and semantic["implication"] == "|=>" else f"({ant}) && !({cons})"
        monitor_event = f"posedge {tb_module}.{clock}" if clock else "*"
        checker = f"""module behavioral_preference_checker;
integer ant_hits = 0; integer fail_hits = 0; reg ant_d = 0;
always @({monitor_event}) begin
  if ({reset_active}) ant_d <= 0;
  else begin
    if ({ant}) ant_hits = ant_hits + 1;
    if ({fail_test}) fail_hits = fail_hits + 1;
    ant_d <= ({ant});
  end
end
final $display("BP_METRIC ant_hits=%0d fail_hits=%0d", ant_hits, fail_hits);
endmodule
"""
        checker_path = runtime_dir / "checker.sv"
        checker_path.write_text(checker, encoding="utf-8")
        results = {}
        for rtl_name in ("correct.v", "buggy.v"):
            tag = rtl_name.removesuffix(".v")
            simv = runtime_dir / f"{tag}.out"
            compile_cmd = ["iverilog", "-g2012", "-I", str(case_dir), "-I", str(ROOT / "external/common_cells/include"), "-o", str(simv), str(case_dir / rtl_name), str(case_dir / "tb.v"), str(checker_path)]
            started = time.perf_counter()
            cp = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=180)
            compile_seconds = time.perf_counter() - started
            sp = None
            if cp.returncode == 0:
                sp = subprocess.run(["vvp", str(simv)], capture_output=True, text=True, timeout=180)
            combined = "" if sp is None else sp.stdout + "\n" + sp.stderr
            metric = re.search(r"BP_METRIC ant_hits=(\d+) fail_hits=(\d+)", combined)
            results[tag] = {"compile_ok": cp.returncode == 0, "compile_command": compile_cmd, "compile_stdout": cp.stdout, "compile_stderr": cp.stderr, "compile_seconds": compile_seconds, "sim_returncode": None if sp is None else sp.returncode, "sim_stdout": "" if sp is None else sp.stdout, "sim_stderr": "" if sp is None else sp.stderr, "ant_hits": int(metric.group(1)) if metric else 0, "fail_hits": int(metric.group(2)) if metric else 0}
        return {"compile_ok": all(x["compile_ok"] for x in results.values()), "correct_pass": results["correct"]["fail_hits"] == 0, "buggy_fail": results["buggy"]["fail_hits"] > 0, "antecedent_hit": results["buggy"]["ant_hits"] > 0, "non_vacuous": results["buggy"]["ant_hits"] > 0, "runs": results}

    parents = load_rows(OUT / "selected_train_parents.csv")[:limit or None]
    seq_root = OUT / "sequential_generation_v2"
    audit_rows = []
    accepted_rows = []
    for parent in parents:
        case_dir = ROOT / parent["dataset_root"] / parent["case_id"]
        signals = tb_visible_identifiers((case_dir / "tb.v").read_text(encoding="utf-8"))
        clock, reset = clock_and_reset(signals)
        used: set[str] = set()
        for slot in range(1, 9):
            accepted = False
            slot_dir = seq_root / parent["parent_bug_id"] / f"slot_{slot:02d}"
            for attempt_dir in sorted(slot_dir.glob("attempt_*")):
                response_path = attempt_dir / "raw_response.json"
                row = {"parent_bug_id": parent["parent_bug_id"], "slot": slot, "attempt": int(attempt_dir.name.split("_")[-1]), "response_path": str(response_path.relative_to(ROOT)).replace("\\", "/")}
                if not response_path.exists():
                    row.update({"accepted": False, "reason": "response_missing"}); audit_rows.append(row); continue
                try:
                    envelope = json.loads(response_path.read_text(encoding="utf-8"))
                    semantic = json.loads(envelope["message"]["content"])
                except Exception as exc:
                    row.update({"accepted": False, "reason": "json_invalid", "error": repr(exc)}); audit_rows.append(row); continue
                if semantic.get("implication") not in ("|->", "|=>"):
                    row.update({"accepted": False, "reason": "invalid_implication", "semantic": semantic}); audit_rows.append(row); continue
                ant_ok, ant_reason = validate_expression(semantic.get("antecedent"), signals, reset)
                cons_ok, cons_reason = validate_expression(semantic.get("consequent"), signals, reset)
                assertion = render_assertion(clock, reset, semantic) if ant_ok and cons_ok else ""
                canonical = re.sub(r"\s+", "", assertion)
                reason = "ok" if ant_ok and cons_ok else (ant_reason if not ant_ok else cons_reason)
                if canonical in used: reason = "duplicate_rendered_sva"
                if reason != "ok":
                    row.update({"accepted": False, "reason": reason, "semantic": semantic}); audit_rows.append(row); continue
                candidate_id = f"{parent['parent_bug_id']}__seq_{slot:02d}"
                runtime_dir = seq_root / parent["parent_bug_id"] / "runtime" / f"candidate_{slot:02d}_attempt_{row['attempt']:02d}"
                runtime_dir.mkdir(parents=True, exist_ok=True)
                try:
                    result = evaluate(case_dir, signals, clock, reset, semantic, runtime_dir)
                except Exception as exc:
                    result = {"compile_ok": False, "exception": repr(exc)}
                if not result.get("compile_ok"):
                    row.update({"accepted": False, "reason": "compile_fail", "semantic": semantic, "assertion": assertion, "evaluation": result})
                    audit_rows.append(row); continue
                candidate_path = seq_root / parent["parent_bug_id"] / f"candidate_{slot:02d}.sva"
                candidate_path.write_text(assertion + "\n", encoding="utf-8")
                row.update({"accepted": True, "reason": "ok", "candidate_id": candidate_id, "semantic": semantic, "assertion": assertion, "candidate_sha256": sha256(candidate_path), "evaluation": result})
                audit_rows.append(row); accepted_rows.append(row); used.add(canonical); accepted = True; break
            if not accepted:
                audit_rows.append({"parent_bug_id": parent["parent_bug_id"], "slot": slot, "accepted": False, "reason": "slot_exhausted"})
    audit_path = seq_root / "ingestion_audit.jsonl"
    audit_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in audit_rows), encoding="utf-8")
    missing = [{"parent_bug_id": p["parent_bug_id"], "slot": slot} for p in parents for slot in range(1, 9) if not any(r["parent_bug_id"] == p["parent_bug_id"] and r["slot"] == slot for r in accepted_rows)]
    dump(seq_root / "accepted_index.json", {"protocol_version": "sequential_structured_v2_visible_compile_gate", "accepted_count": len(accepted_rows), "target_count": 8 * len(parents), "pass": len(accepted_rows) == 8 * len(parents), "records": accepted_rows, "audit_sha256": sha256(audit_path)})
    dump(seq_root / "missing_slots.json", {"protocol_version": "sequential_structured_v2_visible_compile_gate", "missing_count": len(missing), "slots": missing})
    print(json.dumps({"parents": len(parents), "accepted": len(accepted_rows), "target": 8 * len(parents), "compile_ok": sum(bool(r["evaluation"].get("compile_ok")) for r in accepted_rows)}))


def command_freeze_sequential() -> None:
    seq_root = OUT / "sequential_generation"
    accepted = json.loads((seq_root / "accepted_index.json").read_text(encoding="utf-8"))
    if not accepted.get("pass") or accepted.get("accepted_count") != 8:
        raise RuntimeError("One-parent gate is not 8/8; refusing to freeze protocol")
    if not all(r.get("evaluation", {}).get("compile_ok") and r.get("evaluation", {}).get("non_vacuous") for r in accepted["records"]):
        raise RuntimeError("Accepted candidates did not all pass compile/non-vacuity gate")
    manifest = {
        "protocol_version": "sequential_structured_v1",
        "status": "frozen_after_one_parent_8_of_8_gate",
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": "qwen3-8b-pilot:q4_K_M",
        "model_digest": "033521cec2c1f3afcf19a2ced270f4fdea6390582f40e350c10ffd965e6f3a6c",
        "generation": {"temperature": 0.7, "num_predict": 512, "seed": 20260815, "num_ctx": 8192, "think": False, "candidates_per_parent": 8, "maximum_attempts_per_slot": 4},
        "sampling_event": "posedge detected clock; @(*) for clockless combinational RTL",
        "selection": "slot order 1..8; lowest attempt passing syntax, declared-signal, reset-exclusion, and global exact-render uniqueness; evaluation outcomes never select candidates",
        "native_sva_compile_note": "No Slang/Verilator installed. strict renderer/parser plus Icarus compilation of the identical semantic expressions is recorded separately; do not label this native concurrent-SVA compiler coverage.",
        "hashes": {
            "pilot_source_sha256": sha256(ROOT / "src/behavioral_preference_pilot.py"),
            "runner_sha256": sha256(ROOT / "scripts/run_sequential_ollama_requests.ps1"),
            "config_sha256": sha256(CONFIG),
            "prepared_request_index_sha256": sha256(seq_root / "request_index.json"),
            "one_parent_accepted_index_sha256": sha256(seq_root / "accepted_index.json"),
            "one_parent_ingestion_audit_sha256": sha256(seq_root / "ingestion_audit.jsonl"),
        },
        "one_parent_gate": {
            "parent_bug_id": accepted["records"][0]["parent_bug_id"], "accepted": 8,
            "compile_ok": sum(bool(r["evaluation"]["compile_ok"]) for r in accepted["records"]),
            "fixed_safe": sum(bool(r["evaluation"]["correct_pass"]) for r in accepted["records"]),
            "target_detect": sum(bool(r["evaluation"]["buggy_fail"]) for r in accepted["records"]),
            "non_vacuous": sum(bool(r["evaluation"]["non_vacuous"]) for r in accepted["records"]),
            "note": "fixed-safe and target-detect are measured outcomes, never candidate-selection gates",
        },
        "prepared_expansion": {"parent_count": 30, "slot_count_per_parent": 8, "maximum_attempts_per_slot": 4, "request_count": 960},
    }
    dump(OUT / "sequential_protocol_frozen.json", manifest)
    print(json.dumps({"status": manifest["status"], "manifest": str((OUT / "sequential_protocol_frozen.json").relative_to(ROOT))}))


def command_publish_v2() -> None:
    root = OUT / "sequential_generation_v2"
    accepted = json.loads((root / "accepted_index.json").read_text(encoding="utf-8"))
    missing = json.loads((root / "missing_slots.json").read_text(encoding="utf-8"))
    manifest = {
        "protocol_version": "sequential_structured_v2_visible_compile_gate",
        "status": "frozen_before_attempt_2_supplement",
        "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "supersedes": "sequential_structured_v1",
        "v1_evidence_archive": "outputs/behavioral_preference_pilot_v1/protocol_v1_archive",
        "corrections": [
            "allowed identifiers are declarations visible at the testbench top level",
            "Icarus include path contains external/common_cells/include",
            "a candidate is accepted only after correct and buggy monitor compilation succeeds",
            "fixed-safe, target-detect, and non-vacuity remain measured outcomes and do not select candidates",
        ],
        "generation_unchanged": {"model": "qwen3-8b-pilot:q4_K_M", "temperature": 0.7, "num_predict": 512, "seed": 20260815, "num_ctx": 8192, "think": False, "maximum_attempts_per_slot": 4},
        "attempt_1_reingest": {"target_slots": 240, "accepted_compile_legal": accepted["accepted_count"], "missing_slots": missing["missing_count"]},
        "supplement_rule": "For attempts 2 through 4, issue requests only for slots listed by the immediately preceding v2 missing_slots.json.",
        "hashes": {
            "pilot_source_sha256": sha256(ROOT / "src/behavioral_preference_pilot.py"),
            "runner_sha256": sha256(ROOT / "scripts/run_sequential_ollama_requests.ps1"),
            "request_index_sha256": sha256(root / "request_index.json"),
            "attempt1_accepted_index_sha256": sha256(root / "accepted_index.json"),
            "attempt1_audit_sha256": sha256(root / "ingestion_audit.jsonl"),
            "attempt1_missing_slots_sha256": sha256(root / "missing_slots.json"),
        },
    }
    dump(OUT / "sequential_protocol_v2_frozen.json", manifest)
    print(json.dumps({"status": manifest["status"], "accepted": accepted["accepted_count"], "missing": missing["missing_count"]}))


def command_generate(limit: int, base_url: str, model: str, backend: str, prepare_only: bool = False) -> None:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    parents = load_rows(OUT / "selected_train_parents.csv")[:limit or None]
    key = ""
    if backend == "openai":
        key = os.environ.get("QWEN_API_KEY", "").strip()
        if not key:
            key_file = ROOT / ".secrets/qwen_api_key.txt"
            if key_file.exists(): key = key_file.read_text(encoding="utf-8").strip()
        if not key: raise RuntimeError("QWEN_API_KEY is unavailable")
    gen_root = OUT / "generation"
    gen_root.mkdir(parents=True, exist_ok=True)
    index = []
    for parent in parents:
        case_dir = ROOT / parent["dataset_root"] / parent["case_id"]
        target = cfg["candidates_per_parent"]
        prompt = make_prompt(case_dir, parent, target)
        parent_dir = gen_root / parent["parent_bug_id"]
        parent_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = parent_dir / "prompt.txt"; prompt_path.write_text(prompt, encoding="utf-8")
        messages = [{"role": "system", "content": "Return only executable SVA assertion lines."}, {"role": "user", "content": prompt}]
        if backend == "ollama":
            request_public = {
                "model": model, "messages": messages, "stream": False, "think": False,
                "options": {
                    "temperature": cfg["candidate_generation"]["temperature"],
                    "num_predict": cfg["candidate_generation"]["max_new_tokens"],
                    "seed": cfg["candidate_generation"]["seed"], "num_ctx": 8192,
                },
            }
        else:
            request_public = {
                "model": model, "messages": messages,
                "temperature": cfg["candidate_generation"]["temperature"],
                "max_tokens": cfg["candidate_generation"]["max_new_tokens"],
                "seed": cfg["candidate_generation"]["seed"],
            }
        dump(parent_dir / "request.json", request_public)
        if prepare_only:
            index.append({"parent_bug_id": parent["parent_bug_id"], "backend": backend, "model": model, "target_count": target, "prompt_sha256": sha256(prompt_path), "request_sha256": sha256(parent_dir / "request.json"), "status": "request_prepared"})
            continue
        headers = {"Content-Type": "application/json"}
        if backend == "openai": headers["Authorization"] = f"Bearer {key}"
        req = urllib.request.Request(base_url, data=json.dumps(request_public).encode(), headers=headers)
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                raw = response.read()
        except Exception as exc:
            (parent_dir / "error.log").write_text(repr(exc) + "\n", encoding="utf-8")
            raise
        elapsed = time.time() - started
        (parent_dir / "raw_response.json").write_bytes(raw)
        payload = json.loads(raw)
        content = payload["message"]["content"] if backend == "ollama" else payload["choices"][0]["message"]["content"]
        assertions = extract_assertions(content)
        (parent_dir / "candidates.sva").write_text("\n".join(assertions) + "\n", encoding="utf-8")
        record = {"parent_bug_id": parent["parent_bug_id"], "backend": backend, "model": model, "candidate_count": len(assertions), "target_count": target, "temperature": cfg["candidate_generation"]["temperature"], "max_tokens": cfg["candidate_generation"]["max_new_tokens"], "seed": cfg["candidate_generation"]["seed"], "prompt_sha256": sha256(prompt_path), "response_sha256": sha256(parent_dir / "raw_response.json"), "sva_sha256": sha256(parent_dir / "candidates.sva"), "wall_clock_seconds": elapsed, "pass": len(assertions) == target}
        dump(parent_dir / "generation_audit.json", record); index.append(record)
    passed = None if prepare_only else all(r["pass"] for r in index)
    dump(OUT / "generation_index.json", {"backend": backend, "model": model, "requested_parent_count": len(parents), "prepare_only": prepare_only, "records": index, "pass": passed})
    print(json.dumps({"parents": len(index), "prepare_only": prepare_only, "candidate_counts": [] if prepare_only else [r["candidate_count"] for r in index], "pass": passed}))


def command_pairs(evidence: Path) -> None:
    schema = json.loads((OUT / "candidate_evidence_schema.json").read_text(encoding="utf-8"))
    rows = read_jsonl(evidence)
    required = set(schema["required_candidate_fields"])
    for row in rows:
        missing = required - set(row)
        if missing: raise RuntimeError(f"{row.get('candidate_id', '<unknown>')} missing {sorted(missing)}")
    pairs = []
    by_parent: dict[str, list[dict]] = {}
    for row in rows: by_parent.setdefault(row["parent_bug_id"], []).append(row)
    for parent, candidates in sorted(by_parent.items()):
        for a in candidates:
            for b in candidates:
                if a["candidate_id"] == b["candidate_id"]: continue
                fp_a, fp_b = set(a["fp_probe_ids"]), set(b["fp_probe_ids"])
                tp_a, tp_b = set(a["tp_mutant_ids"]), set(b["tp_mutant_ids"])
                if fp_a <= fp_b and tp_a >= tp_b and (fp_a < fp_b or tp_a > tp_b):
                    pairs.append({"pair_id": stable(parent + "\x1f" + a["candidate_id"] + "\x1f" + b["candidate_id"])[:24], "parent_bug_id": parent, "chosen_id": a["candidate_id"], "rejected_id": b["candidate_id"], "chosen_fp": sorted(fp_a), "rejected_fp": sorted(fp_b), "chosen_tp": sorted(tp_a), "rejected_tp": sorted(tp_b)})
    out = OUT / "dominance_pairs.jsonl"
    out.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pairs), encoding="utf-8")
    dump(OUT / "dominance_pair_audit.json", {"candidate_count": len(rows), "parent_count": len(by_parent), "pair_count": len(pairs), "minimum_required": 300, "pass": len(pairs) >= 300, "pair_file_sha256": sha256(out)})
    print(json.dumps({"pairs": len(pairs), "pass": len(pairs) >= 300}))


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    g = sub.add_parser("generate")
    g.add_argument("--limit", type=int, default=0)
    g.add_argument("--base-url", default="https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    g.add_argument("--model", default="qwen3-8b")
    g.add_argument("--backend", choices=["openai", "ollama"], default="openai")
    g.add_argument("--prepare-only", action="store_true")
    p = sub.add_parser("build-pairs"); p.add_argument("--evidence", type=Path, required=True)
    q = sub.add_parser("prepare-sequential")
    q.add_argument("--limit", type=int, default=1)
    q.add_argument("--model", default="qwen3-8b-pilot:q4_K_M")
    q.add_argument("--attempts-per-slot", type=int, default=3)
    i = sub.add_parser("ingest-sequential")
    i.add_argument("--limit", type=int, default=1)
    sub.add_parser("freeze-sequential")
    sub.add_parser("publish-v2")
    args = ap.parse_args()
    if args.command == "init": command_init()
    elif args.command == "generate": command_generate(args.limit, args.base_url, args.model, args.backend, args.prepare_only)
    elif args.command == "build-pairs": command_pairs(args.evidence.resolve())
    elif args.command == "prepare-sequential": command_prepare_sequential(args.limit, args.model, args.attempts_per_slot)
    elif args.command == "ingest-sequential": command_ingest_sequential(args.limit)
    elif args.command == "freeze-sequential": command_freeze_sequential()
    elif args.command == "publish-v2": command_publish_v2()


if __name__ == "__main__": main()
