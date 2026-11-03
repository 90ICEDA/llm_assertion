from __future__ import annotations
import csv, hashlib, json, shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/final_acceptance_bundle_20260810"
ITEMS=[
 (1,"新增数据验收定版","final_dataset_acceptance_20260804","01_dataset_acceptance","accepted","最终manifest、rejected、golden、trace、hardness及完整仿真日志齐全"),
 (2,"新独立case主实验","final46_main_experiment_20260806","02_main_experiment","accepted","统一主表、分解、parent去重和自动重算审计齐全"),
 (3,"统计显著性与稳定性","final46_significance_stability_20260807","03_statistics_stability","accepted","parent级显著性、CI、McNemar、effect size及seed/temperature/k齐全"),
 (4,"Trace与RTL机制分析","final46_mechanism_analysis_20260808","04_mechanism_analysis","accepted","trace控制、RTL context、四象限和人工failure analysis齐全"),
 (5,"同预算visible-only选择","equal_budget_visible_selection_20260809","05_equal_budget_selection","accepted","同预算比较、选择明细、parent去重、coverage曲线和held-out不变性审计齐全"),
 (6,"Failure-guided repair","one_step_failure_guided_repair_20260810","06_failure_guided_repair","accepted","one-step主表、分类修复率、前后指标和完整案例齐全"),
 (7,"过拟合挑战与泛化数据","overfit_challenge_generalization_v2_20260810","07_overfit_generalization","accepted_controlled_semantic_scope","六类诱饵、三种变换、hard pairs和四套无泄漏split齐全；属于受控语义挑战集"),
 (8,"跨模型成本与复现","cross_model_cost_repro_20260810","08_cross_model_repro","accepted","四模型等候选预算、Qwen两阶段、成本、完整seal和端到端审计齐全"),
]

def sha(p:Path)->str:
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
 return h.hexdigest()

def main():
 if OUT.exists(): shutil.rmtree(OUT)
 OUT.mkdir(parents=True)
 inventory=[]; matrix=[]
 for no,title,src_name,dst_name,status,note in ITEMS:
  src=ROOT/"deliverables"/src_name; dst=OUT/dst_name; shutil.copytree(src,dst)
  if no==8:
   shutil.copy2(ROOT/"scripts/run_all_cross_model_repro.ps1",dst/"run_all_cross_model_repro.ps1")
   shutil.copy2(ROOT/"REPRODUCE_CROSS_MODEL.md",dst/"REPRODUCE_CROSS_MODEL.md")
  files=sorted(x for x in dst.rglob("*") if x.is_file())
  for p in files:
   inventory.append({"item_no":no,"item":title,"status":status,"relative_path":p.relative_to(OUT).as_posix(),"source_directory":src_name,"size_bytes":p.stat().st_size,"sha256":sha(p)})
  matrix.append({"item_no":no,"item":title,"status":status,"artifact_directory":dst_name,"file_count":len(files),"size_bytes":sum(x.stat().st_size for x in files),"scope_note":note})
 with (OUT/"acceptance_matrix.csv").open("w",newline="",encoding="utf-8-sig") as f:
  w=csv.DictWriter(f,fieldnames=matrix[0]);w.writeheader();w.writerows(matrix)
 with (OUT/"artifact_inventory.csv").open("w",newline="",encoding="utf-8-sig") as f:
  w=csv.DictWriter(f,fieldnames=inventory[0]);w.writeheader();w.writerows(inventory)
 sums="\n".join(f'{x["sha256"]}  {x["relative_path"]}' for x in inventory)+"\n";(OUT/"SHA256SUMS.txt").write_text(sums,encoding="utf-8")
 summary={"bundle_status":"accepted","item_count":8,"artifact_file_count":len(inventory),"total_size_bytes":sum(x["size_bytes"] for x in inventory),"items":matrix}
 (OUT/"bundle_manifest.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
 index=["# AssertionForge 最终验收包","","本目录集中保存八项任务的最终验收产物。所有文件均为自包含副本，并由 `artifact_inventory.csv` 和 `SHA256SUMS.txt` 冻结。","","## 验收目录",""]
 for m in matrix:index.append(f'{m["item_no"]}. **{m["item"]}** — `{m["status"]}` — `{m["artifact_directory"]}/` — {m["file_count"]} files')
 index += ["","## 使用说明","","- 先查看 `acceptance_overview.xlsx` 或 `acceptance_matrix.csv`。","- 逐项数据使用对应编号目录。","- 文件完整性使用 `SHA256SUMS.txt` 或 `artifact_inventory.csv` 验证。","- 第7项为受控语义过拟合挑战集，不应描述为真实项目RTL重新综合实验。","- 第8项的一键脚本和复现文档已复制进对应目录。"]
 (OUT/"INDEX.md").write_text("\n".join(index)+"\n",encoding="utf-8")
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
