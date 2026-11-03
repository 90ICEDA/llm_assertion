from pathlib import Path
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/behavioral_posthoc_analysis_v1/行为偏好闭环实验归因分析报告.docx"

NAVY = "000000"; BLUE = "000000"; PALE = "FFFFFF"; GRAY = "000000"; LINE = "000000"; RED = "000000"

def font(run, size=10.5, bold=False, color="000000", name="Microsoft YaHei"):
    run.font.name = name; run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size); run.bold = bold; run.font.color.rgb = RGBColor.from_string(color)

def shade(cell, fill):
    return

def margins(cell, top=90, start=110, bottom=90, end=110):
    tc = cell._tc.get_or_add_tcPr(); m = tc.first_child_found_in("w:tcMar")
    if m is None: m = OxmlElement("w:tcMar"); tc.append(m)
    for side, value in (("top",top),("start",start),("bottom",bottom),("end",end)):
        x=OxmlElement(f"w:{side}"); x.set(qn("w:w"),str(value)); x.set(qn("w:type"),"dxa"); m.append(x)

def set_repeat(row):
    trPr=row._tr.get_or_add_trPr(); e=OxmlElement("w:tblHeader"); e.set(qn("w:val"),"true"); trPr.append(e)

def set_table_widths(table, widths):
    table.autofit=False
    grid=table._tbl.tblGrid
    for child in list(grid): grid.remove(child)
    for w in widths:
        e=OxmlElement("w:gridCol"); e.set(qn("w:w"),str(w)); grid.append(e)
    tblPr=table._tbl.tblPr; tblW=tblPr.first_child_found_in("w:tblW")
    tblW.set(qn("w:w"),str(sum(widths))); tblW.set(qn("w:type"),"dxa")
    ind=OxmlElement("w:tblInd"); ind.set(qn("w:w"),"110"); ind.set(qn("w:type"),"dxa"); tblPr.append(ind)
    for row in table.rows:
        for cell,w in zip(row.cells,widths):
            tcPr=cell._tc.get_or_add_tcPr(); tcW=tcPr.first_child_found_in("w:tcW"); tcW.set(qn("w:w"),str(w)); tcW.set(qn("w:type"),"dxa"); margins(cell)

def add_table(doc, headers, rows, widths):
    t=doc.add_table(rows=1, cols=len(headers)); t.style="Table Grid"; set_repeat(t.rows[0])
    for c,txt in zip(t.rows[0].cells,headers):
        c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p=c.paragraphs[0]; p.paragraph_format.space_after=Pt(0); r=p.add_run(txt); font(r,9,bold=True,color="000000")
    for i,row in enumerate(rows):
        cells=t.add_row().cells
        for c,txt in zip(cells,row):
            c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            p=c.paragraphs[0]; p.paragraph_format.space_after=Pt(0); r=p.add_run(str(txt)); font(r,8.6)
    set_table_widths(t,widths); doc.add_paragraph().paragraph_format.space_after=Pt(0)
    return t

def para(doc, text="", bold_lead=None, color="000000", italic=False, after=5):
    p=doc.add_paragraph(); p.paragraph_format.space_after=Pt(after); p.paragraph_format.line_spacing=1.18
    if bold_lead and text.startswith(bold_lead):
        r=p.add_run(bold_lead); font(r,bold=True,color=color); r=p.add_run(text[len(bold_lead):]); font(r,color=color)
    else:
        r=p.add_run(text); font(r,color=color); r.italic=italic
    return p

def bullet(doc,text):
    p=doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after=Pt(2); p.paragraph_format.line_spacing=1.12; font(p.add_run(text),9.8); return p

def label(doc,title,text,warning=False):
    p=doc.add_paragraph(); p.paragraph_format.space_before=Pt(2); p.paragraph_format.space_after=Pt(4)
    font(p.add_run(title+"："),10,bold=True,color="000000"); font(p.add_run(text),10)

def heading(doc,text,level=1):
    p=doc.add_paragraph(text,style=f"Heading {level}"); return p

def code(doc,text):
    p=doc.add_paragraph(); p.paragraph_format.left_indent=Inches(.15); p.paragraph_format.right_indent=Inches(.15); p.paragraph_format.space_after=Pt(5)
    r=p.add_run(text); font(r,8.2,name="Consolas"); return p

def build():
    doc=Document(); sec=doc.sections[0]
    sec.page_width=Inches(8.5); sec.page_height=Inches(11); sec.top_margin=Inches(.82); sec.bottom_margin=Inches(.78); sec.left_margin=Inches(.88); sec.right_margin=Inches(.88); sec.header_distance=Inches(.35); sec.footer_distance=Inches(.35)
    styles=doc.styles
    normal=styles["Normal"]; normal.font.name="Microsoft YaHei"; normal._element.rPr.rFonts.set(qn("w:eastAsia"),"Microsoft YaHei"); normal.font.size=Pt(10.5); normal.paragraph_format.space_after=Pt(5); normal.paragraph_format.line_spacing=1.18
    for n,size,color,before,after in (("Heading 1",16,NAVY,14,6),("Heading 2",12.5,BLUE,10,4),("Heading 3",10.5,BLUE,7,3)):
        s=styles[n]; s.font.name="Microsoft YaHei"; s._element.rPr.rFonts.set(qn("w:eastAsia"),"Microsoft YaHei"); s.font.size=Pt(size); s.font.bold=True; s.font.color.rgb=RGBColor.from_string(color); s.paragraph_format.space_before=Pt(before); s.paragraph_format.space_after=Pt(after); s.paragraph_format.keep_with_next=True
    # Header/footer
    sec.header.paragraphs[0].text=""
    sec.footer.paragraphs[0].text=""
    # Cover
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_before=Pt(55); p.paragraph_format.space_after=Pt(18); font(p.add_run("行为偏好闭环实验归因分析报告"),20,bold=True,color="000000")
    p=doc.add_paragraph(); p.alignment=WD_ALIGN_PARAGRAPH.CENTER; p.paragraph_format.space_after=Pt(30); font(p.add_run("从可执行候选、严格偏序与冻结 OOD Top-1 证据判断模型学到了什么"),12,color="000000")
    add_table(doc,["项目","内容"],[["实验范围","30 train parents · 3 projects · 240 executable candidates"],["偏好数据","483 random + 484 disagreement strict dominance pairs"],["模型与协议","Qwen3-8B · strict five-key JSON AST · deterministic SVA rendering"],["最终结论","NO-GO：未达到 SCS@1 +5pp 且 Fixed-Safe 不下降"],["报告性质","冻结结果上的只读 post-hoc 分析；不修改测试口径与结果"]],[1800,7560])
    label(doc,"核心判断","语法与编译稳定性已显著改善，但没有证据表明模型形成了跨值、跨时序上下文或 unseen bug family 的稳定行为抽象。",True)
    para(doc,"编制日期：2026年8月26日",color=GRAY)
    doc.add_page_break()

    heading(doc,"摘要",1)
    para(doc,"本报告回答五个实验之外但决定论文解释边界的问题：primary 成功候选在何种合法变式上失效；候选不可比较的真实来源；disagreement-guided 是否发现新失败模式；训练收益究竟来自语法模板还是行为抽象；以及行为结果签名是否比文字诊断更适合作为监督。")
    label(doc,"总结果","14 条候选通过原始 primary，但会在观察窗口、值变化、请求间隔、stall/backpressure 和 reset 平移上失效。约 42% 的同-parent候选对未形成严格 preference，其中约 35% 是 FP/TP 签名完全相同，真正交叉不可比仅约 7.3%。")
    label(doc,"证据边界","冻结 probe manifest 没有独立 signal-renaming、width-change 或 parameter-change 分层，因此不能声称这三类泛化已被验证。",True)
    add_table(doc,["问题","结论"],[["Primary 后失效","以绝对周期、具体值和局部 trigger/context 拟合为主"],["不可比较","主要缺少区分证据，不是权重冲突"],["Disagreement-guided","仅增加 1 pair 和 1 signature，未发现新 failure family"],["训练收益","结构合法性/模板收益明确；行为抽象不成立"],["监督选择","行为签名优于文字标签作为主监督，但当前覆盖仍不足"]],[2500,6860])
    heading(doc,"1. 数据与判定口径",1)
    bullet(doc,"Primary pass：compile、fixed_safe、target_detect、non_vacuous 在原始 parent testbench 上同时为真。")
    bullet(doc,"Strict dominance：FP_A ⊆ FP_B、TP_A ⊇ TP_B，且至少一项严格。")
    bullet(doc,"未标注对：FP/TP 签名相同，或两个集合发生交叉而无法形成偏序。")
    bullet(doc,"Failure-mode proxy：probe transformation family；一个 probe 可包含多个 transformation，因此 incidence 计数允许重叠。")

    heading(doc,"2. Primary 成功候选的行为失效",1)
    heading(doc,"2.1 结论",2)
    para(doc,"共有 14 条候选通过原始 primary。合法探针显示，它们往往记住原始轨迹中的具体值、绝对观察周期或局部 trigger，而没有完整编码协议上下文。")
    add_table(doc,["行为归因","探针 family","产生 legal FP 的候选","解释"],[["绝对周期","observation_window_extension","7/14","依赖短观察窗口或 testbench 结束周期"],["具体值/地址","data_address_value","6/14","依赖样例常量而非值域关系"],["请求 trigger","request_spacing","4/14","与原始请求间隔耦合"],["协议上下文","stall_backpressure","4/14","缺失 ready/valid、stall 或 backpressure 条件"],["reset 上下文","reset_translation","3/14","依赖 reset 时点或释放位置"]],[1500,2200,1500,4160])
    para(doc,"Target/family miss 还出现在 observation-window（4 条候选）、data/address-value（3 条）和 request-spacing（1 条）变式上。")
    heading(doc,"2.2 原始证据",2)
    code(doc,"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/case135_prim_intr_enable_mask_ignored/runs/.../result.json")
    code(doc,"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/case139_prim_regwe_addr_check_false_positive/runs/.../result.json")
    code(doc,"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/case461_axis_adapter_segment_boundary_early/runs/.../result.json")
    heading(doc,"2.3 失败/反例",2)
    label(doc,"覆盖缺口","当前探针池没有独立 signal_renaming、width_change 或 parameter_change，因此 data_address_value 只能证明值敏感性，不能替代位宽/参数泛化验证。",True)
    heading(doc,"2.4 下一步决策",2)
    para(doc,"论文应将 primary success 描述为“经常反映 trace-local value、timing-window 与 trigger-context fit”，不得将其直接解释为 invariant protocol behavior。")

    heading(doc,"3. 不可比较候选的真实来源",1)
    heading(doc,"3.1 结论",2)
    para(doc,"每个 policy 有 30 × C(8,2)=840 个同-parent无序候选对。约 42% 未形成严格 preference，但其中绝大部分是当前探针下 FP/TP 签名完全相同。")
    add_table(doc,["Policy","严格 dominance","完全相同签名","交叉不可比","总未标注"],[["random legal","483 (57.50%)","296 (35.24%)","61 (7.26%)","357 (42.50%)"],["disagreement guided","484 (57.62%)","294 (35.00%)","62 (7.38%)","356 (42.38%)"]],[1900,1865,1865,1865,1865])
    heading(doc,"3.2 原始证据",2)
    code(doc,"outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/dominance_audit.json")
    code(doc,"outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json")
    heading(doc,"3.3 失败/反例",2)
    para(doc,"高未标注率不是 Pareto 规则过严的证据。真正 FP/TP 权衡冲突仅约 7.3%；约 35% 的候选对是证据签名相同，说明探针分辨率不足。")
    heading(doc,"3.4 下一步决策",2)
    para(doc,"不放宽 dominance、不调 scalar 权重制造标签。若未来重启，应增加正交的信号重命名、位宽/参数缩放、多阶段协议状态、长窗口和同根因 mutant 证据。")

    heading(doc,"4. Disagreement-guided 是否发现新 failure modes",1)
    heading(doc,"4.1 结论",2)
    para(doc,"没有。两种 policy 覆盖同一组 transformation families；disagreement-guided 主要在既有类别内重新采样。")
    add_table(doc,["指标","Random","Disagreement","差异"],[["Dominance pairs","483","484","+1"],["Unique FP/TP signatures","71","72","+1"],["Distinguishing cells","30.17%","30.38%","+0.21pp"],["Unique distinguishing probes","64.06%","64.38%","+0.31pp"],["Frozen SCS@1","0%","0%","无提升"]],[3300,1800,2100,2160])
    heading(doc,"4.2 原始证据",2)
    code(doc,"outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json → probe_policy")
    heading(doc,"4.3 失败/反例",2)
    para(doc,"例如 stall/backpressure distinguishing incidences 从 271 增至 323，但这是同类内部加密，不是新 failure family。")
    heading(doc,"4.4 下一步决策",2)
    para(doc,"应先扩大 probe generator 的 failure-family 支持，再比较 acquisition policy；否则 disagreement 只能从同一有限池中挑选近重复样本。")

    heading(doc,"5. 训练收益：模板记忆还是行为抽象",1)
    heading(doc,"5.1 结论",2)
    para(doc,"修正 AST 协议后，结构合法性和可执行性显著改善，但冻结 OOD 行为指标没有同步改善。这更支持语法/时序模板记忆，而不是行为抽象。")
    add_table(doc,["Split","Compile","SCS@1","Family Recall","Fixed-Safe","Target Detect"],[["unseen parent","100%","0%","0%","2.86%","60%"],["unseen bug family","100%","0%","0%","40%","52%"]],[1900,1400,1400,1600,1530,1530])
    heading(doc,"5.2 原始证据",2)
    code(doc,"outputs/behavioral_preference_pilot_v2/frozen_top1_ast_v2/execution_evaluation_v1/frozen_top1_metrics.json")
    code(doc,"outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json")
    code(doc,"outputs/phase_b_ood_eval_v1/records/case233_onehot_addr_legal_v1_from_case137_prim_onehot_addr_false_positive/evaluation.json")
    heading(doc,"5.3 分层验证与反例",2)
    add_table(doc,["分层","可否判断","冻结证据"],[["信号重命名","不可判断","无显式 signal-renaming stratum"],["参数/位宽变化","不可判断","无显式 parameter/width stratum"],["Unseen family","可以","Family Recall=0%，不支持行为抽象"]],[2300,1800,5260])
    heading(doc,"5.4 下一步决策",2)
    para(doc,"论文必须拆分“可执行性收益”和“行为泛化收益”：前者成立，后者未成立。Compile rate 或 smoke pass 不能替代 Frozen SCS@1。")

    heading(doc,"6. 行为结果签名与文字诊断监督",1)
    heading(doc,"6.1 结论",2)
    para(doc,"FP/TP 与 antecedent/non-vacuity 组成的行为签名，更适合作为主监督，因为它直接对应可重放的执行结果；文字 failure label 更适合作为辅助解释变量。")
    heading(doc,"6.2 原始证据",2)
    add_table(doc,["Repair 观察","数量"],[["Selected cases","8"],["Buggy detection improved","1"],["Antecedent hit improved","1"],["Introduced fixed FP","1"],["Introduced heldout failure","1"],["Candidate-level buggy improve with FP","7"]],[7000,2360])
    code(doc,"outputs/019ed9f6-87cf-7830-adb8-595fe2ae140d/antecedent_repair_data/antecedent_repair_summary.json")
    heading(doc,"6.3 失败/反例",2)
    para(doc,"现有 repair 结果只能说明文字诊断与修复行为的关联较弱，不能严格证明文字诊断没有因果作用。因果识别需要固定行为证据，仅随机交换 correct/wrong diagnosis。")
    heading(doc,"6.4 下一步决策",2)
    bullet(doc,"以可执行行为签名作为主监督和审计依据。")
    bullet(doc,"文字 diagnosis 只作为辅助输入，不得覆盖执行结果。")
    bullet(doc,"若未来继续，使用随机 diagnosis-label intervention 检验其增量因果作用。")
    bullet(doc,"依据当前 NO-GO，不直接扩大至 3,000–10,000 pairs。")

    heading(doc,"7. 总体结论与论文表述边界",1)
    label(doc,"正式结论","实验工程闭环已经完成且可一键复查；科学假设未达到预设 go gate。模型主要学到结构合法性与局部模板，没有证据证明首次 Top-1 的跨行为分布泛化变好。",True)
    add_table(doc,["可以主张","不能主张"],[["240 条候选均有可执行证据包","行为偏好已改善 frozen Top-1"],["严格 dominance 数据可重放、可审计","disagreement-guided 发现了新 failure family"],["AST 协议解决自由文本/编译退化","已验证 signal-renaming 和 parameter robustness"],["Unseen-family 结果为正式 NO-GO","文字 diagnosis 已被证明没有因果作用"]],[4680,4680])

    heading(doc,"附录 A：复查命令",1)
    code(doc,'Set-Location -LiteralPath "D:\\AssertionForge-main1"\n$Python = "C:\\Users\\USER\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe"\n& $Python "src\\analyze_behavioral_generalization_evidence.py" 2>&1 | Tee-Object -FilePath "outputs\\behavioral_posthoc_analysis_v1\\behavioral_generalization_analysis.log"')
    code(doc,'powershell -NoProfile -ExecutionPolicy Bypass -File scripts\\review_behavioral_preference_closed_loop.ps1')
    heading(doc,"附录 B：证据索引",1)
    for path in [
        "outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.json",
        "outputs/behavioral_posthoc_analysis_v1/behavioral_generalization_analysis.log",
        "outputs/behavioral_preference_pilot_v1/behavioral_probes_v3/probe_manifest.json",
        "outputs/behavioral_preference_pilot_v1/dominance_pairs_v3/dominance_audit.json",
        "outputs/behavioral_preference_pilot_v2/frozen_top1_ast_v2/execution_evaluation_v1/frozen_top1_metrics.json",
        "outputs/phase_b_ood_eval_v1/phase_b_ood_metrics_and_decision.json",
        "outputs/behavioral_preference_closed_loop_final_v1/phase_b_final_manifest.json",
        "outputs/behavioral_preference_closed_loop_final_v1/evaluation_artifact_hashes.json",
    ]: bullet(doc,path)
    para(doc,"注：本报告为冻结结果之上的描述性 post-hoc 分析。所有新增文件位于独立 behavioral_posthoc_analysis_v1 目录，不覆盖 Pilot v1、Pilot v2 或 Phase B 证据。",italic=True,color=GRAY)
    OUT.parent.mkdir(parents=True,exist_ok=True); doc.save(OUT); print(OUT)

if __name__=="__main__": build()
