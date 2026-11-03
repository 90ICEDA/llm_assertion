"""Import previously confirmed prose contracts, never candidate-derived facts."""
import copy
from pathlib import Path
from repair_contract_cases import definition, sources
from .contracts import ROOT, file_hash, read, record, validate, write


def source(path, location, basis):
    path = Path(path)
    return dict(path=str(path.resolve()), sha256=file_hash(path), location=location, basis=basis)


def example(key):
    d = definition(key)
    fixed, buggy = sources(d)
    spec = (ROOT / "rtl_cases_real_scale120/case101_prim_onehot_multihot_suppressed/STIMULUS_NOTES.md" if key == "onehot"
            else ROOT / "rtl_cases_real_scale210_independent/case438_cc_fifo_protocol_suppress_2/spec.md")
    env = [source(ROOT / "scripts/contract_v2_spec.py", "contract(): legal_inputs, reset_cancellation",
                  "Imported confirmed experiment interface: unsigned samples; FIFO must hold push/data while stalled until acceptance or reset.")]
    signals = {**d["inputs"], **d["outputs"], d["clk"]: 1, d["rst"]: 1}
    tests = sorted(str(p) for p in (fixed.parent if key == "onehot" else spec.parent).glob("tb*.v"))
    hashes = {str(p): file_hash(p) for p in [fixed, buggy, spec, ROOT / "scripts/contract_v2_spec.py", *map(Path, tests)]}
    return record("CaseInput", case_id=key, bug_description=d["obligation"], top_module=d["module"],
        rtl={v: dict(sources=[str(p)], include_dirs=[str(p.parent), str(ROOT / "external/common_cells/include")], defines=[])
             for v, p in [("fixed", fixed), ("buggy", buggy)]}, existing_tests=tests,
        parameters={"DataWidth": 8, "Depth": 0} if key == "fifo" else {"OneHotWidth": 4, "StrictCheck": 1},
        clock=dict(signal=d["clk"], event="posedge_pre_NBA", input_drive="negedge"),
        reset=dict(signal=d["rst"], active=0, cancel_pending=True, initial_samples=2),
        signals=dict(inputs=d["inputs"], outputs=d["outputs"], mapping={n: {"buggy": n, "fixed": n, "width": w} for n, w in signals.items()}),
        environment=env, tool_config=dict(backend="iverilog", timeout_seconds=30, iverilog="iverilog", vvp="vvp", jasper="jg", model_url="http://127.0.0.1:11434"),
        input_hashes=hashes, obligation_source=str(spec), limitations=[
            "Existing artificial RTL mutation; no historical repair commit or universal correctness claim.",
            "Restricted sampled monitor, not native concurrent SVA or formal proof.",
            *(["Depth=0 compatibility RTL only; upstream parameter-type RTL not executed; no occupancy/storage/overlap claims.",
               "Upstream full_write/empty_read and Depth>0 assertions are not the selected adapter interface.",
               "Data/full/usage are observed, not newly asserted DUT obligations."] if key == "fifo" else [])])


def load_case(path):
    c = read(path)
    if "correct" in c.get("rtl", {}):
        if "fixed" in c["rtl"]:
            raise ValueError("Ambiguous correct/fixed RTL")
        c["rtl"]["fixed"] = c["rtl"].pop("correct")
    validate("CaseInput", c)
    for p, h in c["input_hashes"].items():
        if file_hash(p) != h:
            raise ValueError("Input changed: " + p)
    for v in c["rtl"].values():
        for p in v["sources"]:
            if p not in c["input_hashes"]:
                raise ValueError("Unhashed RTL: " + p)
    expected = definition(c["case_id"])
    if c["clock"]["signal"] != expected["clk"] or c["reset"]["signal"] != expected["rst"] or c["reset"]["initial_samples"] != 2:
        raise ValueError("Unsupported clock/reset initialization")
    if c["top_module"] != expected["module"] or c["signals"]["inputs"] != expected["inputs"] or c["signals"]["outputs"] != expected["outputs"]:
        raise ValueError("Unsupported interface; adapter supports pinned onehot/FIFO ports")
    if c["parameters"] != ({"Depth": 0, "DataWidth": 8} if c["case_id"] == "fifo" else {"OneHotWidth": 4, "StrictCheck": 1}):
        raise ValueError("Unsupported parameters; no implicit Depth>0 semantics")
    for n, m in c["signals"]["mapping"].items():
        if m["buggy"] != n or m["fixed"] != n:
            raise ValueError("Non-identity signal mapping requires a new adapter")
    expected_widths = {**expected["inputs"], **expected["outputs"], expected["clk"]: 1, expected["rst"]: 1}
    if {n: m["width"] for n, m in c["signals"]["mapping"].items()} != expected_widths:
        raise ValueError("Signal mapping widths changed")
    for p in [c["obligation_source"], *c["existing_tests"], *[e["path"] for e in c["environment"]]]:
        if p not in c["input_hashes"]:
            raise ValueError("Unhashed specification/test/environment: " + p)
    for e in c["environment"]:
        if e["sha256"] != c["input_hashes"][e["path"]]:
            raise ValueError("Environment source hash mismatch")
    return c


def metadata(c):
    return dict(key=c["case_id"], module=c["top_module"], clk=c["clock"]["signal"], rst=c["reset"]["signal"],
                inputs=c["signals"]["inputs"], outputs=c["signals"]["outputs"],
                observation_base=list(c["signals"]["inputs"]) + list(c["signals"]["outputs"]))


def extract(c):
    key = c["case_id"]
    definitions = [("multihot_detect", "popcount(oh_i) > 1", "err_o == 1", ["multihot"], "Multihot reports error at this sample.")] if key == "onehot" else [
        ("empty_when_idle", "!push_i", "empty_o == 1", ["idle"], "An idle Depth=0 interface is empty."),
        ("nonempty_when_present", "push_i", "empty_o == 0", ["present_stalled", "present_accepted"], "Presented data makes Depth=0 nonempty, including backpressure.")]
    result = []
    for ident, trigger, response, branches, description in definitions:
        result.append(record("Obligation", obligation_id=key + "." + ident, description=description,
            scope="confirmed repair-target behavior only", parameters=c["parameters"], branches=branches,
            trigger=trigger, response=response, capture="Same pre-NBA sample. FIFO item identity starts at presentation; hold payload through stall.",
            clock=c["clock"], latency=dict(min=0, max=0), reset=c["reset"],
            exceptions=["No obligation during active reset", *(["zero/onehot err_o may be asserted by address/enable checks"] if key == "onehot" else [])],
            signals=c["signals"]["mapping"], input_constraints=c["environment"],
            sources=[source(c["obligation_source"], "Spec / Behavioral specification", "Independent case prose predates candidates"),
                     source(ROOT / "scripts/repair_contract_cases.py", "definition('" + key + "')", "Previously confirmed scoped obligation imported unchanged")],
            confirmation="imported_confirmed", initialization="Two active-low reset samples; no cross-reset obligations",
            judge=dict(reference="repair_regression.evidence.adjudicate", version="1.0", sha256=file_hash(Path(__file__).with_name("evidence.py")))))
    return result


def freeze(c, out):
    frozen = copy.deepcopy(c)
    paths = {}
    for i, (p, h) in enumerate(c["input_hashes"].items()):
        target = out / "inputs" / (str(i) + "_" + Path(p).name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(p).read_bytes())
        paths[p] = str(target.resolve())
    for variant in frozen["rtl"].values():
        variant["sources"] = [paths[p] for p in variant["sources"]]
    import re
    for variant in frozen["rtl"].values():
        for p in variant["sources"]:
            if re.search(r'^\s*`include', Path(p).read_text(), re.M):
                raise ValueError("External includes need an explicit dependency snapshot adapter")
    frozen["existing_tests"] = [paths[p] for p in c["existing_tests"]]
    frozen["obligation_source"] = paths[c["obligation_source"]]
    for e in frozen["environment"]:
        e["path"] = paths[e["path"]]
    frozen["input_hashes"] = {paths[p]: h for p, h in c["input_hashes"].items()}
    write(out / "case.original.json", c)
    write(out / "case.json", frozen)
    return frozen
