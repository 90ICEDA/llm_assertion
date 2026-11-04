"""Postprocessing only: completed-prefix cuts before acceptance construction."""
import argparse
import ast
import inspect
from pathlib import Path
from research195_refinement_adapter import clone
from research194_refinement_runner import read,dump,file_hash

GROUPS={
    'R_S0':{p:'S0_'+p for p in ('feedback','legacy','local_first')},
    'R_S3':{p:'S3_'+p for p in ('feedback','legacy','local_first')},
    'A':{'A0':'S0_feedback','A1':'S3_feedback','A2':'S0_local_first','A3':'S3_local_first'}}

def runtime():
    m=clone('research196_cost_sections');m.GROUPS=GROUPS
    class Adapter(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module=='research196_independent':node.module='research198_independent'
            return node
        def visit_keyword(self,node):
            self.generic_visit(node)
            if node.arg=='arm' and ast.unparse(node.value)=="e['search'] + '_' + e['strategy']":
                node.value=ast.parse("e['search']+'_'+e['policy']",mode='eval').body
            return node
        def visit_For(self,node):
            self.generic_visit(node)
            if ast.unparse(node.target)=='(axis, grid)':
                node.iter=ast.parse("[('tokens',(0,65536,131072,262144)),('service_seconds',(0,120,240,480)),('round',(0,3,5))]",mode='eval').body
            return node
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                # R198 acquisitions physically reuse an already measured fixed
                # suite; its zero wall_seconds is explicitly recorded.
                node.value=node.value.replace('r196_total_seconds','wall_seconds').replace('research196-cost-sections','research198-cost-sections').replace('R196 acceptance','R198 acceptance')
            return node
    for name in ('register','evaluate','analyze'):
        tree=Adapter().visit(ast.parse(inspect.getsource(getattr(m,name))))
        ast.fix_missing_locations(tree);exec(compile(tree,__file__,'exec'),m.__dict__)
    return m

def register(prepared,execution,out):
    runtime().register(prepared,execution,out)
    path=Path(out)/'registration.json';r=read(path)
    for src in (Path(__file__),Path(prepared)/'protocol.json'):
        r['source_bindings'][str(src.resolve())]=file_hash(src)
    r['fixed_search_scope']='No newly acquired queries. Historical acquisition cost is separately identified, not charged as new physical work.'
    r['round_axis']='Equal completed model-round ceilings of three and five; interface failures consume rounds. Unknown token/service costs remain unknown.'
    dump(path,r);dump(Path(out)/'seal.json',dict(sha256=file_hash(path)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','evaluate','analyze']);p.add_argument('--prepared',type=Path);p.add_argument('--execution',type=Path);p.add_argument('--acceptance',type=Path);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.action=='register':register(a.prepared,a.execution,a.out)
    elif a.action=='evaluate':runtime().evaluate(a.out,a.acceptance)
    else:runtime().analyze(a.out)
