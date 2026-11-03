# Copyright (c) 2025, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

from utils import get_ts
from config import FLAGS
from saver import saver
from typing import Tuple, List, Optional
import os
import subprocess
import re
import tiktoken, shutil

print = saver.log_info


REPORT_UNDETECTABLE_START = "### AF_UNDETECTABLE_START ###"
REPORT_UNDETECTABLE_END = "### AF_UNDETECTABLE_END ###"
REPORT_UNPROCESSED_START = "### AF_UNPROCESSED_START ###"
REPORT_UNPROCESSED_END = "### AF_UNPROCESSED_END ###"
REPORT_COVER_STATUS_START = "### AF_ANTECEDENT_COVER_STATUS_START ###"
REPORT_COVER_STATUS_END = "### AF_ANTECEDENT_COVER_STATUS_END ###"

FORMAL_STATUS_PRIORITY = {
    "proven": 3.0,
    "inconclusive": 2.0,
    "cex": 1.0,
    "error": 0.0,
}


def analyze_coverage_of_proven_svas(svas: List[str], jasper_reports: List[str]) -> str:
    """
    Collect proven SVAs, create a combined SVA file, and run coverage analysis.

    Args:
        svas (List[str]): List of all generated SVAs.
        jasper_reports (List[str]): List of paths to JasperGold report files.

    Returns:
        str: Coverage report as a string.
    """
    print("\n=== Starting Coverage Analysis ===")

    # Debug: Print input counts
    print(f"Number of SVAs: {len(svas)}")
    print(f"Number of reports: {len(jasper_reports)}")

    # Collect only non-vacuous proven SVAs so coverage is not dominated by unreachable antecedents.
    proven_svas = []
    for sva, report_path in zip(svas, jasper_reports):
        with open(report_path, 'r') as f:
            report_content = f.read()
        if (
            extract_proof_status(report_content) == "proven"
            and extract_antecedent_reachability(report_content) is not False
        ):
            proven_svas.append(sva)

    print(f"Number of non-vacuous proven SVAs: {len(proven_svas)}")
    if not proven_svas:
        return "No non-vacuous proven SVAs found. Coverage analysis cannot be performed."

    # Print paths for verification
    print(f"\nDesign directory: {FLAGS.design_dir}")
    original_sva_path = os.path.join(FLAGS.design_dir, "property_goldmine.sva")
    print(f"Original SVA path: {original_sva_path}")
    print(f"File exists: {os.path.exists(original_sva_path)}")

    with open(original_sva_path, "r") as f:
        original_content = f.read()
    print(f"Original SVA file length: {len(original_content)} chars")

    # Extract module info
    # Extract module interface from SVA
    module_match = re.search(
        r'module\s+(\w+)\s*\((.*?)\);', original_content, re.DOTALL
    )
    if not module_match:
        return "Error: Could not find module declaration in the original SVA file."

    module_interface = f"module {module_match.group(1)}({module_match.group(2)});"

    # Debug: Print TCL info
    original_tcl_path, original_tcl_content = find_and_read_original_tcl(
        FLAGS.design_dir
    )
    print(f"\nOriginal TCL path: {original_tcl_path}")
    print(
        f"Original TCL exists: {os.path.exists(original_tcl_path) if original_tcl_path else False}"
    )

    # Extract module name from already loaded TCL content
    module_name = extract_top_module(original_tcl_content)
    if not module_name:
        return f"Error: Could not find elaborate -top command in the TCL file: {original_tcl_path}"

    print(f"\nExtracted module name from TCL: {module_name}")

    # Create combined SVA file
    combined_sva_path = os.path.join(saver.logdir, "combined_proven_svas.sva")
    print(f"\nWriting combined SVA to: {combined_sva_path}")

    with open(combined_sva_path, 'w') as f:
        f.write(f"{module_interface}\n\n")
        for i, sva in enumerate(proven_svas):
            f.write(f"property p{i};\n")
            f.write(f"{sva}\n")
            f.write(f"endproperty\n")
            f.write(f"a{i}: assert property(p{i});\n\n")
        f.write("endmodule\n")

    print(f"Combined SVA file written successfully")

    if not original_tcl_path:
        return "Error: Could not find the original TCL file in the specified directory."

    design_file = extract_design_file(original_tcl_content)
    print(f"Extracted design file: {design_file}")

    if not design_file:
        return f"Error: Could not find design file name in the original TCL file: {original_tcl_path}"

    stopat_command, clock_command, reset_command = extract_clock_and_reset(original_tcl_content)
    maybe_stopat_line = stopat_command if stopat_command else ""

    print(f"\nExtracted 'stopat' command: {stopat_command}")
    print(f"Extracted clock command: {clock_command}")
    print(f"Extracted reset command: {reset_command}")

    if not clock_command or not reset_command:
        return f"Error: Could not find clock and reset commands in the original TCL file: {original_tcl_path}"

    # Write TCL file
    tcl_file_path = os.path.join(saver.logdir, "coverage_analysis.tcl")
    print(f"\nWriting TCL file to: {tcl_file_path}")

    tcl_content = f"""
# Analyze property files 
clear -all 

set ROOT_PATH {FLAGS.design_dir}
set RTL_PATH ${{ROOT_PATH}}

# Initialize coverage for both stimuli models and COI 
check_cov -init -model all -type all -exclude_module {module_name}_tb

analyze -clear 
analyze -v2k ${{RTL_PATH}}/{design_file}
analyze -sva ${{RTL_PATH}}/bindings.sva {combined_sva_path}

# Elaborate design and properties 
elaborate -top {module_name}

# Define clock and reset signals and run proof
{maybe_stopat_line}
{clock_command}
{reset_command}

# Get design information to check general complexity
get_design_info

# Run proof on all assertions with a time limit 
prove -all -time_limit 1m

# Get proof results
set proofs_status [get_status [get_property_list -include {{type {{assert}} disabled {{0}}}}]]

# Output the proof results
puts "proofs: $proofs_status"

# Check if any properties failed (have status 'cex' or 'falsified')
set failed_props [get_property_list -include {{type {{assert}} status {{cex falsified}}}}]

if {{[llength $failed_props] > 0}} {{
    puts "WARNING: Some properties failed with counterexample:"
    foreach prop $failed_props {{
        puts "  - $prop"
    }}
    puts "Continuing with coverage calculation despite property failures..."
}}

# Measure coverage for both stimuli models and COI regardless of property failures
check_cov -measure -type all -verbose

# Coverage reporting script 
set coverage_models {{functional statement toggle expression branch}}
set coverage_types {{stimuli coi}}

puts "\\nCOVERAGE REPORT"
puts "TYPE|MODEL|COVERAGE"
puts "--------------------"

foreach type $coverage_types {{
    foreach model $coverage_models {{
        if {{$type == "coi"}} {{
            set coverage_data [check_cov -report -model $model -type checker -checker_mode coi]
        }} else {{
            set coverage_data [check_cov -report -model $model -type $type]
        }}
        if {{[regexp {{([0-9.]+)%}} $coverage_data match coverage]}} {{
            puts "$type|$model|$coverage"
        }} else {{
            puts "$type|$model|N/A"
        }}
    }}
}}

puts "### COVERAGE_REPORT_START ###"    
set undetectable_coverage [check_cov -list -status undetectable -checker_mode coi]
puts "### UNDETECTABLE_START ###"
puts $undetectable_coverage
puts "### UNDETECTABLE_END ###"

set unprocessed_coverage [check_cov -list -status unprocessed -checker_mode coi]
puts "### UNPROCESSED_START ###"
puts $unprocessed_coverage
puts "### UNPROCESSED_END ###"

puts "### COVERAGE_REPORT_END ###"
"""

    with open(tcl_file_path, 'w') as f:
        f.write(tcl_content)
    print("TCL file written successfully")

    # Launch JasperGold
    folder_name = "coverage_analysis"
    jg_proj_dir = os.path.join(saver.logdir, f"jgproject_{folder_name}_{get_ts()}")
    print(f"\nJasperGold project directory: {jg_proj_dir}")

    jg_command = [
        "jg",
        "-fpv",
        "-batch",
        "-tcl",
        tcl_file_path,
        "-proj",
        jg_proj_dir,
        "-allow_unsupported_OS",
    ]

    # Print complete command for manual running
    print("\n=== Command for manual execution ===")
    print(f"cd {FLAGS.design_dir} && \\")
    print(" ".join(jg_command))
    print("===============================\n")

    try:
        print("Executing JasperGold command...")
        result = subprocess.run(
            jg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            cwd=FLAGS.design_dir,
        )
        # Save coverage report to file
        report_path = os.path.join(saver.logdir, "coverage_report.log")
        with open(report_path, 'w') as f:
            f.write(result.stdout)
        print(f'Saved Jasper coverage report to {report_path}')
        return result.stdout
    except subprocess.CalledProcessError as e:
        print("\n=== Error Details ===")
        print(f"Return code: {e.returncode}")
        print("\n=== Stdout ===")
        print(e.stdout)
        print("\n=== Stderr ===")
        print(e.stderr)
        return f"Error: {e}\n"
    finally:
        # Remove the JasperGold project directory to prevent disk space issues
        if os.path.exists(jg_proj_dir):
            shutil.rmtree(jg_proj_dir)
            print(f"Removed temporary JasperGold project directory: {jg_proj_dir}")


def find_and_read_original_tcl(design_dir: str) -> Tuple[str, str]:
    """
    Find and read the original TCL file in the design directory.

    Args:
        design_dir (str): Path to the design directory.

    Returns:
        Tuple[str, str]: Path to the original TCL file and its content, or (None, None) if not found.
    """
    for root, _, files in os.walk(design_dir):
        for file in files:
            if file.endswith('.tcl'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r') as f:
                    content = f.read()
                if 'analyze -v2k' in content:
                    return file_path, content
    return None, None


def extract_top_module(tcl_content: str) -> str:
    """
    Extract top module name from the elaborate line in TCL content.

    Args:
        tcl_content (str): Content of the TCL file

    Returns:
        str: Top module name or None if not found
    """
    # Look for elaborate -top line
    for line in tcl_content.split('\n'):
        line = line.strip()
        if line.startswith('elaborate -top'):
            # Extract module name after 'elaborate -top'
            parts = line.split()
            if len(parts) >= 3:
                return parts[2]
    return None


def extract_design_file(tcl_content: str) -> str:
    """
    Extract the design file name from the TCL content.

    Args:
        tcl_content (str): Content of the TCL file.

    Returns:
        str: Name of the design file, or None if not found.
    """
    # Join lines that are continued with a backslash
    lines = tcl_content.split('\n')
    joined_lines = []
    current_line = ""
    for line in lines:
        if line.strip().endswith('\\'):
            current_line += line.strip()[:-1] + " "  # Remove backslash and add space
        else:
            current_line += line
            joined_lines.append(current_line.strip())
            current_line = ""

    # If there's any remaining content in current_line, add it
    if current_line:
        joined_lines.append(current_line.strip())

    # Now search for the 'analyze -v2k' command in the joined lines
    for line in joined_lines:
        if 'analyze -v2k' in line:
            match = re.search(r'\$\{RTL_PATH\}/(\S+\.v)', line)
            if match:
                return match.group(1)

    # If we couldn't find it with ${RTL_PATH}, try without it
    for line in joined_lines:
        if 'analyze -v2k' in line:
            match = re.search(r'(\S+\.v)', line)
            if match:
                return match.group(1)

    return None


def find_original_tcl_file(logdir: str) -> str:
    """
    Find TCL files in the specified directory.

    Args:
        logdir (str): Path to the log directory.

    Returns:
        str: Path to the first TCL file found, or None if not found.
    """
    tcl_scripts_dir = os.path.join(logdir, "tcl_scripts")
    for file in os.listdir(tcl_scripts_dir):
        if file.endswith('.tcl'):
            return os.path.join(tcl_scripts_dir, file)
    return None


def extract_clock_and_reset(tcl_content: str) -> Tuple[str, str, str]:
    """
    Extract 'stopat -env', 'clock', and 'reset' commands from the TCL content.

    Args:
        tcl_content (str): Content of the TCL file.

    Returns:
        Tuple[str, str, str]: stopat_command, clock_command, reset_command
                              Any of them may be None if not found.
    """
    stopat_command = None
    clock_command = None
    reset_command = None

    lines = tcl_content.split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('stopat -env'):
            stopat_command = line
        elif line.startswith('clock'):
            clock_command = line
        elif line.startswith('reset'):
            reset_command = line

    return stopat_command, clock_command, reset_command


def extract_proof_status(report_content: str) -> str:
    """
    Extract the proof status from the JasperGold report, focusing only on assertions.

    Args:
        report_content (str): Content of the JasperGold report.

    Returns:
        str: The proof status (proven, cex, inconclusive, or error).
    """
    def _has_fatal_jasper_error(text: str) -> bool:
        fatal_patterns = [
            r"(?im)^\s*(?:fatal|internal\s+error)\s*:",
            r"(?im)^\s*error\s*:",
            r"(?im)^\s*\*\*?\s*error\b",
            r"(?im)\blicense\b.*\b(error|fail|denied|checkout failed)\b",
            r"(?im)\bcommand\s+not\s+found\b",
        ]
        ignored_patterns = [
            "### AF_ANTECEDENT_COVER_STATUS_START ###",
            "### AF_ANTECEDENT_COVER_STATUS_END ###",
            "### AF_UNDETECTABLE_START ###",
            "### AF_UNDETECTABLE_END ###",
            "### AF_UNPROCESSED_START ###",
            "### AF_UNPROCESSED_END ###",
            "### AF_COVER_RUN_ERROR ###",
            "### AF_COVERAGE_MEASURE_ERROR ###",
        ]
        filtered_lines = []
        for line in text.splitlines():
            if any(marker in line for marker in ignored_patterns):
                continue
            filtered_lines.append(line)
        filtered_text = '\n'.join(filtered_lines)
        return any(re.search(pattern, filtered_text) for pattern in fatal_patterns)

    # Look for the SUMMARY section
    summary_section = re.search(
        r'==============================================================\nSUMMARY\n==============================================================\n(.*?)\n\n',
        report_content,
        re.DOTALL,
    )

    if not summary_section:
        return "error" if _has_fatal_jasper_error(report_content) else "inconclusive"

    summary_lines = summary_section.group(1).strip().split('\n')
    assertion_section = False
    assertion_statuses = {}

    for line in summary_lines:
        if line.strip().startswith("assertions"):
            assertion_section = True
            continue
        if assertion_section and line.strip().startswith("covers"):
            break
        if assertion_section:
            parts = line.split(':')
            if len(parts) == 2:
                status = parts[0].strip().lower()
                count = int(parts[1].strip().split()[0])
                assertion_statuses[status] = count

    # Check which assertion statuses have non-zero counts
    non_zero_statuses = [
        status for status, count in assertion_statuses.items() if count > 0
    ]

    if "- proven" in non_zero_statuses:
        return "proven"
    elif "- cex" in non_zero_statuses or "- ar_cex" in non_zero_statuses:
        return "cex"
    elif "- undetermined" in non_zero_statuses or "- unknown" in non_zero_statuses:
        return "inconclusive"
    elif len(non_zero_statuses) == 0:
        return "error" if _has_fatal_jasper_error(report_content) else "inconclusive"
    else:
        return non_zero_statuses[
            0
        ]  # Return the first non-zero status if it doesn't match known categories

    return "inconclusive"


def _extract_marked_section(
    report_content: str, start_marker: str, end_marker: str
) -> Optional[str]:
    pattern = re.escape(start_marker) + r"\s*(.*?)\s*" + re.escape(end_marker)
    match = re.search(pattern, report_content, re.DOTALL)
    return match.group(1) if match else None


def _section_has_meaningful_entries(section_content: Optional[str]) -> Optional[bool]:
    if section_content is None:
        return None

    cleaned_lines = []
    for raw_line in section_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line in {"{}", "[]"}:
            continue
        lower = line.lower()
        if lower in {
            "none",
            "null",
            "n/a",
            "no objects found",
            "no properties found",
        }:
            continue
        if lower.startswith("__af_error__"):
            return None
        cleaned_lines.append(line)

    return len(cleaned_lines) > 0


def extract_antecedent_reachability(report_content: str) -> Optional[bool]:
    """
    Infer whether the assertion antecedent was reachable during formal analysis.

    Returns:
        True when Jasper covers the antecedent-only helper property,
        False when Jasper proves that helper cover is uncoverable,
        None when the report does not contain enough metadata.
    """
    cover_status_section = _extract_marked_section(
        report_content, REPORT_COVER_STATUS_START, REPORT_COVER_STATUS_END
    )
    if cover_status_section is not None:
        normalized = " ".join(
            line.strip()
            for line in cover_status_section.splitlines()
            if line.strip()
        ).lower()
        if normalized and not normalized.startswith("__af_error__"):
            if "uncoverable" in normalized or "unreachable" in normalized:
                return False
            if "covered" in normalized:
                return True
            if "__af_none__" in normalized:
                return None
            if "undetermined" in normalized or "unknown" in normalized:
                return None

    undetectable = _section_has_meaningful_entries(
        _extract_marked_section(
            report_content, REPORT_UNDETECTABLE_START, REPORT_UNDETECTABLE_END
        )
    )
    unprocessed = _section_has_meaningful_entries(
        _extract_marked_section(
            report_content, REPORT_UNPROCESSED_START, REPORT_UNPROCESSED_END
        )
    )

    if undetectable is False and unprocessed is False:
        return True
    if undetectable is True or unprocessed is True:
        return False
    if undetectable is not None or unprocessed is not None:
        return None

    legacy_patterns = [
        r'(?im)\b(assert(?:ion)?|property)\b.*\b(unreachable|vacuous|undetectable)\b',
        r'(?im)\b(unreachable|vacuous|undetectable)\b.*\b(assert(?:ion)?|property)\b',
    ]
    if any(re.search(pattern, report_content) for pattern in legacy_patterns):
        return False

    return None


def format_antecedent_reachability(report_content: str) -> str:
    reachability = extract_antecedent_reachability(report_content)
    if reachability is True:
        return "reachable"
    if reachability is False:
        return "unreachable"
    return "unknown"


def get_effective_formal_score(
    proof_status: str, antecedent_reachability: Optional[bool]
) -> float:
    base_score = FORMAL_STATUS_PRIORITY.get(proof_status, -1)
    if proof_status != "proven":
        return float(base_score)
    if antecedent_reachability is False:
        return 1.5
    if antecedent_reachability is None:
        return 2.75
    return float(base_score)


def get_effective_proof_status(
    proof_status: str, antecedent_reachability: Optional[bool]
) -> str:
    if proof_status == "proven" and antecedent_reachability is False:
        return "proven_vacuous"
    if proof_status == "proven" and antecedent_reachability is None:
        return "proven_unknown_reachability"
    return proof_status


def count_tokens_in_file(file_path):
    with open(file_path, 'r') as file:
        content = file.read()

    # Use the cl100k_base encoder, which is used for GPT-4 and ChatGPT
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = enc.encode(content)
    return len(tokens)


def find_original_tcl_file(design_dir: str) -> str:
    """
    Find the original TCL file in the design directory.

    Args:
        design_dir (str): Path to the design directory.

    Returns:
        str: Path to the original TCL file, or None if not found.
    """
    for root, dirs, files in os.walk(design_dir):
        for file in files:
            if file.endswith('.tcl') and file.startswith('FPV_'):
                return os.path.join(root, file)
    return None
