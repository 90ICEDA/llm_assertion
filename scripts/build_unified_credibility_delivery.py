#!/usr/bin/env python3
"""Build the unified, hash-inventoried credibility-audit delivery."""
from __future__ import annotations
import csv,fnmatch,hashlib,json,os,shutil,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/unified_credibility_audit_20260829"
ARCHIVE=OUT/"raw_evidence.tar.gz"
def long(p):
 s=str(Path(p).resolve());return "\\\\?\\"+s if os.name=="nt" else s
def sha(p):
 h=hashlib.sha256()
 with open(long(p),"rb") as f:
  for b in iter(lambda:f.read(1<<20),b""):h.update(b)
 return h.hexdigest()
def walk(rel):
 base=ROOT/rel;prefix=long(base)
 if base.is_file():return [base]
 ans=[]
 for d,_,fs in os.walk(prefix):
  for f in fs:ans.append(Path(d.replace("\\\\?\\",""))/f)
 return ans
def role(rel):
 s=rel.replace("\\","/")
 if "behavioral_probes_v3" in s:return "raw candidate×probe verdict/stimulus/checker/log"
 if "sequential_generation_v3_pilot30" in s:return "raw candidate generation/evidence/log"
 if "dominance_pairs_v3" in s:return "frozen dominance pair raw data"
 if "phase_b_ood_eval_v1" in s:return "OOD raw evaluation/log/metric"
 if "manual_separability" in s:return "blinded review/witness/CEX"
 if "probe_order_sensitivity" in s:return "probe order/Jaccard/resolution replay"
 if "results_accounting" in s:return "parent flow/metric provenance audit"
 if s.startswith("scripts/") or s.startswith("src/"):return "statistics/reproduction script"
 if "manifest" in s:return "parent/experiment manifest"
 if s.startswith("configs/"):return "frozen config/seed"
 if s.endswith(".log"):return "complete execution log"
 return "supporting raw evidence"
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 sources=[
  "deliverables/final_dataset_acceptance_20260804/final_manifest.json","deliverables/final_dataset_acceptance_20260804/rejected_cases.csv","deliverables/final_dataset_acceptance_20260804/golden_validation.csv","deliverables/final_dataset_acceptance_20260804/hardness_validation.csv","deliverables/final_dataset_acceptance_20260804/provenance_validation.csv","deliverables/final_dataset_acceptance_20260804/trace_activation.csv",
  "deliverables/final46_main_experiment_20260806/parent_deduplicated_results.csv","deliverables/final46_main_experiment_20260806/candidate_details.csv",
  "deliverables/equal_budget_visible_selection_20260809",
  "outputs/behavioral_preference_pilot_v1/selected_train_parents.csv","outputs/behavioral_preference_pilot_v1/pilot_manifest.json","outputs/behavioral_preference_pilot_v1/behavioral_preference_v3_frozen.json","outputs/behavioral_preference_pilot_v1/candidate_evidence_schema.json","outputs/behavioral_preference_pilot_v1/behavioral_probes_v3","outputs/behavioral_preference_pilot_v1/sequential_generation_v3_pilot30","outputs/behavioral_preference_pilot_v1/dominance_pairs_v3","outputs/behavioral_preference_pilot_v1/final_report_v1","outputs/behavioral_preference_pilot_v1/ollama_cpu_stderr.log","outputs/behavioral_preference_pilot_v1/ollama_cpu_stdout.log",
  "outputs/phase_b_ood_eval_v1","outputs/behavioral_preference_closed_loop_final_v1","outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json","outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.log",
  "deliverables/one_step_failure_guided_repair_20260810",
  "deliverables/results_accounting_audit_20260829","deliverables/probe_order_sensitivity_20260829","deliverables/manual_separability_review_20260829",
  "configs/behavioral_preference_pilot_v1.json",
  "scripts/rebuild_results_audit.py","scripts/analyze_probe_order_sensitivity.py","scripts/repair_missing_probe_verdicts.py","scripts/prepare_blinded_manual_pair_review.py","scripts/run_blinded_manual_separability_review.py","scripts/build_unified_credibility_delivery.py",
  "src/behavioral_preference_v3_probes.py","src/build_behavioral_preference_v3_dominance.py","src/build_pilot_v1_final_report.py","src/analyze_behavioral_generalization_evidence.py"
 ]
 files={}
 for src in sources:
  p=ROOT/src
  if not p.exists():raise FileNotFoundError(src)
  for f in walk(src):
   rel=f.relative_to(ROOT).as_posix()
   # Compiled binaries/VCD are rebuild products; JSON embeds full commands,
   # stdout/stderr, return codes and timeout flags. Keep all text/raw evidence.
   if f.suffix.lower() in {".out",".vcd",".pyc"}:continue
   files[rel]=f
 inventory=[]
 if ARCHIVE.exists():ARCHIVE.unlink()
 with tarfile.open(long(ARCHIVE),"w:gz",compresslevel=6) as tf:
  for rel,f in sorted(files.items()):
   tf.add(long(f),arcname=rel,recursive=False)
   inventory.append({"archive_path":rel,"source_path":rel,"logical_role":role(rel),"size_bytes":os.stat(long(f)).st_size,"sha256":sha(f)})
 with (OUT/"artifact_inventory.csv").open("w",encoding="utf-8-sig",newline="") as h:
  w=csv.DictWriter(h,fieldnames=list(inventory[0]));w.writeheader();w.writerows(inventory)
 archive_sha=sha(ARCHIVE)
 # Easy-access copies of the derived deliverables; raw evidence remains in archive.
 easy=OUT/"artifacts"
 if easy.exists():shutil.rmtree(long(easy))
 easy.mkdir()
 for name in ("results_accounting_audit_20260829","probe_order_sensitivity_20260829","manual_separability_review_20260829"):
  shutil.copytree(long(ROOT/"deliverables"/name),easy/name)
 # Keep the append-only log at the delivery root; copytree intentionally does not touch it.
 summary={"status":"complete","archive":"raw_evidence.tar.gz","archive_sha256":archive_sha,"file_count":len(inventory),"uncompressed_bytes":sum(int(x["size_bytes"]) for x in inventory),"archive_bytes":ARCHIVE.stat().st_size,"roles":dict(__import__('collections').Counter(x["logical_role"] for x in inventory))}
 (OUT/"delivery_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
 readme='''# Unified credibility audit delivery\n\nThis delivery contains the sample-flow/accounting audit, probe-order sensitivity replay, blinded manual-separability review, replayable witnesses, append-only unexpected-behavior log, and a hash-inventoried archive of raw evidence and scripts.\n\n- `raw_evidence.tar.gz`: actual raw files with repository-relative paths.\n- `artifact_inventory.csv`: per-file role, byte size and SHA-256.\n- `SHA256SUMS.txt`: archive and inventory checksums.\n- `artifacts/`: convenient unpacked copies of the three new audit deliverables.\n- `unexpected_behavior.md`: append-only anomaly history; resolved false alarms are retained.\n\nCompiled `.out`, `.pyc` and VCD rebuild products are omitted; result JSON retains commands, tool outputs, return codes, timeout flags, hashes and verdicts, while stimuli/checkers/SVA are included for replay.\n'''
 (OUT/"README.md").write_text(readme,encoding="utf-8")
 checks=[("raw_evidence.tar.gz",ARCHIVE),("artifact_inventory.csv",OUT/"artifact_inventory.csv"),("unexpected_behavior.md",OUT/"unexpected_behavior.md"),("README.md",OUT/"README.md"),("delivery_summary.json",OUT/"delivery_summary.json")]
 if (OUT/"build_error.log").exists():checks.append(("build_error.log",OUT/"build_error.log"))
 (OUT/"SHA256SUMS.txt").write_text("".join(f"{sha(p)}  {name}\n" for name,p in checks),encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":
 try:main()
 except Exception as exc:
  import traceback
  OUT.mkdir(parents=True,exist_ok=True)
  (OUT/"build_error.log").write_text(traceback.format_exc(),encoding="utf-8")
  raise
