"""Exact model AST reuse under an explicitly broader syntax interface.

This is a NEW interface-continuation experiment, not retroactive research39
acceptance and not a new model call. Latest actual v1 is fixed before replay.
Only &&/|| variadic rendering and explicit rst operands are added. No leaf,
operator, sampled function, timing, slot or obligation is deleted or inferred.
Native target/history acceptance and post-freeze independent testing unchanged.
"""
import argparse
import copy
import json
from pathlib import Path

import research17_loop as loop
import research17_model_schema as grammar
import research15_native_interface as native
import research32_runtime as extension
import research31_gate as gate
from research28_report import raw_response
from research34_applicability import native_target_gate
from research34_campaign import snapshot, digest
from research35_campaign import holdout
from research36_applicability import validate_events
from research17_report import artifacts, cost_audit

SOURCE=loop.ROOT/'deliverables/research39_real_20261022_r01/core/v1/model_call'
PREP=loop.ROOT/'deliverables/research39_prepare_20261022_r01'
PROFILE='qualified_sampled_reset_v3'
read,dump=loop.read,loop.dump


def expression(node):
    count=[0]
    require=grammar._require
    def walk(value,path,depth):
        count[0]+=1
        require(depth<=grammar.MAX_DEPTH and count[0]<=grammar.MAX_NODES,'complexity',path,'AST limit exceeded.')
        require(type(value) is dict,'expression_object_required',path,'AST object required.')
        if set(value)=={'signal'}:
            require(value['signal'] in (*grammar.SIGNALS,'rst'),'unknown_signal',path,'Only declared signals or explicit rst.')
            return value['signal']
        if set(value)=={'int'}: return grammar.expression(value,path)
        require(set(value)=={'op','args'},'expression_fields',path,'Exactly op and args.')
        op,args=value['op'],value['args']
        require(op in grammar.UNARY+grammar.BINARY,'unsupported_operator',path,'Unsupported operator.')
        require(type(args) is list,'operator_arity',path,'args must be an array.')
        arity=1 if op in grammar.UNARY else 2
        require(2<=len(args)<=8 if op in ('&&','||') else len(args)==arity,
                'operator_arity',path,'Variadic logical &&/|| only; all others keep exact arity.')
        rendered=[walk(a,f'{path}.args[{i}]',depth+1) for i,a in enumerate(args)]
        if op=='!': return f'(!({rendered[0]}))'
        if op in grammar.SAMPLED: return f'{op}({rendered[0]})'
        # Parenthesized native operator chain preserves order and every operand.
        return '('+(' '+op+' ').join(rendered)+')'
    return walk(node,'$',0)


def assemble(value,current):
    assert set(value)=={'operation','assertion_id','assertions','reason'}
    assert value['operation']=='replace_one' and len(value['assertions'])==1
    assert isinstance(value['reason'],str)
    item=value['assertions'][0]
    assert set(item)=={'antecedent','consequent','timing','obligation'}
    assert item['timing'] in ('same_sample','next_sample')
    props=copy.deepcopy(current['assertions'])
    index=next(i for i,a in enumerate(props) if a['id']==value['assertion_id'])
    assert item['obligation']==props[index]['obligations']==['stall_stability']
    ant,cons=expression(item['antecedent']),expression(item['consequent'])
    arrow='|->' if item['timing']=='same_sample' else '|=>'
    props[index]=dict(property=f'({ant}) {arrow} ({cons})',obligations=item['obligation'],reason=value['reason'])
    candidate=native.normalize_candidate(dict(assertions=props,syntax_profile=PROFILE))
    assert all(a==b for a,b in zip(current['assertions'],candidate['assertions']) if a['id']!=value['assertion_id'])
    return candidate


def qualify(out):
    out.mkdir()
    checks=[]
    def check(name,okay):
        checks.append(dict(name=name,passed=bool(okay)))
        assert okay,name
    # New profile explicitly opts in. Existing interfaces remain unchanged.
    fixture=dict(assertions=[dict(property='(!rst) |-> mvalid',obligations=['stall_stability'])])
    try: native.normalize_candidate({**fixture,'syntax_profile':'qualified_sampled_multi_v2'})
    except AssertionError as exc: check('legacy_profile_still_rejects_rst','interface_unknown:rst' in str(exc))
    else: raise AssertionError('legacy profile silently changed')
    c=native.normalize_candidate({**fixture,'syntax_profile':PROFILE})
    check('explicit_rst_preserved','!rst' in c['assertions'][0]['property'])
    tree=dict(op='&&',args=[dict(signal='mvalid'),dict(op='!',args=[dict(signal='mready')]),dict(op='!',args=[dict(signal='rst')])])
    check('all_operands_preserved',expression(tree)=='(mvalid && (!(mready)) && (!(rst)))')
    for op in ('==','!=','+','-'):
        try: expression(dict(op=op,args=[dict(int=i) for i in range(3)]))
        except grammar.SchemaError: check('no_variadic_nonassociative_'+op,True)
        else: raise AssertionError(op)
    # Auxiliary Icarus expression-only qualification: 4^3 assignments, both
    # logical operators, with 0/1/X/Z. This does not substitute for native SVA.
    folder=out/'four_state_boolean';folder.mkdir()
    source='''module tb;
reg a,b,c; reg vals[0:3]; integer i,j,k,n;
initial begin
vals[0]=0; vals[1]=1; vals[2]=1'bx; vals[3]=1'bz; n=0;
for(i=0;i<4;i=i+1) for(j=0;j<4;j=j+1) for(k=0;k<4;k=k+1) begin
a=vals[i]; b=vals[j]; c=vals[k]; #1;
if ((a && b && c) !== ((a && b) && c)) $fatal(1,"AND_ASSOC_LEFT");
if ((a && b && c) !== (a && (b && c))) $fatal(1,"AND_ASSOC_RIGHT");
if ((a || b || c) !== ((a || b) || c)) $fatal(1,"OR_ASSOC_LEFT");
if ((a || b || c) !== (a || (b || c))) $fatal(1,"OR_ASSOC_RIGHT");
n=n+4;
end
$display("EXPRESSION_CHECKS %0d",n); $finish;
end
endmodule
'''
    (folder/'tb.sv').write_text(source)
    command=native.runner.command
    version,_=command(['iverilog','-V'],folder,'expression_tool_version',15)
    compiled,_=command(['iverilog','-g2012','-o','expression_sim','tb.sv'],folder,'expression_compile',30)
    executed,log=command(['vvp','expression_sim'],folder,'expression_execute',30)
    check('four_state_associativity_256',compiled['exit_code']==executed['exit_code']==0 and 'EXPRESSION_CHECKS 256' in log)
    # True native SVA checks the newly exposed reset signal on actual FIFO RTL.
    build=loop.runtime.build(c,out/'native_reset_operand',2,0)
    check('native_rst_compile',build['native']['compile_status']=='passed')
    replay=loop.runtime.execute(build,out/'native_reset_replay',loop.common_case()['rows'],'correct')
    check('native_rst_execution',replay['native']['execution_status']=='completed')
    check('native_rst_operand_observed',bool(replay['native']['triggers']) and bool(replay['native']['failures']))
    check('native_sampling',replay['sampling_qualification']['status']=='passed')
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,
        scope='Arbitrary syntax diagnostic; false SVA is deliberate. Not a model repair or a formal equivalence proof.',
        auxiliary_boolean_commands=3,auxiliary_boolean_tests=256,model_calls=0)
    dump(out/'result.json',result)
    return result


def run(out):
    loop.prepare(out);snapshot(out)
    initial=read(PREP/'shared_initial.json')
    edit=read(SOURCE/'model_edit.json')
    assert raw_response(SOURCE,edit)
    assert read(SOURCE/'result.json')['status']=='response_received'
    plan=read(PREP/'verified_plan.json')
    assert validate_events(plan,read(PREP/'expected.private.json'))['accepted']
    dump(out/'protocol.json',dict(
        source=str(SOURCE),source_sha256=digest(SOURCE/'model_edit.json'),selection='Latest actual research39 v1, fixed before any replay. No candidate search among archived outputs.',
        interface='New opt-in rst and variadic logical operator support. All AST operands/functions and timing preserved. Existing research39 rejection remains valid.',
        interpretation='Archived real model output with new syntax adapter; NOT a fresh generation or an accepted edit under the previous schema.',
        gate='Unchanged native_target_gate and research31 history decide, unknown rejects. Full113 history before freeze; fresh56 holdout only after acceptance.',
        maximum_new_model_calls=0,formal_calls=0))
    dump(out/'source_model_edit.json',edit)
    dump(out/'shared_initial.json',initial)
    dump(out/'verified_plan.json',plan)
    current=initial
    status='not_started'
    try:
        qualify(out/'interface_qualification')
        candidate=assemble(edit,initial)
        dump(out/'candidate.json',candidate)
        (out/'candidate.sva').write_text(native.candidate_sva(candidate))
        with extension.installed():
            small=loop.replay(candidate,out/'target_native',read(PREP/'target_cases.json'))
            verdict=native_target_gate(read(PREP/'target_baseline.json'),small,edit['assertion_id'])
            dump(out/'target_gate.json',verdict)
            print('TARGET',verdict['accepted'],len(verdict['reasons']),flush=True)
            if not verdict['accepted']:
                status='native_target_or_small_history_rejected';return
            before=read(PREP/'full_baseline.json')
            full=loop.replay(candidate,out/'history_native',read(PREP/'full_cases.json'))
            verdict=gate.decide(before['group']['ledger'],full['group']['ledger'],sorted(loop.inspect(before['group']['ledger'])['misses'])) if full.get('group') else dict(accepted=False,reasons=[dict(kind='native_unavailable')])
            verdict['accepted']=bool(verdict['accepted'] and full['healthy'])
            dump(out/'historical_gate.json',verdict)
            print('HISTORY',verdict['accepted'],len(verdict['reasons']),flush=True)
            if not verdict['accepted']:
                status='full_history_rejected';return
            current=candidate
            loop.freeze(out/'core',current,'accepted_interface_continuation_before_fresh_inputs')
            holdout(out,current,read(PREP/'full_cases.json'))
            status='interface_continuation_accepted_independent_completed'
    except BaseException:
        status='execution_exception';raise
    finally:
        if not (out/'core/freeze.json').exists(): loop.freeze(out/'core',current,'retained_after_rejection')
        dump(out/'outcome.json',dict(status=status,accepted=current!=initial,frozen_hash=loop.sha(current),
            model_calls=0,source_model_call=str(SOURCE),source_call_cost_charged_to='research39',
            semantic_edits_by_adapter=False,interface_changed=True))
        dump(out/'cost.json',cost_audit(out,artifacts(out)))
        print('TERMINAL',status,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert loop.ROOT in a.out.resolve().parents
    run(a.out.resolve())
