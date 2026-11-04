"""Reuse native runner with fixed-evidence cache or genuine online session."""
import ast
import copy
import inspect
from research199_refinement import runtime
from research194_refinement_runner import read
from research198_execute import FixedSession

def configured(arm,state,adapter):
    core,runner=runtime(arm);cache={core.digest(state['initial']):state['first_measurement']}
    evaluate=adapter.evaluate
    def measured(candidate,folder,queries):
        value=evaluate(candidate,folder,queries);cache[core.digest(candidate)]=value;return value
    adapter.evaluate=measured
    if arm.startswith('B'):
        def merge(candidate,measurements):
            a,b=measurements
            if a['candidate_sha256']!=core.digest(candidate) or b['candidate_sha256']!=core.digest(candidate) or core.digest(a['evidence'])!=core.digest(b['evidence']):raise ValueError('fixed_history_mismatch')
            result=copy.deepcopy(a);result['cost']=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0)
            result['history_composition']=dict(physical_native_jobs=0,reason='Identical fixed development history; no evidence duplication.')
            return result
        runner.merge_measurements=merge
    # The original online runner dereferences a None budget-stop acquisition.
    # Insert an explicit stop before that dereference; preserve all native gates.
    class Stop(ast.NodeTransformer):
        def visit_Assign(self,node):
            if any(isinstance(t,ast.Name) and t.id=='selected' for t in node.targets):
                prefix=ast.parse("if acquired is None:\n records.append(dict(round=index+1,status='search_budget_exhausted',model_calls=0))\n controller.finished=True\n break").body
                return prefix+[node]
            return self.generic_visit(node)
    tree=Stop().visit(ast.parse(inspect.getsource(runner.run_trajectory)));ast.fix_missing_locations(tree)
    exec(compile(tree,__file__,'exec'),runner.__dict__)
    return core,runner,cache
