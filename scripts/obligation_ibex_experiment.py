"""Real-history Ibex #54 assertion generation/refinement, separate from artificial cases.

Private reference derives flag obligations from published RV32C encodings.
No patch, corrected RTL, private reference or holdout is sent to the model.
"""
import argparse
import collections
import copy
import json
from pathlib import Path
import random
import shutil
import obligation_continuation as cont
import obligation_continuation_experiment as experiment
from obligation_continuation import x, iso, ref, public, PRIOR

BASE_MONITOR=x.monitor
BASE_ORDINARY=x.policy.ordinary
BASE_DISAGREEMENT=x.policy.disagreement
BASE_GUIDED=x.policy.guided
HISTORY=PRIOR/'historical_screening/ibex_54'


def encode(family,rd,imm):
    if family=='li':return (2<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1
    if family=='lui':return (3<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1
    if family in ('srli','srai'):return (4<<13)|((imm>>5)<<12)|((family=='srai')<<10)|((rd%8)<<7)|((imm&31)<<2)|1
    return ((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|2


def decode_obligation(insn):
    q=insn&3;funct=(insn>>13)&7;rd=(insn>>7)&31;imm=((insn>>12)&1)*32+((insn>>2)&31)
    if q==1 and funct==2:return 'c_li',0,'hint' if rd==0 else 'normal'
    if q==1 and funct==3:return 'c_lui',int(imm==0),'reserved_zero' if imm==0 else 'hint' if rd==0 else 'normal'
    if q==1 and funct==4 and ((insn>>10)&3) in (0,1):
        return ('c_srai' if (insn>>10)&1 else 'c_srli'),int(imm>=32),'disabled_custom' if imm>=32 else 'hint' if imm==0 else 'normal'
    if q==2 and funct==0:return 'c_slli',int(imm>=32),'disabled_custom' if imm>=32 else 'hint' if imm==0 or rd==0 else 'normal'
    raise ValueError('outside frozen historical scope')


def monitor(d,trace):
    if d['key']!='ibex':return BASE_MONITOR(d,trace)
    events=[];epoch=0;prefix=True
    for r in trace:
        if not r[d['rst']]:epoch+=1;prefix=True;continue
        family,illegal,branch=decode_obligation(r['instr_i'])
        checks=[]
        for name,expected,actual in [(family+'.legality',illegal,r['illegal_instr_o']),('compressed_flag',1,r['is_compressed_o'])]:
            checks.append(dict(obligation=name,expected=expected,actual=actual,trigger_cycle=r['cycle'],due_cycle=r['cycle'],
                transaction_id=f'ibex:e{epoch}:t{r["cycle"]}:i{r["instr_i"]:04x}',branch=branch,conditional=False,passed=expected==actual))
        legal=all(c['passed'] for c in checks)
        events.append(dict(cycle=r['cycle'],checks=checks,legal_prefix=prefix and legal,first_violation=prefix and not legal,
            classification='scoped_legal_sample' if legal else 'target_violation'))
        prefix=prefix and legal
    return dict(events=events,pending=[],cancelled=[],scope='RV32C flag behavior for five instruction families; no decoder data claim',full_spec_resolved=True)


def rows_for(values,reset_position=None):
    rows=[]
    for i,v in enumerate(values):rows.append(dict(cycle=i,stimulus_id=f'instruction:{i}',rst_ni=int(i>=2 and i!=reset_position),instr_i=v))
    return rows


def ordinary(d,seed):
    if d['key']!='ibex':return BASE_ORDINARY(d,seed)
    rng=random.Random(seed);values=[]
    for _ in range(24):
        family=rng.choice(('li','lui','srli','srai','slli'));rd=rng.randrange(16)
        imm=rng.randrange(8)+(32 if rng.randrange(2) else 0)
        values.append(encode(family,rd,imm))
    return rows_for(values)


def disagreement(d,seed,incumbent):
    if d['key']!='ibex':return BASE_DISAGREEMENT(d,seed,incumbent)
    if incumbent is None:return ordinary(d,seed)
    rows=copy.deepcopy(incumbent);fresh=ordinary(d,seed);rng=random.Random(seed)
    for _ in range(6):
        i=rng.randrange(2,24);rows[i]['instr_i']=fresh[i]['instr_i']
    return rows


def guided(d,seed,step):
    if d['key']!='ibex':return BASE_GUIDED(d,seed,step)
    rng=random.Random(seed);families=('li','lui','srli','srai','slli');values=[encode('li',1,1)]*2
    for i in range(22):
        family=families[(i+step)%5]
        if i%4==3:rd=rng.randrange(1,16);imm=rng.randrange(1,8)
        else:rd=0 if family in ('li','lui','slli') else rng.randrange(8);imm=rng.randrange(1,8) if family=='lui' else 0
        values.append(encode(family,rd,imm))
    return rows_for(values)


def install():
    x.monitor=monitor;x.policy.ordinary=ordinary;x.policy.disagreement=disagreement;x.policy.guided=guided
    experiment.KEYS=('ibex',);experiment.BLOCK_NAME='historical_formal'
    cont.configure()


def prepare():
    block=x.OUT/'historical_formal';block.mkdir(exist_ok=False)
    folder=x.OUT/'frozen/ibex';folder.mkdir(exist_ok=False)
    d=dict(key='ibex',parent_bug_id='lowRISC/ibex#54',provenance='real_historical_fix',module='ibex_case',clk='clk_i',rst='rst_ni',
        inputs=dict(instr_i=16),outputs=dict(is_compressed_o=1,illegal_instr_o=1),observation_base=['instr_i','is_compressed_o','illegal_instr_o'])
    x.dump(folder/'definition.json',d)
    wrapper='\nmodule ibex_case(input wire clk_i,input wire rst_ni,input wire [15:0] instr_i,output wire is_compressed_o,output wire illegal_instr_o);\nwire [31:0] unused_decoded;\nibex_compressed_decoder dut(.instr_i({16\'b0,instr_i}),.instr_o(unused_decoded),.is_compressed_o(is_compressed_o),.illegal_instr_o(illegal_instr_o));\nendmodule\n'
    for variant,revision in [('correct','after'),('buggy','before')]:
        source=(HISTORY/revision/'ibex_defines.sv').read_text()+'\n'+(HISTORY/revision/'ibex_compressed_decoder.sv').read_text()+wrapper
        (folder/(variant+'.v')).write_text(source)
    contract=dict(scope='Real Ibex #54 RV32C compressed legality flags; five families only. Combinational decoder: no design clock/reset; harness clk/reset only sample transactions and initialize checkers. Delay zero is appropriate.',
        sources=['https://github.com/lowRISC/ibex/issues/51','https://docs.riscv.org/reference/isa/v20260120/unpriv/c-st-ext.html'],
        encoding='16-bit instruction; quadrant=bits[1:0], funct3=bits[15:13], rd=bits[11:7], imm6={bit12,bits6:2}. All selected instructions have is_compressed_o=1.',
        obligations=[
            'quadrant1 funct3=2: C.LI legal for every imm and rd, including rd=0 HINT.',
            'quadrant1 funct3=3: C.LUI/ADDI16SP illegal if imm6=0, otherwise legal including rd=0 HINT and rd=2 ADDI16SP.',
            'quadrant1 funct3=4, bits11:10=0/1: C.SRLI/C.SRAI. bit12=0 is legal including shift=0 HINT. bit12=1 uses a custom extension not enabled in this historical RV32 configuration: illegal.',
            'quadrant2 funct3=0: C.SLLI. bit12=0 is legal including rd=0 or shift=0 HINT; bit12=1 custom extension disabled: illegal.'],
        boundary='Do not unconditionally require illegal_instr_o=0: reserved immediate-zero C.LUI and disabled-custom shift encodings are illegal.',
        limitations='Decoded 32-bit payload not exposed to generator in this scoped flag experiment; prior independent boundary regression separately checks decoded values. Not full ISA verification.')
    x.dump(folder/'public_contract.json',contract);x.dump(folder/'contract.json',dict(contract,legal_inputs='Only the five scoped opcode families, no X/Z; arbitrary ordering; combinational transactions independent'))
    x.dump(folder/'spec_sources.json',dict(urls=contract['sources'],history_source=x.rel(HISTORY/'source.json'),
        public_material='paraphrased issue intent, architecture instruction encoding/legality, ports; no patch/post-fix RTL/tests'))
    original=x.read(HISTORY/'reproduction.json');assert original['admitted']
    x.dump(block/'history_lineage.json',dict(source=original['source'],reproduction=x.rel(HISTORY/'reproduction.json'),
        patch_verification=x.rel(HISTORY/'patch_validation/result.json'),
        source_hashes={x.rel(p):x.sha(p) for p in [HISTORY/'fix.patch',HISTORY/'benchmark_tb.sv',*HISTORY.glob('before/*.sv'),*HISTORY.glob('after/*.sv')]},
        generator_visible_files=[x.rel(folder/'public_contract.json')],patch_or_fixed_RTL_visible=False))
    install()
    common=[guided(d,740031,0),ordinary(d,740039)]
    x.dump(block/'common/ibex.json',common)
    # New low-16-bit encodings, not upper-bit aliases or renamed prior tests.
    # Development public domain uses imm low five bits 0..7 and rd 0..15.
    values=[encode('slli',0,s) for s in range(8,32)]
    values += [encode('lui',rd,8+(rd%16)) for rd in range(16,32)]
    values += [encode('srli',rd,s) for rd in range(8) for s in (9,17,25)]
    old_values={r['instruction'] for r in x.read(HISTORY/'boundary_vectors.json')}
    assert not set(values)&old_values
    hidden=[]
    for i in range(6):
        rng=random.Random(862713+i*113);ordered=values.copy();rng.shuffle(ordered)
        hidden.append(rows_for([encode('li',1,1)]*2+ordered[:30],12+i))
    x.dump(block/'quarantine/ibex/inputs.json',hidden)
    x.dump(block/'quarantine/provenance.json',dict(new_distinct_instruction_encodings=len(set(values)),
        no_overlap_with_old_223_boundary_encodings=True,development_operand_partition='imm low5 0..7; integer rd0..15',
        holdout_operand_partition='imm low5 8..31; extra nonhint rd16..31; new lower-16-bit encodings',
        semantic_limit='Same architectural obligation families, not independent bugs; HINTs can have equivalent architectural execution while decoder encodings differ.',
        frozen_before_initial_generation=True,generator_visible=False))
    x.dump(block/'quarantine_freeze.json',{x.rel(p):x.sha(p) for p in (block/'quarantine').rglob('*') if p.is_file()})
    # Independent reference qualification on saved benchmark vectors. Only flags
    # evaluated here; expected decoded values remain in historical regression.
    qa=[]
    for v in x.read(HISTORY/'boundary_vectors.json'):
        family,illegal,branch=decode_obligation(v['instruction']);assert illegal==v['illegal']
        qa.append(dict(input=v['instruction'],family=family,expected=illegal,branch=branch))
    x.dump(block/'reference_qualification.json',dict(passed=True,vectors=len(qa),records=qa))
    manual=dict(id='harness_qa_only',antecedent='1',consequent='1',delay=0,provenance='manual_QA_not_model_candidate')
    q=iso.evaluate(d,common[0],[manual],'ibex_harness_qualification');x.dump(block/'harness_qualification.json',q)
    assert q['status']=='ok'
    fixed=x.read(x.ROOT/q['runs'][0]['run']/'independent_reference.json')
    assert all(c['passed'] for e in fixed['events'] for c in e['checks'])
    mutant=x.read(x.ROOT/q['runs'][1]['run']/'independent_reference.json')
    assert any(not c['passed'] for e in mutant['events'] for c in e['checks'])
    print('IBEX history/monitor/harness qualified; hidden encodings frozen before generation',flush=True)


def generate():
    install();block=x.OUT/'historical_formal'
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'quarantine_freeze.json').items())
    r=cont.call_model('ibex','shared_initial',0,[],[],x.OUT/'historical_generation')
    if not r['candidates']:raise RuntimeError('initial model generation failed; preserved call must be diagnosed before formal comparison')
    qualify_and_freeze(r,1)


def generate_retry():
    install();block=x.OUT/'historical_formal'
    assert not (block/'freeze.json').exists()
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'quarantine_freeze.json').items())
    previous=x.read(x.OUT/'historical_generation/models/ibex/shared_initial/0/result.json')
    assert previous['status']=='candidate_language_error'
    x.dump(x.OUT/'historical_generation/syntax_repair_protocol.json',dict(
        reason='first shared generation referenced undeclared conceptual names imm6 and bit12; genuine candidate error, no infrastructure change',
        additional_actual_calls_max=2,formal_arm_budget_unchanged=True,model_and_sampling_unchanged=True,
        selection='first syntactically valid and executable shared candidate; do not choose by semantic score',
        information='same public contract plus previous model response and actual parser error; no patch or private scenarios',
        first_failed_call_preserved=True,all_initial_generation_costs_separate_from_formal=True))
    for rnd in (1,2):
        r=cont.call_model('ibex','shared_initial',rnd,[],[],x.OUT/'historical_generation')
        if r['candidates']:
            qualify_and_freeze(r,rnd+1);return
    raise RuntimeError('shared initial syntax repair budget exhausted; no manual fallback')


def qualify_and_freeze(r,generation_calls):
    block=x.OUT/'historical_formal'
    d=x.read(x.OUT/'frozen/ibex/definition.json');cs=r['candidates']
    q=iso.evaluate(d,x.read(block/'common/ibex.json')[0],cs,'ibex_initial_qualification')
    x.dump(block/'initial_execution.json',q)
    assert q['status']=='ok','initial candidate not executable'
    x.dump(block/'initial/ibex.json',cs)
    cfg=x.read(x.OUT/'common_config.json')
    protocol=dict(cfg,parents=['ibex'],arms=list(experiment.ARMS),kind='real_historical_formal',
        generation=f'{generation_calls} actual shared initial generation/syntax-repair calls; first executable AST unchanged; generation separately costed',
        A='fixed common inputs/legacy acquired feedback',B='generic mutation, FP+FN objective; no obligation scheduling',
        C='obligation templates, active FN feedback plus common legal regression',D='obligation templates plus common legal boundary templates, FP+FN',
        sole_variation='same acquisition/feedback ablations as synthetic block; same shared interface/model/budgets',
        no_patch_or_private_monitor_or_hidden_answers_in_model=True,query_budget_per_parent_arm=14,
        initial_and_regression='two common 24-sample schedules on both revisions',final_selection=cfg['final_selection'],
        target='legality/compressed flags in five RV32C instruction families; not complete ISA',
        shared_input_domain='selected five public opcode families; development imm low5 0..7, rd0..15; no oracle labels for B scheduling')
    x.dump(block/'protocol.json',protocol)
    files=[Path(__file__),Path(experiment.__file__),Path(cont.__file__),Path(interface_path())]
    files += [p for p in block.rglob('*') if p.is_file()]+[p for p in (x.OUT/'frozen/ibex').rglob('*') if p.is_file()]+[x.OUT/'common_config.json']
    x.dump(block/'freeze.json',{x.rel(p):x.sha(p) for p in files})
    print('IBEX initial model candidate frozen; 8 formal model calls and 56 development queries registered',flush=True)


def generate_compact():
    """New separately identified initial-pool block, after failed syntax repair."""
    import json
    install();block=x.OUT/'historical_formal'
    assert not (block/'freeze.json').exists()
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'quarantine_freeze.json').items())
    out=x.OUT/'historical_generation_v2';out.mkdir(exist_ok=False)
    x.dump(out/'protocol.json',dict(previous_block='historical_generation',previous_calls=3,previous_status='all candidate_language_error, budget exhausted',
        new_pool_version='ibex_shared_initial_v2',actual_call_budget=1,selection='first single executable generated assertion; no semantic score selection',
        changed_mechanism='initial generation asks for exactly one assertion and clarifies conceptual encoding names are not signals',
        formal_interface_and_four_arm_budget_unchanged=True,model_and_sampling_unchanged=True,no_manual_candidate=True))
    cfg=x.read(x.OUT/'common_config.json');d=x.read(x.OUT/'frozen/ibex/definition.json')
    request=x.read(x.OUT/'historical_generation/models/ibex/shared_initial/0/request.json')
    prompt=json.loads(request['messages'][0]['content'])
    prompt['task']='Generate exactly ONE useful executable assertion from the public contract. Use only declared identifiers from expression_rules.allowed_identifiers. Encoding names in contract prose describe bit fields, not declared helper signals. Do not invent identifiers. Return only JSON {"assertions":[{"antecedent":"...","consequent":"...","delay":0}]}. Start with one obligation; further refinement occurs later.'
    prompt['expression_rules']['max_assertions']=1
    request['messages'][0]['content']=json.dumps(prompt)
    folder=out/'models/ibex/shared_initial/0'
    result,content=cont.interface.stream_call(request,folder,x.dump,cfg['model_digest'],cfg['timeout_seconds'])
    result['candidates']=None
    if result['status']=='response_received':
        try:
            cs=cont.interface.extract(content,d,'ibex_shared_initial_v2')
            assert len(cs)==1,'initial_single_assertion_count'
            result.update(status='parsed',candidates=cs)
        except (AssertionError,KeyError,TypeError,ValueError) as exc:result.update(status='candidate_language_error',error=repr(exc))
    x.dump(folder/'result.json',result)
    if not result['candidates']:raise RuntimeError('single-assertion initial generation failed; no manual fallback')
    qualify_and_freeze(result,4)


def interface_path():
    return cont.interface.__file__


def develop():
    install();experiment.develop()


def acceptance():
    install();experiment.setup();block=ref.BLOCK;out=block/'acceptance';out.mkdir(exist_ok=False)
    assert all(x.sha(x.ROOT/p)==h for p,h in x.read(block/'final_freeze.json').items())
    d=x.read(x.OUT/'frozen/ibex/definition.json');hidden=x.read(block/'quarantine/ibex/inputs.json')
    queries=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()]
    dev={r['instr_i'] for q in queries for rr in q['runs'][:1] for r in x.read(x.ROOT/rr['run']/'input.json') if r['rst_ni']}
    held={r['instr_i'] for rows in hidden for r in rows if r['rst_ni']}
    assert not dev&held
    results=[]
    for arm in experiment.ARMS:
        for version in ('initial','final'):
            cs=x.read(block/'initial/ibex.json') if version=='initial' else x.read(block/'development/ibex'/arm/'final.json')['candidates']
            for i,rows in enumerate(hidden):
                q=iso.evaluate(d,rows,cs,f'historical_acceptance/{arm}/{version}/{i}')
                x.append(out/'queries.jsonl',dict(arm=arm,version=version,scenario=i,**q))
                results.append(dict(case='ibex',arm=arm,version=version,scenario=i,metrics=experiment.paired_metrics(d,q,cs)))
    x.dump(out/'results.json',results)
    summary=[]
    for arm in experiment.ARMS:
        row=dict(case='ibex',arm=arm,scenarios=6,parent_acceptance='not_established')
        for version in ('initial','final'):
            ms=[r['metrics'] for r in results if (r['arm'],r['version'])==(arm,version)]
            row[version]={n:sum(len(m[n]) for m in ms) for n in ('fp','first_misses','later_misses','causal_detections','attribution_unknown')}
            row[version]['unknown_scenarios']=sum(m['status']!='ok' for m in ms)
            row[version]['causally_detected_obligations']=sorted({c['obligation'] for m in ms for e in m['causal_detections'] for c in e['transaction_obligations']})
        summary.append(row)
    x.dump(out/'summary.json',summary)
    x.dump(out/'isolation.json',dict(development_encodings=len(dev),holdout_encodings=len(held),overlap=sorted(dev&held),
        architectural_noop_equivalence_not_counted_as_independent_bugs=True))
    print('IBEX independent acceptance complete',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default=cont.NAME);p.add_argument('action',choices=['prepare','generate','generate_retry','generate_compact','develop','acceptance'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
