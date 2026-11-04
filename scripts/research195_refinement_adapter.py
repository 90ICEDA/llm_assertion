"""Explicit R195 dependency injection; R194 source and imported modules stay intact.

F: free edit, P: free edit with localization, L: constrained local edit.
All arms use the identical R3 history gate and the same feedback/evidence.
No transport is implemented here. A backend must be explicitly injected.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import uuid
from research194_refinement_safe_localization import safe_localize


def clone(name):
    path=Path(__file__).with_name(name+'.py')
    private='_r195_'+name+'_'+uuid.uuid4().hex
    spec=importlib.util.spec_from_file_location(private,path)
    module=importlib.util.module_from_spec(spec);sys.modules[private]=module
    spec.loader.exec_module(module)
    return module


def runtime(arm='L'):
    if arm not in ('F','P','L'):raise ValueError('unknown_R195_arm')
    core=clone('research194_refinement')
    runner=clone('research194_refinement_runner')
    def localization(candidate,evidence,enabled=True):
        return safe_localize(candidate,evidence)['actionable_findings'] if enabled else []
    core.localize=localization
    base_controller=core.Controller
    class Controller(base_controller):
        def __post_init__(self):
            super().__post_init__()
            self.stage='local' if arm=='L' else 'free'
            self.fallback_enabled=False
        def consider_empty_domain(self,measurement):return None
        def parse(self,response,evidence,validate):
            if arm!='L':
                if self.finished or self.rounds>=self.max_rounds:raise ValueError('controller_terminal_or_budget')
                if not isinstance(response,dict) or set(response)!={'assertions','reason'} or not isinstance(response['reason'],str):raise ValueError('free_response_schema')
                proposal=validate(copy.deepcopy(response['assertions']))
                before={a['label']:a['obligations'] for a in self.active}
                after={a['label']:a['obligations'] for a in proposal}
                if set(before)!=set(after):raise ValueError('fixed_assertion_labels_no_addition_or_deletion')
                if before!=after:raise ValueError('fixed_obligation_mapping_no_drift')
                return proposal,dict(stage='free',changed=['existing_assertion_predicates_and_timing'],noops=[])
            return super().parse(response,evidence,validate)
        def observe(self,*args,**kwargs):
            result=super().observe(*args,**kwargs)
            self.stage='local' if arm=='L' else 'free'
            result['next_stage']=self.stage
            return result
    core.Controller=Controller
    original_request=core.build_request
    def build_request(case,controller,evidence,seed,round_index,model='deepseek/deepseek-v3-0324'):
        request=original_request(case,controller,evidence,seed,round_index,model)
        context=json.loads(request['messages'][-1]['content'])
        context['experiment']=dict(version='research195',arm=arm,common_gate='R3 historical timely and any-cycle retention',
            contrast='Only localization visibility and edit permissions differ; no composition/regeneration fallback.')
        context['immutable_assertion_structure']=dict(labels=[a['label'] for a in controller.active],
            obligations={a['label']:a['obligations'] for a in controller.active},
            rule='All arms preserve exactly these labels and obligation mappings. Never add/delete assertions or change obligations. Free arms may rewrite only existing antecedent, consequent and timing fields; localized arm may change only authorized fields.')
        audit=safe_localize(controller.active,evidence)
        context['unmapped_localization']=audit['unmapped_localizations']
        if arm=='F':context.pop('localization',None)
        else:context['localization']=audit['actionable_findings']
        context.pop('fallback_receipt',None)
        request['messages'][-1]['content']=json.dumps(context,separators=(',',':'))
        return request
    core.build_request=build_request;runner.r=core
    return core,runner


class ArchivedResponseBackend:
    provenance='archived_response_replay; zero new model calls; response was not generated for the new request'
    def __init__(self,source):self.source=Path(source);self.used=False
    def __call__(self,request,folder):
        if self.used:raise ValueError('archive_single_use')
        self.used=True;folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
        import hashlib
        value=json.loads(self.source.read_text(encoding='utf-8'))
        record=dict(status='archived_response_replay',model_calls=0,prompt_tokens=0,completion_tokens=0,
            source=str(self.source.resolve()),source_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(),
            newly_generated_for_request=False,causal_model_comparison_eligible=False)
        (folder/'result.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
        (folder/'archived_model_edit.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
        return record,value
