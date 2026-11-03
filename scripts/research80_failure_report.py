"""Read-only aggregation of the completed presentation pilot; no model calls."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepared", type=Path, required=True)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    args = p.parse_args()
    audit = read(args.audit / "audit.json")
    outcome = read(args.run / "outcome.json")
    assert audit["passed"] and audit["outcome"] == outcome
    assert outcome["status"] == "pilot_failed_no_accepted_version"
    cost = read(args.audit / "cost.json")
    names = dict(A="原标识＋完整反馈", B="内容标识与采样绑定＋完整反馈",
                 C="原标识＋去重引用反馈", D="内容标识与采样绑定＋去重引用反馈")
    arms = []
    sources = []
    for arm in "ABCD":
        loc = args.run / "arms" / arm / "plan/v0"
        prepared = args.prepared / "arms" / arm
        decision = read(loc / "decision.json")
        plan = read(loc / "model_call/hold_plan.json")
        rows = {x["id"]: x for x in read(prepared / "windows.private.json")}
        aliases = {v: k for k, v in read(prepared / "aliases.json").items()}
        mismatches = []
        for d in decision["details"]:
            row = rows[d["id"]]
            assert d["window_matches_certificate"] == (d["model_window"] == row["expected"])
            differences = {key: dict(expected=value, actual=d["model_window"].get(key))
                           for key, value in row["expected"].items()
                           if value != d["model_window"].get(key)}
            if differences:
                mismatches.append(dict(id=d["id"], original_id=aliases.get(d["id"], d["id"]),
                                       differences=differences, public_samples=row["public"]))
        response = read(loc / "model_call/response.assembled.json")
        item = dict(arm=arm, presentation=names[arm], accepted=decision["accepted"],
                    windows=len(rows), window_correct=sum(x["window_matches_certificate"] for x in decision["details"]),
                    executed_rule_correct=sum(x["rule_matches_certificate"] for x in decision["details"]),
                    rule_window_consistent=sum(x["rule_matches_window"] for x in decision["details"]),
                    rule_binding_errors=[x for x in decision["reasons"] if x["kind"] == "incorrect_rule_binding"],
                    actual_rules={k: plan[k] for k in ("trigger_condition", "reset_cancellation", "hold_requirement")},
                    mismatches=mismatches, finish_reason=response["service_done"]["finish_reason"],
                    cost=cost["by_phase"]["arms/" + arm])
        assert not item["accepted"] and item["finish_reason"] == "stop"
        arms.append(item)
        for path in (loc / "decision.json", loc / "model_call/hold_plan.json", prepared / "windows.private.json"):
            sources.append(dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    report = dict(scope="One fixed-seed presentation pilot; all arms retain the full plan gate.",
                  outcome=outcome, arms=arms, sources=sources, total_cost=cost["total"],
                  unused_slots=4, unused_slots_transferable=False,
                  conclusion="No new accepted SVA; stopped before generation. No causal gate/no-gate or core mechanism benefit estimate.")
    (args.audit / "presentation_comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# research80：四组呈现先导实际结果", "",
             "已按固定种子7907执行四次真实计划判断。四组均失败，控制器停止；仍停滞在完整计划一致性门控，未进入SVA生成。", "",
             "|组|呈现|统一规则执行正确|逐窗口答案正确|完整计划|输入/输出tokens|",
             "|---|---|---:|---:|---|---:|"]
    for a in arms:
        c = a["cost"]
        lines.append(f"|{a['arm']}|{a['presentation']}|{a['executed_rule_correct']}/11|{a['window_correct']}/11|拒绝|{c['prompt_tokens_total']}/{c['completion_tokens_total']}|")
    lines += ["", "新增接受版本0；完整105历史回放0；新独立验收0（未启动）；两个核心机制增量证据0。",
              "四组仅封存了同一上一版本，不能将四次封存计为四个新版本。", "",
              "A将复位取消条件写成检查周期rst=0，并混淆w1/w3的数据。B规则正确，但6个窗口答案错误。C/D规则正确，均在w0、w2将变化后的数据当作应保持的数据：", "",
              "|窗口|周期|起始mdata|检查mdata|C/D填写expected_data|真实/模型判定|",
              "|---|---|---:|---:|---:|---|",
              "|w0|49→50|3883009061|3883009060|3883009060|violated / satisfied|",
              "|w2|7→8|267114574|267114575|267114575|violated / satisfied|", "",
              "这些数值来自实际响应和封存开发采样。没有拼接其他轮次的正确片段，也没有替模型执行正确规则后将其算为模型完整回答通过。", "",
              "本次观察支持：接口与传输正常，错误仍包含规则与样本运用不一致。内容标识没有在本次试验提高完整通过率；去重引用降低输入tokens，但没有恢复成功。单种子、每格一次不能推断稳定因果收益。所有组均保留计划门槛，因此本实验不能证明该门槛相对直接生成能提高SVA成功率。", "",
              "控制器实际使用4/8次；未触发的4个SVA名额不能用于追加计划调用。新原生编译/执行及形式化调用均为0；模型输入59484、输出4459 tokens，服务账单金额不可用。模型墙钟合计约137.50秒。", "",
              "已停止，不启动第二种子、不扩大机制对比、不生成独立测试。旧独立批次未改动。后续若开展新研究，应另行预注册能区分模型样本执行能力与计划门槛作用的对照；本轮不追加同模型单字段修正、不降低现有接受标准。", "",
              "## 复核命令（无模型调用）", "", "```powershell",
              "wsl -- python3 scripts/research80_pilot_audit.py result --prepared deliverables/research80_prepare_20261024_r02 --run deliverables/research80_real_20261025_r01 --out deliverables/research80_audit_recheck_20261025_r01",
              "wsl -- python3 scripts/research80_failure_report.py --prepared deliverables/research80_prepare_20261024_r02 --run deliverables/research80_real_20261025_r01 --audit deliverables/research80_audit_recheck_20261025_r01",
              "```", "", "原始响应、逐窗口判定及预算流水位于research80_real_20261025_r01；字段级差异与来源哈希见同目录报告的presentation_comparison.json。"]
    (args.audit / "CASE_TRACE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("REPORT", len(arms), "arms; no additional model or native calls")


if __name__ == "__main__":
    main()
