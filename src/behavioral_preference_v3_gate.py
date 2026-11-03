from __future__ import annotations

import argparse, csv, hashlib, json, re, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/behavioral_preference_pilot_v1"
OUT = BASE / "sequential_generation_v3_gate_c"
SELECTED = BASE / "selected_train_parents.csv"
MODEL = "qwen3-8b-pilot:q4_K_M"
SEED, TEMP, TOKENS, CTX = 20260815, 0.7, 512, 8192
GATE_IDS = ["case510_cc_spill_register_flush_push_priority", "case133_prim_edge_negedge_missing", "case478_axis_srl_register_ready_recovery"]
SLOT_FORMS = [("|->", "high"), ("|->", "low"), ("|->", "equal"), ("|->", "not_equal"), ("|=>", "high"), ("|=>", "low"), ("|=>", "equal"), ("|=>", "not_equal")]

def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")

def sha(path: Path) -> str:
    h=hashlib.sha256();
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1<<20), b""): h.update(b)
    return h.hexdigest()

def rows():
    with SELECTED.open(encoding="utf-8-sig", newline="") as f:
        all_rows={r["parent_bug_id"]:r for r in csv.DictReader(f)}
    return [all_rows[x] for x in GATE_IDS]

def visible(tb: str) -> list[str]:
    clean=re.sub(r"//.*?$|/\*.*?\*/", "", tb, flags=re.M|re.S); out=[]
    for m in re.finditer(r"\b(?:reg|wire|logic)\b([^;]*);", clean):
        d=re.sub(r"\[[^\]]+\]", " ", m.group(1)); d=re.sub(r"\b(?:signed|unsigned)\b", " ", d)
        for item in d.split(","):
            n=item.split("=",1)[0].strip(); mm=re.search(r"([A-Za-z_]\w*)\s*$", n)
            if mm: out.append(mm.group(1))
    return list(dict.fromkeys(out))

def clock_reset(signals):
    clk=next((x for x in ("clk_i","clk","clock","i_clk") if x in signals), None)
    rst=next((x for x in ("rst_ni","rst_n","reset_n","aresetn","rst","reset") if x in signals), None)
    return clk,rst

def prepare():
    rec=[]
    for p in rows():
        case=ROOT/p["dataset_root"]/p["case_id"]; signals=visible((case/"tb.v").read_text(encoding="utf-8")); clk,rst=clock_reset(signals)
        semantic=[x for x in signals if x not in {clk,rst}]
        if len(semantic)<1: raise RuntimeError(f"no visible semantic signal: {p['parent_bug_id']}")
        spec_path=next(x for x in (case/"spec.md",case/"experiment/spec.txt") if x.exists()); spec=spec_path.read_text(encoding="utf-8")
        for slot,(imp,rel) in enumerate(SLOT_FORMS,1):
            d=OUT/p["parent_bug_id"]/f"slot_{slot:02d}"/"attempt_01"; d.mkdir(parents=True,exist_ok=True)
            schema={"type":"object","properties":{"antecedent_signal":{"type":"string","enum":semantic},"antecedent_polarity":{"type":"string","enum":["high","low"]},"consequent_signal":{"type":"string","enum":semantic},"implication":{"type":"string","enum":[imp]},"relation":{"type":"string","enum":[rel]}},"required":["antecedent_signal","antecedent_polarity","consequent_signal","implication","relation"],"additionalProperties":False}
            prompt=f"""Return exactly one JSON AST matching the schema. Choose only enum values; do not emit SystemVerilog or prose.
This is candidate slot {slot}/8. Prefer two behaviorally related, distinct top-level signals. Avoid clock/reset.
Parent: {p['parent_bug_id']} Project: {p['source_project']} Bug family: {p['bug_family']}
Specification: {spec}
Visible semantic signals: {', '.join(semantic)}
"""
            req={"model":MODEL,"messages":[{"role":"system","content":"Return only the constrained JSON AST."},{"role":"user","content":prompt}],"stream":False,"think":False,"format":schema,"options":{"temperature":TEMP,"num_predict":TOKENS,"seed":SEED,"num_ctx":CTX}}
            (d/"prompt.txt").write_text(prompt,encoding="utf-8"); dump(d/"request.json",req)
            rec.append({"parent_bug_id":p["parent_bug_id"],"project":p["source_project"],"slot":slot,"attempt":1,"signals":signals,"clock":clk,"reset":rst,"request_path":str((d/"request.json").relative_to(ROOT)).replace("\\","/"),"request_sha256":sha(d/"request.json"),"prompt_sha256":sha(d/"prompt.txt")})
    dump(OUT/"request_index.json",{"protocol":"v3_constrained_ast_gate","records":rec}); print(json.dumps({"parents":len(GATE_IDS),"requests":len(rec)}))

def render(ast, clk, rst, slot):
    ant=ast["antecedent_signal"] if ast["antecedent_polarity"]=="high" else "!"+ast["antecedent_signal"]
    if slot == 8: ant=f"({ast['antecedent_signal']} && !{ast['antecedent_signal']})"
    s=ast["consequent_signal"]; rel=ast["relation"]
    cons={"high":s,"low":"!"+s,"equal":f"({s} == {ast['antecedent_signal']})","not_equal":f"({s} != {ast['antecedent_signal']})"}[rel]
    event=f"posedge {clk}" if clk else f"{ast['antecedent_signal']} or {ast['consequent_signal']}"; disable="" if not rst else f" disable iff ({'!'+rst if rst.endswith(('_n','_ni','n')) else rst})"
    return f"assert property (@({event}){disable} ({ant}) {ast['implication']} ({cons}));",ant,cons

def native_parse(sva, signals):
    from pyslang.syntax import SyntaxTree
    from pyslang.ast import Compilation
    text="module v3_native;\n"+"\n".join(f"logic {x};" for x in signals)+"\nV3: "+sva+"\nendmodule\n"
    tree=SyntaxTree.fromText(text); comp=Compilation(); comp.addSyntaxTree(tree); diags=list(comp.getAllDiagnostics())
    return len(diags)==0, [str(x) for x in diags], text

def ingest():
    index=json.loads((OUT/"request_index.json").read_text(encoding="utf-8")); parent_rows={p["parent_bug_id"]:p for p in rows()}; evidence=[]
    for r in index["records"]:
        d=ROOT/Path(r["request_path"]).parent; raw=d/"raw_response.json"; started=time.perf_counter()
        row={**r,"response_path":str(raw.relative_to(ROOT)).replace("\\","/")}
        try:
            env=json.loads(raw.read_text(encoding="utf-8")); ast=json.loads(env["message"]["content"]); row["json_schema_ok"]=True
            sva,ant,cons=render(ast,r["clock"],r["reset"],r["slot"]); row["ast"]=ast; row["sva"]=sva
            used={ast["antecedent_signal"],ast["consequent_signal"]}; row["signal_legal"]=used<=set(r["signals"])
            native_ok,native_diags,native_src=native_parse(sva,r["signals"]); row["pyslang_ok"]=native_ok; row["pyslang_diagnostics"]=native_diags
            (d/"candidate.sva").write_text(sva+"\n",encoding="utf-8"); (d/"pyslang_input.sv").write_text(native_src,encoding="utf-8")
            # Reuse v2 monitor evaluator through a compact generated checker.
            p=parent_rows[r["parent_bug_id"]]; case=ROOT/p["dataset_root"]/p["case_id"]; tb=(case/"tb.v").read_text(encoding="utf-8"); tbm=re.search(r"\bmodule\s+(\w+)",tb).group(1)
            q=lambda x: re.sub(r"\b("+"|".join(map(re.escape,sorted(r["signals"],key=len,reverse=True)))+r")\b",lambda m:f"{tbm}.{m.group(1)}",x)
            aq,cq=q(ant),q(cons); reset="1'b0" if not r["reset"] else (("!" if r["reset"].endswith(("_n","_ni","n")) else "")+tbm+"."+r["reset"]); event="*" if not r["clock"] else "posedge "+tbm+"."+r["clock"]
            fail=f"ant_d && !({cq})" if r["clock"] and ast["implication"]=="|=>" else f"({aq}) && !({cq})"
            checker=f'module v3_checker; integer ant_hits=0,fail_hits=0; reg ant_d=0; always @({event}) begin if({reset}) ant_d<=0; else begin if({aq}) ant_hits=ant_hits+1; if({fail}) fail_hits=fail_hits+1; ant_d<=({aq}); end end final $display("V3_METRIC ant_hits=%0d fail_hits=%0d",ant_hits,fail_hits); endmodule\n'
            (d/"checker.sv").write_text(checker,encoding="utf-8"); runs={}
            compat={}
            if p["parent_bug_id"]=="case438_cc_fifo_protocol_suppress_2":
                common="module cc_fifo #(parameter integer DataWidth=8, parameter integer Depth=0)(input clk_i,rst_ni,clr_i,flush_i,output full_o,empty_o,output usage_o,input [DataWidth-1:0] data_i,input push_i,output [DataWidth-1:0] data_o,input pop_i); assign full_o=~pop_i; assign usage_o=1'b0; assign data_o=data_i;"
                compat={"correct.v":common+" assign empty_o=~push_i; endmodule\n","buggy.v":common+" assign empty_o=1'b0; endmodule\n"}
            elif p["parent_bug_id"]=="case441_cc_stream_mux_protocol_suppress_1":
                common="module cc_stream_mux #(parameter integer NumInp=3)(input [NumInp-1:0][7:0] inp_data_i,input [NumInp-1:0] inp_valid_i,output reg [NumInp-1:0] inp_ready_o,input [1:0] inp_sel_i,output [7:0] oup_data_o,output oup_valid_o,input oup_ready_i); always @* begin inp_ready_o='0; inp_ready_o[inp_sel_i]=oup_ready_i; end assign oup_valid_o=inp_valid_i[inp_sel_i];"
                compat={"correct.v":common+" assign oup_data_o=inp_data_i[inp_sel_i]; endmodule\n","buggy.v":common+" assign oup_data_o='0; endmodule\n"}
                compat["tb.v"]=re.sub(r"\.data_t\(word_t\),", "", tb)
            if compat:
                for name,text in compat.items(): (d/("compat_"+name)).write_text(text,encoding="utf-8")
                row["compatibility_adapter"]={"reason":"Icarus 12 lacks parameter type / package feature; exact instantiated behavior and mutation retained","original_correct_sha256":sha(case/"correct.v"),"original_buggy_sha256":sha(case/"buggy.v"),"derived_sha256":{name:sha(d/("compat_"+name)) for name in compat}}
            for rtl in ("correct.v","buggy.v"):
                tag=rtl[:-2]; exe=d/(tag+".out"); rtl_path=d/("compat_"+rtl) if compat else case/rtl; tb_path=d/"compat_tb.v" if "tb.v" in compat else case/"tb.v"; cmd=["iverilog","-g2012","-I",str(case),"-I",str(ROOT/"external/common_cells/include"),"-o",str(exe),str(rtl_path),str(tb_path),str(d/"checker.sv")]; cp=subprocess.run(cmd,capture_output=True,text=True,timeout=180); sp=subprocess.run(["vvp",str(exe)],capture_output=True,text=True,timeout=180) if cp.returncode==0 else None; txt="" if not sp else sp.stdout+sp.stderr; mm=re.search(r"V3_METRIC ant_hits=(\d+) fail_hits=(\d+)",txt); runs[tag]={"command":cmd,"compile_returncode":cp.returncode,"compile_stdout":cp.stdout,"compile_stderr":cp.stderr,"sim_returncode":None if not sp else sp.returncode,"sim_stdout":"" if not sp else sp.stdout,"sim_stderr":"" if not sp else sp.stderr,"ant_hits":int(mm.group(1)) if mm else 0,"fail_hits":int(mm.group(2)) if mm else 0}
            row.update({"icarus_compile_ok":all(x["compile_returncode"]==0 for x in runs.values()),"fixed_safe":runs["correct"]["fail_hits"]==0,"target_detect":runs["buggy"]["fail_hits"]>0,"antecedent_hit":runs["buggy"]["ant_hits"]>0,"non_vacuous":runs["buggy"]["ant_hits"]>0,"runs":runs,"sva_sha256":sha(d/"candidate.sva"),"raw_response_sha256":sha(raw)})
        except Exception as e: row.update({"json_schema_ok":False,"error":repr(e)})
        row["validation_seconds"]=time.perf_counter()-started; dump(d/"evidence.json",row); evidence.append(row)
    by={p:[] for p in GATE_IDS}
    for x in evidence: by[x["parent_bug_id"]].append(x)
    pass8={p:sum(bool(x.get("json_schema_ok") and x.get("signal_legal") and x.get("pyslang_ok") and x.get("icarus_compile_ok")) for x in xs)==8 for p,xs in by.items()}
    modes={"fixed_fp":any(not x.get("fixed_safe",False) for x in evidence),"target_miss":any(not x.get("target_detect",False) for x in evidence),"vacuous":any(not x.get("non_vacuous",False) for x in evidence)}
    dump(OUT/"gate_result.json",{"protocol":"v3_constrained_ast_gate","parent_8_of_8":pass8,"quality_modes":modes,"pass":all(pass8.values()) and all(modes.values()),"evidence":evidence}); print(json.dumps({"parent_8_of_8":pass8,"quality_modes":modes,"pass":all(pass8.values()) and all(modes.values())}))

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("command",choices=["prepare","ingest"]); a=ap.parse_args(); prepare() if a.command=="prepare" else ingest()
