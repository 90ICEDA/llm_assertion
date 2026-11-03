"""Native property frontend with derived antecedents and native cover actions."""
import copy
import json
from pathlib import Path
import re
import research_native_runner as runner
import research_native_closed_loop as old

ROOT=runner.ROOT
OUT=ROOT/'deliverables/research15_native_20261015_r01'
dump=runner.dump
REFERENCE=old.REFERENCE.replace('  integer native_cycle=-1;\n  always @(negedge clk) native_cycle <= native_cycle+1;\n','')
OBLIGATIONS={'order_payload','no_unsolicited_output','stall_stability','drain_no_loss','reset_cancellation'}


def unparen(text):
    text=text.strip()
    while text.startswith('(') and text.endswith(')'):
        balance=0;encloses=True
        for i,c in enumerate(text):
            balance+=(c=='(')-(c==')')
            if balance==0 and i<len(text)-1:encloses=False;break
        if not encloses:break
        text=text[1:-1].strip()
    return text


def normalize_candidate(candidate):
    result=copy.deepcopy(candidate)
    assert isinstance(result.get('assertions'),list) and 1<=len(result['assertions'])<=5,'assertion_count'
    seen=set()
    for index,item in enumerate(result['assertions']):
        text=unparen(item['property'])
        assert not re.search(r'[;`]|\b(?:initial|always|endmodule|assert|assume|cover)\b',text),'non_property_input'
        assert '##' not in text,'unsupported_sequence_delay'
        pieces=re.split(r'(\|->|\|=>)',text)
        assert len(pieces)==3,'require_exactly_one_explicit_implication'
        ant,imp,cons=map(str.strip,pieces)
        assert ant and cons,'empty_expression'
        scrubbed=re.sub(r"\b\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+",'0',text)
        identifiers=set(re.findall(r'\$?[A-Za-z_][A-Za-z_0-9]*',scrubbed))
        allowed=set('svalid sready sdata mvalid mready mdata ref_count ref_expected drain_due'.split())
        allowed.update(('$past','$stable','$rose','$fell','$changed','$isunknown','$unsigned','$signed'))
        assert not identifiers-allowed,'interface_unknown:'+','.join(sorted(identifiers-allowed))
        sampled=set(re.findall(r'\$(?:past|stable|rose|fell|changed)',ant))
        qualified={'$rose','$past'} if result.get('syntax_profile') in ('qualified_sampled_v1','qualified_sampled_multi_v2') else set()
        assert not sampled-qualified,'antecedent_temporal_expression_not_supported'
        signature=re.sub(r'\s+','',text)
        assert signature not in seen,'duplicate_property'
        seen.add(signature)
        obligations=item.get('obligations',[])
        if result.get('syntax_profile')=='qualified_sampled_multi_v2':
            assert 1<=len(obligations)<=len(OBLIGATIONS) and len(set(obligations))==len(obligations) and set(obligations)<=OBLIGATIONS,'invalid_obligation_mapping'
        else:
            assert len(obligations)==1 and obligations[0] in OBLIGATIONS,'one_named_obligation_per_property'
        item.update(id=f'a{index}',property=text,derived_antecedent=ant,implication=imp,
                    derived_delay=0 if imp=='|->' else 1,consequent=cons)
        item.pop('trigger',None)
    result['trigger_source']='Antecedent parsed from exact native property, observed with native cover property action'
    return result


def candidate_sva(candidate):
    candidate=normalize_candidate(candidate)
    lines=[]
    for item in candidate['assertions']:
        i=item['id']
        lines.extend([f'{i}: assert property (@(posedge clk) disable iff (rst) ({item["property"]}))',
            f'  else $display("ASSERT_FAIL {i} cycle=%0d", $sampled(native_cycle));',
            f'cv_{i}: cover property (@(posedge clk) disable iff (rst) ({item["derived_antecedent"]}))',
            f'  $display("TRIGGER {i} cycle=%0d", $sampled(native_cycle));'])
    return '\n'.join(lines)+'\n'


def run_native(source,directory,**kwargs):
    # Coverage-user is needed for Verilator cover property instrumentation.
    original=runner.command
    def command(args,*pos,**kw):
        if '--binary' in args:args=[*args,'--coverage-user']
        return original(args,*pos,**kw)
    runner.command=command
    try: result=runner.run_native(source,directory,**kwargs)
    finally:runner.command=original
    result['trigger_measurement']='native cover property on parsed antecedent; finite sampled trigger evidence, not formal reachability'
    dump(Path(directory)/'result.json',result)
    return result


def replay_native(compiled,directory,args=()):
    result=runner.replay_native(compiled,directory,args)
    result['trigger_measurement']='native cover property on parsed antecedent; finite sampled trigger evidence, not formal reachability'
    dump(Path(directory)/'result.json',result)
    return result


def compile_candidate(candidate,directory,template):
    candidate=normalize_candidate(candidate)
    assert template.count('// NATIVE_REFERENCE')==1 and template.count('// NATIVE_PROPERTIES')==1
    source=template.replace('// NATIVE_REFERENCE',REFERENCE).replace('// NATIVE_PROPERTIES',candidate_sva(candidate))
    result=run_native(source,directory,extra_sources=[old.RTL])
    compiled=dict(directory=str(Path(directory).resolve()),candidate=candidate,native=result)
    dump(Path(directory)/'compiled.json',compiled)
    return compiled


def run_replay(compiled,directory,rows,mode):
    import research15_search_runtime as runtime
    directory=Path(directory)
    schedule=runtime.save_schedule(directory.parent/(directory.name+'_stimulus'),rows)
    result=replay_native(compiled['directory'],directory,[f'+stimulus={schedule}',f'+fault={mode}'])
    trace=runtime.parse_trace(directory/'execute.log')
    oracle=runtime.oracle(trace,rows)
    record=dict(native=result,trace=trace,oracle=oracle,candidate=compiled['candidate'],
        mode=runtime.MODES[mode],directory=str(directory.resolve()))
    dump(directory/'trace.json',trace);dump(directory/'oracle.json',oracle);dump(directory/'replay.json',record)
    return record


def probe():
    c={'assertions':[{'property':'(svalid && sready) |=> mvalid','obligations':['order_payload']}]}
    source='''module tb;
bit clk=0; always #5 clk=~clk;
bit rst=1,svalid=0,sready=1,mvalid=0;
integer native_cycle=-1;
always @(negedge clk) native_cycle<=native_cycle+1;
PROPERTIES
initial begin
repeat(2) @(negedge clk);rst=0;svalid=1;
@(negedge clk);svalid=0;mvalid=1;
@(negedge clk);svalid=1;mvalid=0;
@(negedge clk);svalid=0;mvalid=0;
repeat(2) @(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;
end
endmodule'''.replace('PROPERTIES',candidate_sva(c))
    result=run_native(source,OUT/'cover_qualification')
    qualification=dict(native=result,expected_trigger_count=2,expected_failure_count=1,
        passed=len(result.get('triggers',[]))==2 and len(result.get('failures',[]))==1 and result['execution_status']=='completed')
    dump(OUT/'cover_qualification/qualification.json',qualification)
    print(json.dumps(qualification,indent=2))


if __name__=='__main__':probe()
