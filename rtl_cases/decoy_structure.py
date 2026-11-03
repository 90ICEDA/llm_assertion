from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional


DECOY_CSV_FILES = [
    "waveform_good_decoy.csv",
    "waveform_bad_decoy.csv",
]

DECOY_VCD_FILES = [
    "waveform_good_decoy.vcd",
    "waveform_bad_decoy.vcd",
]


def load_manifest(root: Path) -> List[Dict[str, object]]:
    return json.loads((root / "case_manifest.json").read_text(encoding="utf-8"))["cases"]


def write_manifest(root: Path, cases: List[Dict[str, object]]) -> None:
    manifest = {"cases": cases}
    (root / "case_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def case_id(case_name: str) -> str:
    return case_name.split("_", 1)[0]


def cluster_key(entry: Dict[str, object]) -> str:
    return str(entry.get("seed_case_name") or entry["name"])


def build_cluster_members(entries: List[Dict[str, object]]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for entry in entries:
        grouped.setdefault(cluster_key(entry), []).append(str(entry["name"]))

    ordered: Dict[str, List[str]] = {}
    for seed_name, members in grouped.items():
        variants = sorted(name for name in members if name != seed_name)
        ordered[seed_name] = ([seed_name] if seed_name in members else []) + variants
    return ordered


def choose_decoy_donor(case_name: str, members: List[str]) -> Optional[str]:
    if len(members) <= 1:
        return None
    if case_name not in members:
        return members[0]
    idx = members.index(case_name)
    return members[(idx + 1) % len(members)]


def rewrite_dumpfile_and_add_idle(tb_text: str, current_case_id: str, source_case: str) -> str:
    updated = re.sub(
        r'\$dumpfile\(".*?"\);',
        f'$dumpfile("{current_case_id}_decoy.vcd");',
        tb_text,
        count=1,
    )
    if "AF_DECOY_IDLE" not in updated:
        updated = re.sub(
            r"(\brst_n\s*=\s*1'b1\s*;\s*)",
            r"\1\n    // AF_DECOY_IDLE\n    @(posedge clk);",
            updated,
            count=1,
        )
    if not updated.startswith("// AF_DECOY_SOURCE:"):
        updated = f"// AF_DECOY_SOURCE: {source_case}\n{updated}"
    return updated


def default_overfit_lure(entry: Dict[str, object], source_label: str) -> str:
    bug_class = str(entry.get("bug_class", "")).strip()
    bug_type = str(entry.get("bug_type", "")).strip()
    if bug_class == "combination_same_cycle":
        return (
            f"Decoy trace replays the same same-cycle bug family for {bug_type} through "
            f"{source_label}, but changes surrounding legal context or idle spacing so literal pinning "
            "to the seen trace should fail."
        )
    if bug_class == "temporal_cross_cycle":
        return (
            f"Decoy trace preserves the same temporal trigger for {bug_type} through {source_label}, "
            "but shifts surrounding prelude timing so the assertion must generalize beyond the seen trace."
        )
    return (
        f"Decoy trace preserves the same bug-triggering relation for {bug_type} through {source_label}, "
        "but changes non-essential trace detail so literal memorization is penalized."
    )


def append_decoy_notes(case_dir: Path, lure: str, source_label: str) -> None:
    notes_path = case_dir / "STIMULUS_NOTES.md"
    if not notes_path.exists():
        return
    text = notes_path.read_text(encoding="utf-8")
    if "## Overfit Decoy" in text:
        return
    block = (
        "\n\n## Overfit Decoy\n\n"
        f"- Source: `{source_label}`\n"
        f"- Lure: {lure}\n"
        "- Files: `tb_decoy.v`, `waveform_good_decoy.csv`, `waveform_bad_decoy.csv`\n"
    )
    notes_path.write_text(text.rstrip() + block + "\n", encoding="utf-8", newline="\n")


def copy_if_exists(src: Path, dst: Path) -> bool:
    if not src.exists():
        return False
    shutil.copy2(src, dst)
    return True


def select_source_files(root: Path, case_name: str, donor_name: Optional[str]) -> Dict[str, object]:
    case_dir = root / case_name
    holdout_tb = case_dir / "tb_holdout.v"
    holdout_good = case_dir / "waveform_good_holdout.csv"
    holdout_bad = case_dir / "waveform_bad_holdout.csv"
    holdout_good_vcd = case_dir / "waveform_good_holdout.vcd"
    holdout_bad_vcd = case_dir / "waveform_bad_holdout.vcd"
    if holdout_tb.exists() and holdout_good.exists() and holdout_bad.exists():
        return {
            "source_case": case_name,
            "source_label": "self held-out trace with a decoy idle perturbation",
            "tb_path": holdout_tb,
            "good_csv": holdout_good,
            "bad_csv": holdout_bad,
            "good_vcd": holdout_good_vcd,
            "bad_vcd": holdout_bad_vcd,
            "strategy": "self_holdout_bootstrap",
        }

    primary = {
        "source_case": case_name,
        "source_label": "self primary trace with a decoy idle perturbation",
        "tb_path": case_dir / "tb.v",
        "good_csv": case_dir / "waveform_good.csv",
        "bad_csv": case_dir / "waveform_bad.csv",
        "good_vcd": case_dir / "waveform_good.vcd",
        "bad_vcd": case_dir / "waveform_bad.vcd",
        "strategy": "self_primary_bootstrap",
    }
    if Path(primary["tb_path"]).exists() and Path(primary["good_csv"]).exists() and Path(primary["bad_csv"]).exists():
        return primary

    if donor_name:
        donor_dir = root / donor_name
        return {
            "source_case": donor_name,
            "source_label": f"donor primary trace from {donor_name}",
            "tb_path": donor_dir / "tb.v",
            "good_csv": donor_dir / "waveform_good.csv",
            "bad_csv": donor_dir / "waveform_bad.csv",
            "good_vcd": donor_dir / "waveform_good.vcd",
            "bad_vcd": donor_dir / "waveform_bad.vcd",
            "strategy": "cluster_donor_primary_fallback",
        }

    return primary


def ensure_decoy_structure(root: Path) -> List[Dict[str, object]]:
    entries = load_manifest(root)
    clusters = build_cluster_members(entries)
    rows: List[Dict[str, object]] = []

    for entry in entries:
        case_name = str(entry["name"])
        key = cluster_key(entry)
        donor_name = choose_decoy_donor(case_name, clusters.get(key, [case_name]))
        source = select_source_files(root, case_name, donor_name)
        case_dir = root / case_name
        current_case_id = case_id(case_name)

        tb_text = Path(source["tb_path"]).read_text(encoding="utf-8")
        decoy_tb = rewrite_dumpfile_and_add_idle(
            tb_text,
            current_case_id=current_case_id,
            source_case=str(source["source_case"]),
        )
        (case_dir / "tb_decoy.v").write_text(decoy_tb, encoding="utf-8", newline="\n")

        decoy_good_csv = copy_if_exists(Path(source["good_csv"]), case_dir / "waveform_good_decoy.csv")
        decoy_bad_csv = copy_if_exists(Path(source["bad_csv"]), case_dir / "waveform_bad_decoy.csv")
        decoy_good_vcd = copy_if_exists(Path(source["good_vcd"]), case_dir / "waveform_good_decoy.vcd")
        decoy_bad_vcd = copy_if_exists(Path(source["bad_vcd"]), case_dir / "waveform_bad_decoy.vcd")

        lure = str(entry.get("overfit_lure", "") or "").strip()
        if not lure:
            lure = default_overfit_lure(entry, str(source["source_label"]))
            entry["overfit_lure"] = lure

        entry["overfit_decoy_source_case"] = str(source["source_case"])
        entry["overfit_decoy_strategy"] = str(source["strategy"])
        append_decoy_notes(case_dir, lure, str(source["source_label"]))

        rows.append(
            {
                "case_name": case_name,
                "seed_case_name": str(entry.get("seed_case_name", "") or ""),
                "decoy_source_case": str(source["source_case"]),
                "decoy_strategy": str(source["strategy"]),
                "overfit_lure_present": bool(lure),
                "tb_decoy_present": (case_dir / "tb_decoy.v").exists(),
                "waveform_good_decoy_present": decoy_good_csv,
                "waveform_bad_decoy_present": decoy_bad_csv,
                "waveform_good_decoy_vcd_present": decoy_good_vcd,
                "waveform_bad_decoy_vcd_present": decoy_bad_vcd,
                "decoy_structure_ok": bool(lure and decoy_good_csv and decoy_bad_csv),
            }
        )

    write_manifest(root, entries)
    return rows
