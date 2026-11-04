"""Reuse development-only example selection with the R197 cases and analysis."""
import argparse
import ast
import inspect
from pathlib import Path
from research195_refinement_adapter import clone
from research197_cases import get_case
from research197_results import analysis_runtime


def runtime():
    module=clone('research196_cards');module.get_case=get_case;module.search_analysis=analysis_runtime().search_analysis
    class Title(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str):node.value=node.value.replace('R196','R197')
            return node
    tree=Title().visit(ast.parse(inspect.getsource(module.attach)));ast.fix_missing_locations(tree)
    exec(compile(tree,__file__,'exec'),module.__dict__)
    return module


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','attach'])
    for key in ('prepared','execution','acceptance'):p.add_argument('--'+key,type=Path)
    p.add_argument('--out',required=True,type=Path);a=p.parse_args();m=runtime()
    m.select(a.prepared,a.execution,a.out) if a.action=='select' else m.attach(a.out,a.acceptance)
