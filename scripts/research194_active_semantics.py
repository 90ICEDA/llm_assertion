"""Bounded temporal semantics and counterfactual query goals.

This optional planner never imports an RTL oracle or a test population. It
interprets an explicit SVA expression subset, retaining unknown for unsupported
constructs, absent signal/history, and unfinished temporal attempts. Hypothetical
outputs distinguish candidate predicates, not legal and illegal RTL behavior.
Only independently judged, actually executed traces can become evidence.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import re
import time


class Unsupported(ValueError):
    pass


TOKEN=re.compile(r"\s*(?:(\d+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+|\d+)|([A-Za-z_$][A-Za-z0-9_$]*)|(===|!==|&&|\|\||==|!=|<=|>=|<<|>>|[()\[\],?:!~+*/%&|^<>-]))")
PRECEDENCE={'||':1,'&&':2,'|':3,'^':4,'&':5,'==':6,'!=':6,'<':7,'<=':7,'>':7,'>=':7,'<<':8,'>>':8,'+':9,'-':9,'*':10,'/':10,'%':10}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class Parser:
    def __init__(self,text):
        self.tokens=[];pos=0
        while pos<len(text):
            if not text[pos:].strip():break
            m=TOKEN.match(text,pos)
            if not m:raise Unsupported('token:'+text[pos:pos+24])
            self.tokens.append(next(v for v in m.groups() if v is not None));pos=m.end()
        self.index=0

    def peek(self):return self.tokens[self.index] if self.index<len(self.tokens) else None
    def take(self,expected=None):
        token=self.peek()
        if token is None or (expected is not None and token!=expected):raise Unsupported('expected:'+str(expected))
        self.index+=1;return token

    def expression(self,minimum=0):
        token=self.take()
        if token in ('!','-','+','|','^'):
            node=('unary',token,self.expression(11))
        elif token=='~':raise Unsupported('bitwise_not_requires_width_semantics')
        elif token=='(':
            node=self.expression();self.take(')')
        elif token[0].isdigit():
            if "'" not in token:value=int(token)
            else:
                width,raw=token.split("'");signed=raw[0].lower()=='s';raw=raw[1:] if signed else raw
                if re.search('[xXzZ?]',raw[1:]):value=None
                else:
                    value=int(raw[1:].replace('_',''),{'b':2,'o':8,'d':10,'h':16}[raw[0].lower()])&((1<<int(width))-1)
                    if signed and value&(1<<(int(width)-1)):value-=1<<int(width)
            node=('literal',value)
        elif token[0].isalpha() or token[0] in '_$':
            if self.peek()=='(':
                self.take('(');args=[]
                if self.peek()!=')':
                    args.append(self.expression())
                    while self.peek()==',':self.take(',');args.append(self.expression())
                self.take(')')
                if token not in ('$past','$rose','$fell','$stable','$onehot','$onehot0','$countones'):raise Unsupported('call:'+token)
                node=('call',token,tuple(args))
            else:node=('literal',int(token=='true')) if token in ('true','false') else ('signal',token)
        else:raise Unsupported('expression:'+token)
        while self.peek()=='[':
            self.take('[');first=self.expression();last=None
            if self.peek()==':':self.take(':');last=self.expression()
            self.take(']');node=('slice',node,first,last)
        while self.peek() in PRECEDENCE and PRECEDENCE[self.peek()]>=minimum:
            op=self.take();node=('binary',op,node,self.expression(PRECEDENCE[op]+1))
        if minimum==0 and self.peek()=='?':
            self.take('?');yes=self.expression();self.take(':');node=('conditional',node,yes,self.expression())
        return node


def parse(text):
    p=Parser(str(text));node=p.expression()
    if p.peek() is not None:raise Unsupported('trailing:'+p.peek())
    return node


def value(node,trace,index):
    kind=node[0]
    if kind=='literal':return node[1]
    if kind=='signal':
        if index<0 or index>=len(trace):return None
        v=trace[index].get(node[1]);return int(v) if isinstance(v,(bool,int)) else None
    if kind=='unary':
        v=value(node[2],trace,index)
        if v is None:return None
        if node[1]=='|':return int(bool(v))
        if node[1]=='^':return v.bit_count()%2 if v>=0 else None
        return int(not v) if node[1]=='!' else -v if node[1]=='-' else v
    if kind=='slice':
        v,first=value(node[1],trace,index),value(node[2],trace,index)
        last=value(node[3],trace,index) if node[3] is not None else first
        if None in (v,first,last) or first<last or last<0:return None
        return (v>>last)&((1<<(first-last+1))-1)
    if kind=='conditional':
        cond=value(node[1],trace,index)
        if cond is not None:return value(node[2] if cond else node[3],trace,index)
        a,b=value(node[2],trace,index),value(node[3],trace,index)
        return a if a==b else None
    if kind=='call':
        name,args=node[1:]
        if not args:return None
        if name=='$past':
            if len(args)>2:return None
            depth=value(args[1],trace,index) if len(args)==2 else 1
            return None if depth is None or depth<1 else value(args[0],trace,index-depth)
        if len(args)!=1:return None
        current=value(args[0],trace,index)
        if name in ('$rose','$fell','$stable'):
            previous=value(args[0],trace,index-1)
            if current is None or previous is None:return None
            return int(current==previous) if name=='$stable' else int(bool(current&1) and not(previous&1)) if name=='$rose' else int(not(current&1) and bool(previous&1))
        if current is None or current<0:return None
        count=current.bit_count()
        return count if name=='$countones' else int(count==1) if name=='$onehot' else int(count<=1)
    if kind=='binary':
        op=node[1];a,b=value(node[2],trace,index),value(node[3],trace,index)
        if op=='&&':return 0 if a==0 or b==0 else None if a is None or b is None else 1
        if op=='||':return 1 if (a is not None and a!=0) or (b is not None and b!=0) else None if a is None or b is None else 0
        if a is None or b is None:return None
        if op in ('/','%') and b==0:return None
        if op in ('<<','>>') and b<0:return None
        return {'==':lambda:int(a==b),'!=':lambda:int(a!=b),'<':lambda:int(a<b),'<=':lambda:int(a<=b),
            '>':lambda:int(a>b),'>=':lambda:int(a>=b),'&':lambda:a&b,'|':lambda:a|b,'^':lambda:a^b,
            '+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:int(a/b),'%':lambda:a%b,
            '<<':lambda:a<<b,'>>':lambda:a>>b}[op]()
    raise Unsupported('unknown_ast')


def dependencies(node):
    if node[0]=='signal':return {node[1]}
    result=set()
    for item in node[1:]:
        if isinstance(item,tuple):
            if item and isinstance(item[0],str) and item[0] in ('signal','literal','unary','binary','slice','conditional','call'):result.update(dependencies(item))
            else:
                for arg in item:
                    if isinstance(arg,tuple):result.update(dependencies(arg))
    return result


def compile_assertion(assertion):
    try:
        ant=parse(assertion['antecedent']);con=parse(assertion['consequent'])
        if 'window' in assertion:low,high=assertion['window']
        else:
            timing=assertion.get('timing','same_sample')
            if timing not in ('same_sample','next_sample'):raise Unsupported('timing:'+timing)
            low=high=int(timing=='next_sample')
        if not isinstance(low,int) or not isinstance(high,int) or low<0 or high<low:raise Unsupported('invalid_window')
        reset=parse(assertion.get('disable','rst'))
        cancel=parse(assertion['cancel']) if assertion.get('cancel') else None
        return dict(supported=True,antecedent=ant,consequent=con,window=(low,high),disable=reset,cancel=cancel,
                    signals=sorted(dependencies(ant)|dependencies(con)|dependencies(reset)|(dependencies(cancel) if cancel else set())))
    except (KeyError,ValueError,TypeError) as exc:return dict(supported=False,reason=str(exc),signals=[])


def evaluate_assertion(assertion,trace):
    c=compile_assertion(assertion)
    if not c['supported']:return dict(label=assertion.get('label'),status='unknown',reason=c['reason'],triggers=[],failures=[],unknown_attempts=[],attempts=[])
    triggers=[];failures=[];unknown=[];attempts=[]
    for t in range(len(trace)):
        reset=value(c['disable'],trace,t)
        if reset is None:unknown.append(dict(trigger=t,reason='disable_unknown'));continue
        if reset:continue
        trigger=value(c['antecedent'],trace,t)
        if trigger is None:unknown.append(dict(trigger=t,reason='antecedent_unknown'));continue
        if not trigger:continue
        triggers.append(trace[t].get('cycle',t));low,high=c['window'];samples=[];cancelled=False;uncertain=False;success=False
        for due in range(t,t+high+1):
            if due>=len(trace):uncertain=True;continue
            disabled=value(c['disable'],trace,due)
            exempt=value(c['cancel'],trace,due) if c['cancel'] else 0
            if disabled or exempt:cancelled=True;break
            if disabled is None or exempt is None:uncertain=True
            if due<t+low:continue
            v=value(c['consequent'],trace,due);samples.append(dict(cycle=trace[due].get('cycle',due),value=v))
            if v is None:uncertain=True
            elif v:success=True;break
        verdict='cancelled' if cancelled else 'satisfied' if success else 'unknown' if uncertain else 'violated'
        attempt=dict(trigger_cycle=trace[t].get('cycle',t),window=list(c['window']),verdict=verdict,samples=samples)
        attempts.append(attempt)
        if verdict=='violated':failures.append(trace[t+high].get('cycle',t+high))
        elif verdict=='unknown':unknown.append(attempt)
    status='failed' if failures else 'unknown' if unknown else 'passed' if triggers else 'vacuous'
    return dict(label=assertion.get('label'),status=status,triggers=triggers,failures=failures,unknown_attempts=unknown,attempts=attempts)


def evaluate_candidate(candidate,trace):
    assertions=[evaluate_assertion(a,trace) for a in candidate]
    status='failed' if any(a['status']=='failed' for a in assertions) else 'unknown' if any(a['status']=='unknown' for a in assertions) else 'passed' if any(a['triggers'] for a in assertions) else 'vacuous'
    return dict(candidate_sha256=digest(candidate),status=status,assertions=assertions,
                failure_cycles=sorted({t for a in assertions for t in a['failures']}),trigger_cycles=sorted({t for a in assertions for t in a['triggers']}))


def semantic_differences(candidates):
    result=[]
    for ai,bi in itertools.combinations(range(len(candidates)),2):
        a,b=candidates[ai],candidates[bi];dimensions=set()
        for x,y in itertools.zip_longest(a,b,fillvalue={}):
            if x.get('antecedent')!=y.get('antecedent'):dimensions.add('trigger')
            if x.get('consequent')!=y.get('consequent'):dimensions.add('response')
            if (x.get('timing'),x.get('window'))!=(y.get('timing'),y.get('window')) or re.findall(r'\$past\([^)]*\)',str(x))!=re.findall(r'\$past\([^)]*\)',str(y)):dimensions.add('window')
            if any(re.search(r'(id|tag|data|payload|addr)',str(z)) for z in (x,y)) and x.get('consequent')!=y.get('consequent'):dimensions.add('transaction')
            if (x.get('cancel'),x.get('disable'))!=(y.get('cancel'),y.get('disable')) or any(w in str(x)+str(y) for w in ('flush','ready','reset')) and x.get('antecedent')!=y.get('antecedent'):dimensions.add('exception')
        result.append(dict(a=ai,b=bi,dimensions=sorted(dimensions),semantic_separation_requires_witness=True))
    return result


def hypothesized_traces(query,output_signals,limit=48):
    """Finite symbolic output assignments; inputs stay byte-identical.

    Domains are public signal widths and {0,1,max}; pulses visit an evenly spaced
    sample grid. These traces are NOT simulator runs or legal-behavior evidence.
    """
    rows=query.get('planner_rows',query['rows'])
    base=[dict(r) for r in rows]
    for i,row in enumerate(base):
        row.setdefault('cycle',i)
        for name in output_signals:row.setdefault(name,0)
    yield dict(kind='all_outputs_zero',trace=base)
    if not rows:return
    positions=sorted({int(i*(len(rows)-1)/7) for i in range(8)})
    count=1
    if limit>1:
        yield dict(kind='all_outputs_one',trace=[dict(r,**{n:1 for n in output_signals}) for r in base]);count+=1
    for name,width in sorted(output_signals.items()):
        width=int(width);domain=sorted({1,(1<<min(width,16))-1})
        for val in domain:
            if count>=limit:return
            constant=[dict(r,**{name:val}) for r in base]
            yield dict(kind='constant',signal=name,value=val,trace=constant);count+=1
            for position in positions:
                if count>=limit:return
                pulse=[dict(r) for r in base];pulse[position][name]=val
                yield dict(kind='single_sample_response',signal=name,value=val,cycle=position,trace=pulse);count+=1


def plan_goal(query,candidates,output_signals,max_hypotheses=48):
    start=time.perf_counter();witnesses={};attempts=unknowns=0
    differences=semantic_differences(candidates)
    for hypothetical in hypothesized_traces(query,output_signals,max_hypotheses):
        predictions=[evaluate_candidate(c,hypothetical['trace']) for c in candidates];attempts+=1
        unknowns+=sum(p['status']=='unknown' for p in predictions)
        for pair in differences:
            a,b=pair['a'],pair['b'];pa,pb=predictions[a],predictions[b]
            if any(item['unknown_attempts'] for p in (pa,pb) for item in p['assertions']):continue
            # Different failing cycles also partition candidates with equal whole-run status.
            if pa['failure_cycles']==pb['failure_cycles']:continue
            key=f'{a}:{b}'
            if key not in witnesses:
                witnesses[key]=dict(pair=[a,b],dimensions=pair['dimensions'],hypothesis={k:v for k,v in hypothetical.items() if k!='trace'},
                    hypothetical_trace=hypothetical['trace'],predictions=[pa,pb],status='semantic_hypothesis_requires_actual_execution')
    total=len(differences)
    return dict(query_id=query['id'],goal='Distinguish candidate temporal predicates under the submitted public input schedule',
        constraints=query.get('constraints',[]),input_sha256=digest(query['rows']),hypothetical_pairs=sorted(witnesses),
        witnesses=list(witnesses.values()),semantic_discrimination=len(witnesses)/max(1,total),
        candidate_pairs=total,hypothesis_evaluations=attempts,candidate_hypothesis_evaluations=attempts*len(candidates),
        unknown_hypothesis_predictions=unknowns,planning_seconds=time.perf_counter()-start,
        legality='unknown until independent oracle judges executed RTL trace',native_queries=0,model_calls=0)


def verify_native_predictions(candidate,trace,native):
    """Native labels/cycles validate the semantic interpreter; mismatch is unknown."""
    prediction=evaluate_candidate(candidate,trace)
    def markers(field):
        result={}
        for m in native.get(field,[]):
            cycle=m.get('cycle')
            if cycle is None:
                found=re.search(r'cycle=(-?\d+)',m.get('detail',''));cycle=int(found[1]) if found else None
            if cycle is not None:result.setdefault(m['id'],set()).add(cycle)
        return result
    triggers,failures=markers('triggers'),markers('failures');checks=[]
    for item in prediction['assertions']:
        checks.append(dict(label=item['label'],semantic_status=item['status'],
            unknown_attempts=len(item['unknown_attempts']),triggers_match=set(item['triggers'])==triggers.get(item['label'],set()),
            failures_match=set(item['failures'])==failures.get(item['label'],set())))
    supported=native.get('compile_status')=='passed' and native.get('execution_status')=='completed'
    match=supported and all(c['semantic_status']!='unknown' and not c['unknown_attempts'] and c['triggers_match'] and c['failures_match'] for c in checks)
    return dict(status='confirmed_semantics' if match else 'unknown',checks=checks,prediction=prediction,
                native_healthy=supported,oracle_status='not_decided_by_candidate_predictions')
