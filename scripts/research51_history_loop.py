"""Original Ibex #166: shared real transport/native runner/evidence gate.

No RTL editing or artificial fault modes. Local controls are explicitly NOT LLM
outputs. prepare qualifies the adapter; run requires a new bounded grant.
"""
import argparse
import copy
import hashlib
import json
import random
import re
import secrets
import shutil
from pathlib import Path
import research15_history as historical
import research15_native_interface as native
import research15_acceptance as acceptance
from research20_remote import RemoteModel, DEFAULT_URL, DEFAULT_MODEL
from research17_model import read, dump
from research17_report import cost_audit

ROOT=Path(__file__).resolve().parents[1]
ORIGINAL=ROOT/'deliverables/research51_original_20261022_r01'
UPSTREAM=ROOT/'deliverables/research51_upstream_20261022_r01'
OBLIGATIONS=dict(illegal_branch_persists='BRANCH funct3 010 or 011 is illegal on every execution sample, including held instr_new_i=0 samples.',
    op_bit28_illegal='Register-register OP encodings with bit28 set are illegal in this historical RV32I/M decoder on every sample.')
CONFIGS=historical.CONFIGS


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def assemble(value,current):
    assert type(value) is dict and set(value)=={'operation','assertions','reason'}
    assert type(value['reason']) is str and type(value['assertions']) is list
    op=value['operation'];items=value['assertions']
    if op=='keep':
        assert current is not None and not items
        return copy.deepcopy(current)
    assert op in ('add','replace') and 1<=len(items)<=6
    properties=copy.deepcopy(current['assertions']) if op=='add' and current else []
    for item in items:
        assert set(item)=={'antecedent','consequent','timing','obligations'}
        assert type(item['obligations']) is list and item['obligations'] and set(item['obligations'])<=set(OBLIGATIONS)
        for expr in (item['antecedent'],item['consequent']):
            assert type(expr) is str and 1<=len(expr)<=1024
            assert re.fullmatch(r"[a-zA-Z0-9_ ()!<>=&|$.'\[\]:+*/%?~-]+",expr), 'expression_characters'
            assert not any(s in expr for s in (';','`','##','|->','|=>','//','/*'))
            # Reject unknown identifiers instead of rewriting model expressions.
            stripped=re.sub(r"\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+",'0',expr)
            names=set(re.findall(r'\$?[A-Za-z_][A-Za-z_0-9]*',stripped))
            assert names<={'instr','instr_new','illegal_insn','rv32m','rv32e','$past','$stable','$rose','$fell'},str(names)
        delay={'same_sample':0,'next_sample':1}[item['timing']]
        properties.append(dict(id=f'a{len(properties)}',**item,delay=delay,
            property='('+item['antecedent']+') '+('|=>' if delay else '|->')+' ('+item['consequent']+')'))
    assert len(properties)<=6
    return dict(assertions=properties)


def transactions(seed,count,exclude):
    rng=random.Random(seed);result=[];used=set(exclude)
    while len(result)<count:
        index=len(result);kind=index%4
        word=((rng.randrange(16)<<20)|(rng.randrange(16)<<15)|(rng.randrange(1,16)<<7))
        if kind in (0,2):word|=(rng.choice((2,3)) if kind==0 else rng.choice((0,1,4,5,6,7)))<<12|0x63
        else:word|=(rng.choice((8,9,0x28)) if kind==1 else 0)<<25|rng.randrange(8)<<12|0x33
        if word in used:continue
        used.add(word)
        result.append(dict(id=index,instruction=word,hold_samples=rng.randrange(2,10),
            family=('branch_reserved','op_bit28','branch_legal','op_control')[kind],
            search_strategy=('repair_difference','legal_hold_perturbation','obligation_gap')[index%3]))
    return result


def samples(txns,cohort):
    rows=[]
    for t in txns:
        assert 1<=t['hold_samples']<=32
        for phase in range(t['hold_samples']):
            rows.append(dict(sample_id=len(rows),transaction_id=t['id'],phase=phase,
                instruction=t['instruction'],instr_new=int(phase==0),family=t['family'],cohort=cohort))
    return rows


def obligation(row):
    word=row['instruction']
    if word&127==0x63 and (word>>12)&7 in (2,3):return 'illegal_branch_persists'
    if word&127==0x33 and word&(1<<28):return 'op_bit28_illegal'
    return 'encoding_controls'


def bench(candidate,rows,configs,stimulus):
    n=len(configs)
    lines=['module tb; bit clk=0; always #5 clk=~clk;',
        f'logic [31:0] instr; logic instr_new; logic [{n-1}:0] illegal; integer sample_id=-1,transaction_id=-1,phase=-1;',
        'initial begin $dumpfile("wave.vcd"); $dumpvars(0,tb); end']
    for i,c in enumerate(configs):
        lines += [f'ibex_decoder #(.RV32E({c["RV32E"]}),.RV32M({c["RV32M"]})) dut{i}(.instr_new_i(instr_new),.instr_rdata_i(instr),.illegal_c_insn_i(1\'b0),.illegal_insn_o(illegal[{i}]));',
            f'if (1) begin : config{i}',f'wire illegal_insn=illegal[{i}]; localparam bit rv32m={c["RV32M"]},rv32e={c["RV32E"]};']
        for a in candidate['assertions']:
            key=f'{a["id"]}_c{i}'
            lines += [f'assert property (@(posedge clk) disable iff(sample_id<0) ({a["property"]})) else $display("ASSERT_FAIL {key} cycle=%0d",$sampled(sample_id));',
                f'cover property (@(posedge clk) disable iff(sample_id<0) ({a["antecedent"]})) $display("TRIGGER {key} cycle=%0d",$sampled(sample_id));']
        lines+=['end']
    lines += ['always @(posedge clk) if(sample_id>=0) $display("TRACE sample=%0d txn=%0d phase=%0d instr=%h new=%b observed=%b",sample_id,transaction_id,phase,instr,instr_new,illegal);', 'initial begin']
    # Match the independently reproduced original15 sampling harness. Direct
    # fscanf writes did not propagate decoder combinational reevaluation in the
    # local tool build; the failed qualification is retained, never accepted.
    for r in rows:
        lines.append(f"@(negedge clk); sample_id={r['sample_id']}; transaction_id={r['transaction_id']}; phase={r['phase']}; instr=32'h{r['instruction']:08x}; instr_new=1'b{r['instr_new']};")
    lines += ['@(posedge clk); #1; $display("NATIVE_RUN_COMPLETE"); $finish; end endmodule']
    return '\n'.join(lines)+'\n'


def replay(candidate,txns,cohort,out,sources,configs=CONFIGS):
    out.mkdir(parents=True,exist_ok=False);rows=samples(txns,cohort)
    dump(out/'transactions.json',txns);dump(out/'samples.json',rows)
    stimulus=out/'stimulus.txt'
    stimulus.write_text(''.join(f'{r["sample_id"]} {r["transaction_id"]} {r["phase"]} {r["instruction"]:08x} {r["instr_new"]}\n' for r in rows))
    tb=bench(candidate,rows,configs,stimulus);observed={};results={};healthy=True
    for rev in ('before','after'):
        result=native.run_native(tb,out/rev,extra_sources=[sources/rev/'ibex_defines.sv',sources/rev/'ibex_decoder.sv'])
        results[rev]=result;trace={}
        if result['execution_status']=='completed':
            for line in (out/rev/'execute.log').read_text().splitlines():
                if line.startswith('TRACE '):
                    fields=dict(v.split('=') for v in line.split()[1:]);sid=int(fields['sample']);r=rows[sid]
                    assert sid not in trace and int(fields['instr'],16)==r['instruction'] and int(fields['new'])==r['instr_new']
                    assert int(fields['txn'])==r['transaction_id'] and int(fields['phase'])==r['phase']
                    trace[sid]=int(fields['observed'],2)
        healthy &= len(trace)==len(rows) and result['compile_status']=='passed' and result['execution_status']=='completed'
        observed[rev]=trace
    def markers(rev,kind):
        return {(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in results[rev].get(kind,[])}
    hits={rev:markers(rev,'failures') for rev in results};triggers={rev:markers(rev,'triggers') for rev in results}
    ledger=[];input_hash=acceptance.sha([r['instruction'] for r in rows]);reference=[]
    if healthy:
        for r in rows:
            sid=r['sample_id'];ob=obligation(r)
            for ci,cfg in enumerate(configs):
                exp=historical.oracle(r['instruction'],r['instr_new'],cfg)
                actual={rev:(observed[rev][sid]>>ci)&1 for rev in results}
                fixed_ok=actual['after']==exp
                reference.append(dict(**r,configuration=cfg,expected=exp,actual=actual,obligation=ob))
                for rev in results:
                    aa=[]
                    for a in candidate['assertions']:
                        if ob!='encoding_controls' and ob not in a['obligations']:continue
                        name=f'{a["id"]}_c{ci}';trigger=(name,sid-a['delay']) in triggers[rev];failed=(name,sid) in hits[rev]
                        aa.append(dict(id=a['id'],trigger=trigger,failed=failed,
                            causal_detection=bool(rev=='before' and actual[rev]!=exp and fixed_ok and trigger and failed and (name,sid) not in hits['after'])))
                    key=acceptance.sha(dict(cohort=cohort,transaction=r['transaction_id'],phase=r['phase'],word=r['instruction'],config=cfg,revision=rev,obligation=ob))
                    ledger.append(dict(evidence_id=key,obligation=ob,stimulus_sha256=input_hash,
                        sample=r,configuration=cfg,revision=rev,expected=exp,observed=actual[rev],
                        required=ob in OBLIGATIONS,
                        oracle=dict(legality='legal',verdict='violated' if actual[rev]!=exp else 'satisfied',validator='research15_history.oracle ISA encoding rules'),
                        native=dict(compile='ok',support='supported',execution='ok',trigger_source='property_antecedent_cover',
                            attribution_status='confirmed' if fixed_ok else 'unknown',assertions=aa)))
    info=acceptance.inspect(ledger)
    counts={k:len(info[k]) for k in ('rows','triggers','detections','misses','false_positives','unknown')}
    result=dict(healthy=bool(healthy),ledger=ledger,counts=counts,reference=reference,
        required_untriggered=[k for k,r in info['rows'].items() if r['required'] and k not in info['triggers']],
        mapping=info['mapping'],native_status={rev:{k:results[rev][k] for k in ('compile_status','tool_support_status','execution_status','property_status')} for rev in results},
        scope='Original combinational decoder with held instruction phases. Not full-core retire/trap reproduction; no artificial faults or oracle-based DUT.')
    dump(out/'result.json',result);return result


def admissible(result):
    return result['healthy'] and not result['required_untriggered'] and not any(result['counts'][k] for k in ('misses','false_positives','unknown'))


def decide(before,after):
    gate=acceptance.decide(before['ledger'],after['ledger'],acceptance.inspect(before['ledger'])['misses'])
    # Preserve required-obligation triggers, not incidental legal-control firing.
    kept=[]
    old=acceptance.inspect(before['ledger'])['rows']
    for r in gate['reasons']:
        if r['kind']=='lost_obligation_trigger':
            r={**r,'evidence_keys':[k for k in r['evidence_keys'] if old[k]['required']]}
            if not r['evidence_keys']:continue
        kept.append(r)
    if not admissible(after):kept.append(dict(kind='full_scope_target_legal_trigger_or_unknown_failure'))
    return dict(accepted=not kept,reasons=kept,shared_gate=gate,
        applicability_rule='Native trigger observations retained; lost-trigger acceptance constraint applies only to independently required obligations.')


def evidence(result):
    info=acceptance.inspect(result['ledger']);unique={}
    for k in sorted(info['misses']|info['false_positives']|info['unknown']):
        r=info['rows'][k]
        kind='unknown' if k in info['unknown'] else 'false_positive' if k in info['false_positives'] else 'miss'
        mechanism='held_branch' if r['obligation']=='illegal_branch_persists' and r['sample']['phase']>0 else r['obligation']
        key=(kind,mechanism,r['revision'])
        if key not in unique:unique[key]=dict(kind=kind,mechanism=mechanism,row=r,
            trigger_state='triggered_but_insufficient' if k in info['triggers'] else 'not_triggered')
    return dict(counts=result['counts'],native_status=result['native_status'],
        deduplication='kind + obligation/failure mechanism + revision; phases/words are not additional discoveries',
        independent_findings=list(unique.values()),required_untriggered_count=len(result['required_untriggered']),
        mapping={ob:{'assertions':m['assertions'],**{k:len(v) for k,v in m.items() if k!='assertions'}} for ob,m in result['mapping'].items()})


SCHEMA=dict(operation='replace | add | keep',reason='explanation string',assertions=[dict(
    antecedent='boolean SystemVerilog expression',consequent='boolean SystemVerilog expression',
    timing='same_sample | next_sample',obligations=list(OBLIGATIONS))])


def payload(prep,current=None,feedback=None,phase='initial_generation'):
    body=dict(case='Original upstream Ibex #166, fixes #163; no artificial faults',
        source=read(prep/'source_binding.json'),
        rtl={rev:{p.name:p.read_text() for p in (prep/rev).glob('*.sv')} for rev in ('before','after')},
        confirmed_obligations=OBLIGATIONS,
        interface='instr=instr_rdata_i, instr_new=instr_new_i, illegal_insn=illegal_insn_o. illegal_c_insn_i=0. rv32m/rv32e are the DUT parameters. Decoder has no clock/reset/ready ports. Test clock samples settled combinational output; inputs change on prior negedge. New instruction: instr_new=1; hold same bits with instr_new=0 for remaining phases. Illegal instruction words are legal decoder stimuli.',
        legal_controls='Do not report failures on legal BRANCH and OP words or NOP. No full-core handshake/trap completion assumed.',
        current_assertions=current,phase=phase,actual_development_feedback=feedback,
        output=SCHEMA,limits='JSON only, <=6 properties total. Choose all operands and timing. Use only instr,instr_new,illegal_insn,rv32m,rv32e and $past/$stable/$rose/$fell. No oracle expected-answer signal, declarations, modules or file operations. keep requires an existing set and empty assertions.',
        timing='same_sample is overlapped |->; next_sample is nonoverlapped |=>. All required held samples must be protected. Predicates are never repaired by the harness.')
    return dict(model=DEFAULT_MODEL,temperature=0.2,seed=5101,max_tokens=2048,stream=True,
        stream_options=dict(include_usage=True),response_format=dict(type='json_object'),
        messages=[dict(role='system',content='Generate or refine native SVA from original RTL, confirmed specification and actual evidence. Return only the declared JSON edit. Explanations are not evidence.'),dict(role='user',content=json.dumps(body))])


class Model(RemoteModel):
    def __init__(self,out,prep):
        super().__init__(out,dict(options=dict(seed=5101,temperature=.2,num_predict=2048),max_model_calls=3,max_tokens=400000,max_wall_seconds=7200))
        self.prep=prep
        cfg=read(self.out/'remote_transport_config.json');cfg['max_output_tokens']=2048;dump(self.out/'remote_transport_config.json',cfg)
    def _payload(self,current,target,feedback,phase):return payload(self.prep,current,feedback,phase)
    def save_decoded_output(self,folder,value,current,secret):
        cand=assemble(value,current);dump(folder/'candidate.json',cand)
        (folder/'candidate.sva').write_text('\n'.join(a['property'] for a in cand['assertions'])+'\n')
        return cand,'assembled_without_semantic_rewrite'


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    downloads=read(UPSTREAM/'downloads.json');assert len(downloads)==4 and all(r['matches_archived'] for r in downloads)
    original=read(ORIGINAL/'summary.json');assert original['admitted_original_module']
    for rev in ('before','after'):
        shutil.copytree(ORIGINAL/rev,out/rev)
        for p in (out/rev).glob('*.sv'):assert digest(p)==digest(UPSTREAM/rev/p.name)
    protocol=read(ORIGINAL/'protocol.json')
    binding={k:protocol[k] for k in ('case_id','upstream','before_commit','after_commit','merge_commit','legal_stimulus')}
    binding.update(source_sha256=original['source_sha256'],fresh_reproduction=str(ORIGINAL),upstream_verification=str(UPSTREAM),
        scope='Original historical module, not full-core exception; stat and FIFO presented remain unknown.')
    dump(out/'source_binding.json',binding)
    history=read(ORIGINAL/'transactions.json');used={t['instruction'] for t in history}
    search=transactions(5101,36,used)
    dump(out/'history_cases.json',history);dump(out/'search_cases.json',search)
    dump(out/'development_manifest.json',dict(history_instructions=sorted(used),
        all_used_instructions=sorted(used|{t['instruction'] for t in search}),
        classification='All prior original #166 reproduction and this search pool are development. New holdout words are drawn only after final freeze.',
        original_samples_sha256=digest(ORIGINAL/'samples.json')))
    good=assemble(dict(operation='replace',reason='Local adapter control ONLY; never a model response or prompt.',assertions=[
        dict(antecedent="instr[6:0]==7'h63 && (instr[14:12]==3'd2 || instr[14:12]==3'd3)",consequent='illegal_insn',timing='same_sample',obligations=['illegal_branch_persists']),
        dict(antecedent="instr[6:0]==7'h33 && instr[28]",consequent='illegal_insn',timing='same_sample',obligations=['op_bit28_illegal'])]),None)
    weak=copy.deepcopy(good);a=weak['assertions'][0];a['antecedent']='('+a['antecedent']+') && instr_new';a['property']='('+a['antecedent']+') |-> ('+a['consequent']+')'
    small=search[:8]
    g=replay(good,small,'qualification',out/'qualification/good',out)
    w=replay(weak,small,'qualification',out/'qualification/first_phase_only',out)
    gate=decide(g,w)
    checks=dict(original_source_bytes=True,good_control_passes=admissible(g),
        phase_limited_control_misses=w['counts']['misses']>0,
        history_loss_rejected=not gate['accepted'],native_covers_observed=g['counts']['triggers']>0,
        fixed_oracle_pass=not any(r['actual']['after']!=r['expected'] for r in g['reference']))
    dump(out/'qualification.json',dict(passed=all(checks.values()),checks=checks,gate=gate,model_calls=0,
        controls_are_not_model_results=True))
    assert all(checks.values()),checks
    dump(out/'request.preview.json',payload(out))
    dump(out/'protocol.json',dict(maximum_calls=3,retries=0,endpoint=DEFAULT_URL,model=DEFAULT_MODEL,
        initial_calls=1,remaining_calls='Up to2 native-feedback refinements; no extra transport retry. Initial interface failure uses remaining calls and stays reported.',
        search='36 preregistered transaction queries batched into paired native executions; three hold/encoding strategies. Dedup by obligation/error mechanism.',
        accepted_rule='No critical unknown, no false alarm, all independent violations detected and required samples covered; historical detections and required triggers preserved.',
        holdout='Only after a model candidate is accepted and all decisions complete: freeze, then96 new instruction words excluding all151 development words, configs including RV32E=1/RV32M=0. Never feedback.',
        success_boundary='Module-level historical reproduction only. If initial already protects all witnesses, review may keep it; no invented refinement benefit or initial weakening.',
        request_sha256=digest(out/'request.preview.json')))
    snap=out/'source_snapshot';snap.mkdir()
    for name in ('research51_history_loop.py','research15_history.py','research15_acceptance.py','research15_native_interface.py','research_native_runner.py','research20_remote.py'):
        shutil.copy2(ROOT/'scripts'/name,snap/name)
    dump(out/'source_hashes.json',{p.name:digest(p) for p in snap.iterdir()})
    dump(out/'cost.json',cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ('.json','.sv','.py'))})
    print('HISTORICAL_PREPARED',checks,flush=True)


def run(prep,out,auth_path):
    auth=read(auth_path);protocol=read(prep/'protocol.json')
    assert auth['scope']=='research51_original_ibex166' and auth['authorized_calls']==3
    assert auth['endpoint']==DEFAULT_URL and auth['request_sha256']==protocol['request_sha256']
    assert auth['run_output']==out.relative_to(ROOT).as_posix()
    for name,h in read(prep/'sealed.json').items():assert digest(prep/name)==h,name
    for name,h in read(prep/'source_hashes.json').items():assert digest(ROOT/'scripts'/name)==h,name
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(auth_path,out/'authorization.json')
    shutil.copytree(prep/'source_snapshot',out/'source_snapshot');dump(out/'protocol.json',protocol)
    llm=Model(out,prep);current=None;previous=None;accepted=None;feedback=None;decisions=[];status='no_accepted_version'
    history=read(prep/'history_cases.json');search=read(prep/'search_cases.json')
    try:
        for index in range(3):
            v=out/f'v{index}';had_current=current is not None
            call,candidate=llm.call(v/'model_call',current,'historical_repair_obligations',feedback,'refinement' if had_current else 'initial_generation')
            if candidate is None:
                feedback=dict(last_actual_native_feedback=feedback,latest_interface_or_transport_failure=call)
                decisions.append(dict(version=index,accepted=False,reason='no_executable_model_candidate'));continue
            h=replay(candidate,history,'history',v/'history',prep)
            s=replay(candidate,search,'search',v/'search',prep)
            full=dict(healthy=h['healthy'] and s['healthy'],ledger=h['ledger']+s['ledger'],
                counts={k:h['counts'][k]+s['counts'][k] for k in h['counts']},
                required_untriggered=h['required_untriggered']+s['required_untriggered'])
            verdict=decide(previous,full) if previous is not None else dict(accepted=admissible(full),reasons=[] if admissible(full) else [dict(kind='initial_target_or_legal_or_trigger_failure')])
            dump(v/'decision.json',verdict);dump(v/'search_evidence.json',evidence(s));dump(v/'history_evidence.json',evidence(h))
            decisions.append(dict(version=index,accepted=verdict['accepted'],phase='refinement' if had_current else 'initial_generation'))
            feedback=dict(actual_proposed_assertions=candidate,search=evidence(s),history=evidence(h),decision=verdict)
            if current is None:current=candidate;previous=full
            if verdict['accepted']:accepted=candidate;current=candidate;previous=full
            print('HISTORICAL_VERSION',index,verdict['accepted'],h['counts'],s['counts'],flush=True)
            if had_current and verdict['accepted']:break
        if accepted is not None:
            dump(out/'frozen_candidate.json',accepted);dump(out/'freeze.json',dict(sha256=acceptance.sha(accepted),decisions=decisions))
            manifest=read(prep/'development_manifest.json');seed=secrets.randbelow(2**31)
            test=transactions(seed,96,set(manifest['all_used_instructions']))
            dump(out/'independent_split.json',dict(seed=seed,transactions=test,generated_after_freeze=True,
                semantic_word_disjoint=True,not_unseen_instruction_family=True))
            test_result=replay(accepted,test,'independent',out/'independent',prep,CONFIGS+[dict(RV32E=1,RV32M=0)])
            dump(out/'independent_acceptance.json',dict(passed=admissible(test_result),counts=test_result['counts'],
                per_obligation_mapping=test_result['mapping'],scope='Original decoder, finite held-instruction evidence; not full-core or formal proof.'))
            status='frozen_independent_pass' if admissible(test_result) else 'frozen_independent_fail'
    finally:
        dump(out/'outcome.json',dict(status=status,calls=len(llm.calls),decisions=decisions,
            accepted_candidate_sha256=acceptance.sha(accepted) if accepted else None,formal_calls=0))
        dump(out/'cost.json',cost_audit(out,[p for p in out.rglob('*') if p.is_file()]))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
