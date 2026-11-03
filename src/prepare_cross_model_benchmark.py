from __future__ import annotations
import argparse, hashlib, json, shutil
from pathlib import Path
DEFAULT=["case101_prim_onehot_multihot_suppressed","case104_prim_fifo_full_early","case112_prim_intr_test_pulse_dropped","case125_prim_fifo_wrap_late","case135_prim_intr_enable_mask_ignored"]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--source",default="rtl_cases_real_scale120");ap.add_argument("--out",required=True);ap.add_argument("--all",action="store_true");a=ap.parse_args();src,out=Path(a.source).resolve(),Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
 ids=sorted(x.name for x in src.iterdir() if x.is_dir()) if a.all else DEFAULT; rows=[]
 required=["correct.v","buggy.v","tb.v","tb_holdout.v","waveform_good.csv","waveform_bad.csv"]
 for cid in ids:
  s,d=src/cid,out/cid
  missing=[x for x in required if not(s/x).exists()]
  if missing:raise RuntimeError(f"{cid} missing {missing}")
  if d.exists():shutil.rmtree(d)
  shutil.copytree(s,d)
  rows.append({"case_id":cid,"file_count":sum(1 for x in d.iterdir() if x.is_file()),"case_sha256":hashlib.sha256("".join(sha(x) for x in sorted(d.iterdir()) if x.is_file()).encode()).hexdigest()})
 (out/"benchmark_manifest.json").write_text(json.dumps({"case_count":len(rows),"cases":rows},indent=2),encoding="utf-8")
 print(out/"benchmark_manifest.json")
if __name__=="__main__":main()
