"""Generic expression/checker capability extension. No contract labels used here.

popcount accepts an unsigned declared packed signal (including permitted pN copies).
Its 32-bit unsigned result propagates X/Z. Delays 0,1,2 mean exact sampled distance;
only the antecedent is captured. Consequent operands are sampled at the due edge.
"""
import copy, re
import run_repair_contract as legacy

LEGACY_TB = legacy.tb_text
CAPABILITIES = {
    'version': '3.0', 'delay': [0, 1, 2],
    'popcount': 'popcount(unsigned_declared_signal), width 1..256, returns unsigned 32-bit count; X/Z propagates',
    'expressions': 'native SV integer literals, unsigned declared ports/history, arithmetic, bitwise, logical, comparison, ternary, constant indexing/concatenation; elaborator rejects malformed expressions',
    'signedness': 'ports/history and popcount return unsigned; other operators and sized/unsized integer literals use Icarus SystemVerilog sizing and signedness; no real/string/cast/user functions',
    'sampling': 'posedge pre-NBA; delay d checks consequent(t) iff antecedent(t-d); overlapping triggers independently queued',
    'reset': 'active-low asynchronous reset clears pending antecedents; no checks while reset; observer pN values zero-filled on sampled reset as legacy, qualification includes sampled reset',
    'history': 'no inherited antecedents before initialization; pending at end is recorded, not silently passed; pN explicit zero-initialized copies, not native $past',
    'disable': 'only supplied reset; enable is an ordinary signal; custom disable iff unsupported',
    'unknown': 'four-state SV computes CHECK; X/Z in active trace or CHECK yields unknown and is not an effective simulation',
    'unsupported': ['delay outside 0..2','unpermitted identifiers/history','popcount of general expressions, slices or signed values','system functions','hierarchical names','assignment/statements','temporal operators inside expressions'],
}

def widths(d, param=None):
    w={**d['inputs'],**d['outputs']}
    if param and d['key']=='fifo':w['data_i']=w['data_o']=param['DataWidth']
    if param and d['key']=='filter':w['thresh_i']=param['CntWidth']
    if d['key']=='spill':w['q_o']=w['valid_o']
    return {**w,**{f'p{j}_{s}':v for j in (1,2,3) for s,v in w.items()}}

def normalize(c,d,depth=0,param=None):
    assert isinstance(c,dict),'parse:not_object'
    assert set(c)>={'antecedent','consequent','delay'},'parse:missing_fields'
    assert type(c['delay']) is int and c['delay'] in (0,1,2),'unsupported:delay'
    allowed=set(d['observation_base'])|{f'p{j}_{s}' for j in range(1,depth+1) for s in d['observation_base']}
    ws=widths(d,param);out={};rules=[]
    for key in ('antecedent','consequent'):
        expr=c[key]
        assert isinstance(expr,str) and 0<len(expr)<1200,'parse:expression_type_or_length'
        assert not re.search(r'[;`@$"\\.]|//|/\*|(?<![=!<>])=(?!=)',expr),'illegal:expression_or_assignment'
        def count(m):
            s=m.group(1);assert s in allowed,'permission:popcount_argument'
            assert 1<=ws[s]<=256,'unsupported:popcount_width'
            rules.append({'field':key,'from':m.group(0),'to':f'af_count_{ws[s]}({s})','rule':'unsigned_signal_popcount_v1','width':ws[s]})
            return f'af_count_{ws[s]}({s})'
        converted=re.sub(r'\bpopcount\s*\(\s*([A-Za-z_]\w*)\s*\)',count,expr)
        cleaned=re.sub(r"\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ]+",'0',expr)
        names=set(re.findall(r'\b[A-Za-z_]\w*',cleaned))
        assert names<=allowed|{'popcount'},'permission:identifier:'+str(sorted(names-allowed-{'popcount'}))
        assert 'popcount' not in converted,'unsupported:popcount_argument_expression'
        # No other function calls; a signal followed by '(' is not an operator.
        for name in re.findall(r'\b([A-Za-z_]\w*)\s*\(',converted):
            assert re.fullmatch(r'af_count_\d+',name),'unsupported:function'
        out[key]=converted
    out['delay']=c['delay']
    return out,rules

def count_function(w):
    return f'''function automatic [31:0] af_count_{w}(input [{w-1}:0] value);
integer i;
begin af_count_{w}=32'b0;
for(i=0;i<{w};i=i+1) af_count_{w}=af_count_{w}+{{31'b0,value[i]}};
end
endfunction'''

def monitor(clk,rst,j,c):
    a,b,delay=c['antecedent'],c['consequent'],c['delay']
    ant=f'ad{j}[{delay-1}]' if delay else f'({a})'
    update=f'ad{j} <= '+(f"{{ad{j}[{delay-2}:0], (({a}) ? 1'b1 : 1'b0)}};" if delay>1 else f"(({a}) ? 1'b1 : 1'b0);")
    return '\n'.join([f'reg [{max(delay,1)-1}:0] ad{j}=0;',f'always @(posedge {clk} or negedge {rst}) begin if(!{rst}) ad{j}<=0; else begin',
        f'$display("CHECK {j} %0d %0d %0d",cycle, (({a}) ? 1 : 0), (({ant}) && !({b})) ? 1 : 0);',update,'end end'])

def tb_text(d,rows,candidates,param=None):
    norm=[];functions=set()
    for c in candidates:
        try:
            z,rules=normalize(c,d,c.get('authorized_history_depth',3),param)
            functions.update(x['width'] for x in rules);norm.append({**c,**z})
        except AssertionError:
            # Preserve unsupported raw expressions for real compile diagnostics.
            norm.append(c)
    text=LEGACY_TB(d,rows,norm,param)
    for j,c in enumerate(norm):
        a,b=c['antecedent'],c['consequent'];ante=f'ad{j}' if c['delay'] else f'({a})'
        old='\n'.join([f'reg ad{j}=0;',f'always @(posedge {d["clk"]} or negedge {d["rst"]}) begin if(!{d["rst"]}) ad{j}<=0; else begin',f'$display("CHECK {j} %0d %0d %0d",cycle, (({a}) ? 1 : 0), (({ante}) && !({b})) ? 1 : 0);',f"ad{j}<=(({a}) ? 1'b1 : 1'b0); end end"])
        assert old in text
        text=text.replace(old,monitor(d['clk'],d['rst'],j,c))
    return text.replace('module tb;','module tb;\n'+'\n'.join(count_function(w) for w in sorted(functions)),1)

def reference_checks(rows,c,eval_expr,rst):
    """Independent due-event list, deliberately not a shift-register translation."""
    due={};out=[]
    for i,row in enumerate(rows):
        if not row[rst]:due.clear();continue
        a=eval_expr(c['antecedent'],row)
        if a:due[i+c['delay']]=True
        fail=int(bool(due.pop(i,False)) and not eval_expr(c['consequent'],row))
        out.append({'cycle':i,'trigger':int(bool(a)),'fail':fail})
    return out
