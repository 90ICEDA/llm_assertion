"""Pre-execution clarification only; refuse to amend after any model result."""
from run_contract_v2 import OUT,read,dump,sha,rel,freeze,stamp
from contract_v2_spec import contract
from pathlib import Path
assert not list((OUT/'model_calls').rglob('result.json')),'Cannot alter a protocol after observing model outcomes'
p=OUT/'protocol_freeze.json';old=read(p)
archive=OUT/'protocol_preexecution_v20.json';assert not archive.exists();dump(archive,old)
protocol=read(OUT/'protocol.json')
protocol['version']='2.1'
protocol['acceptance_scope']='finite frozen scenarios; exercise all declared scenario branches, but require assertion antecedent witnesses only on required_assertion_trigger_branches. Negative/legal controls and reset cancellation need not trigger a target antecedent. All target components activated, no misses/FP, no unknown/spec ambiguity for complete pass.'
protocol['refinement']+=' Baseline delay=1 already retains an antecedent bit: refinement collision search therefore starts at full one-cycle port history (a conservative capability superset), not memoryless history=0.'
protocol['preexecution_amendment']={'time':stamp(),'reason':'static protocol review distinguishes negative controls from necessary antecedent branches, and accounts for the one-bit delay=1 memory before declaring an observation collision; no model calls or supplemental outcomes observed'}
dump(OUT/'protocol.json',protocol)
for folder in (OUT/'frozen').iterdir():
    if folder.is_dir():dump(folder/'contract.json',contract(folder.name))
dump(p,{'time':stamp(),'preexecution_previous_freeze':rel(archive),'hashes':{name:sha(Path(__file__).resolve().parents[1]/name) for name in old['hashes']}})
