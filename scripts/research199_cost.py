"""Predeclared prefix cuts, including necessary-obligation coverage."""
import ast
import inspect
import statistics
from pathlib import Path
from research195_refinement_adapter import clone
from research194_refinement_runner import read,dump,file_hash
from research199_refinement import ARMS
import research197_cases as cases

GROUPS={g:{a:spec['search']+'_'+a for a,spec in ARMS.items() if spec['cohort']==cohort} for g,cohort in [('B','factorial'),('A','online')]}

def acquisition_seconds(cost):
    return cost.get('r196_total_seconds',cost.get('wall_seconds'))

def profile(m):
    by={}
    for ev in m['evidence']:
        if ev['status']=='confirmed' and ev['label']=='violation' and ev.get('counted_target',True):by.setdefault(ev['obligation'],set()).add(ev['id'])
    protected={ob for ob,ids in by.items() if ids and ids<=set(m['transaction_detected_ids'])}
    return set(by),protected

def runtime():
    m=clone('research196_cost_sections');m.GROUPS=GROUPS;m.acquisition_seconds=acquisition_seconds
    class Adapter(ast.NodeTransformer):
        def visit_ImportFrom(self,n):
            if n.module=='research196_independent':n.module='research199_independent'
            return n
        def visit_keyword(self,n):
            self.generic_visit(n)
            if n.arg=='arm' and ast.unparse(n.value)=="e['search'] + '_' + e['strategy']":n.value=ast.parse("e['search']+'_'+e['arm']",mode='eval').body
            return n
        def visit_Call(self,n):
            self.generic_visit(n)
            if ast.unparse(n)=="c.get('r196_total_seconds')":return ast.parse('acquisition_seconds(c)',mode='eval').body
            return n
        def visit_For(self,n):
            self.generic_visit(n)
            if ast.unparse(n.target)=='(axis, grid)':n.iter=ast.parse("[('tokens',(0,65536,131072,262144)),('service_seconds',(0,120,240,480)),('round',(0,1,2,3))]",mode='eval').body
            return n
        def visit_Constant(self,n):
            if isinstance(n.value,str):n.value=n.value.replace('research196-cost-sections','research199-cost-sections').replace('R196 acceptance','R199 acceptance')
            return n
    for name in ('register','evaluate','analyze'):
        tree=Adapter().visit(ast.parse(inspect.getsource(getattr(m,name))));ast.fix_missing_locations(tree);exec(compile(tree,__file__,'exec'),m.__dict__)
    return m

def register(prepared,execution,out):
    runtime().register(prepared,execution,out);path=Path(out)/'registration.json';r=read(path)
    r['source_bindings'][str(Path(__file__).resolve())]=file_hash(__file__)
    r['primary_cost_axis']=dict(axis='tokens',budget_label='131072',preregistered=True)
    r['cost_scope']='B: incremental fixed-evidence refinement, historical acquisition separate. A: logical actual first-query cost plus fresh subsequent planning/acquisition/history/model service; first physical query shared between paired arms.'
    dump(path,r);dump(Path(out)/'seal.json',dict(sha256=file_hash(path)))

def analyze(out):
    out=Path(out);runtime().analyze(out);data=read(out/'analysis.json');index=read(out/'projection_index.json');cache={}
    def get(cid,h,fault):
        key=cid+'/'+h+'/'+fault
        if key not in cache:
            src=index[key]
            if file_hash(src['path'])!=src['sha256']:raise ValueError('projection_changed')
            cache[key]=read(src['path'])
        return cache[key]
    for row in data['summary']:
        subset=[s for s in data['cells'] if all(s[k]==row[k] for k in ('group','axis','budget_label'))];rates=[]
        for cid in sorted({s['case_id'] for s in subset}):
            pair=[s for s in subset if s['case_id']==cid]
            if len(pair)!=2:continue
            faults=set.intersection(*({f['fault'] for f in s['faults'] if f['eligible']} for s in pair))
            if not faults:continue
            seeds=[]
            for s in pair:
                exposed=set();failed=set()
                for f in faults:
                    x,p=profile(get(cid,s['checkpoints'][row['arm']]['candidate_sha256'],f));exposed|=x;failed|=x-p
                seeds.append(len(exposed-failed)/len(cases.get_case(cid)['obligations']))
            rates.append(statistics.mean(seeds))
        row['necessary_obligation_rate']=statistics.mean(rates) if rates else None
    dump(out/'analysis.json',data)
