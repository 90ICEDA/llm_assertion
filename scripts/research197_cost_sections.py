"""Opt-in R197 cost analysis using the existing completed-prefix machinery.

Keep F/P/T distinct from the main R3 arm. Select checkpoints before acceptance
and evaluate them with the R197 RTL/oracle adapter, never the R196 adapter.
"""
import argparse
import ast
import copy
import inspect
from pathlib import Path
from research195_refinement_adapter import clone
from research194_refinement_runner import read,dump,file_hash


def runtime():
    module=clone('research196_cost_sections')
    module.GROUPS=copy.deepcopy(module.GROUPS)
    module.GROUPS['T']={'F':'F','P':'P','T':'T'}
    class Adapter(ast.NodeTransformer):
        def visit_ImportFrom(self,node):
            if node.module=='research196_independent':node.module='research197_independent'
            return node
        def visit_keyword(self,node):
            self.generic_visit(node)
            # The original register labels all isolation runs S0_R3. Preserve
            # their registered identities to prevent contamination of R/A.
            if node.arg=='arm' and ast.unparse(node.value)=="e['search'] + '_' + e['strategy']":
                node.value=ast.parse("e.get('arm') or e['search']+'_'+e['strategy']",mode='eval').body
            return node
        def visit_Constant(self,node):
            if isinstance(node.value,str):
                node.value=node.value.replace('research196-cost-sections','research197-cost-sections').replace('R196 acceptance','R197 acceptance')
            return node
    for name in ('register','evaluate','analyze'):
        tree=Adapter().visit(ast.parse(inspect.getsource(getattr(module,name))))
        ast.fix_missing_locations(tree)
        exec(compile(tree,__file__,'exec'),module.__dict__)
    return module


def register(prepared,execution,out):
    from research197_prepare import verify
    verify(prepared)
    # No acceptance inputs or grades are read by checkpoint selection.
    runtime().register(prepared,execution,out)
    path=Path(out)/'registration.json';data=read(path)
    data['source_bindings'][str(Path(__file__).resolve())]=file_hash(__file__)
    data['source_bindings'][str((Path(prepared)/'protocol.json').resolve())]=file_hash(Path(prepared)/'protocol.json')
    dump(path,data);dump(Path(out)/'seal.json',dict(sha256=file_hash(path)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['register','evaluate','analyze'])
    for key in ('prepared','execution','acceptance'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args()
    if a.action=='register':register(a.prepared,a.execution,a.out)
    elif a.action=='evaluate':runtime().evaluate(a.out,a.acceptance)
    else:runtime().analyze(a.out)
