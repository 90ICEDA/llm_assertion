"""Current-candidate online acquisition using existing wall-cost-aware selector."""
import copy
from pathlib import Path
from research195_refinement_adapter import clone
from research197_search import SearchCases,contexts
from research194_refinement_runner import dump
from research194_refinement import digest

def session(cid,strategy,seed,out,*,baseline,queries,cost_model,max_queries=3):
    module=clone('research196_active_search');module.control_contexts=contexts
    class CurrentSession(module.Session):
        def acquire(self,current_candidate=None,round=None,history=(),**kwargs):
            current_hash=digest(current_candidate)
            # Same-candidate history only; old accepted candidates cannot make
            # new candidates appear protected. The parent also filters by hash.
            usable=[e for e in history if e.get('candidate_sha256')==current_hash]
            value=super().acquire(current_candidate,round=round,history=usable,**kwargs)
            if value is not None:
                if value['selection']['candidate_sha256']!=current_hash:raise ValueError('stale_search_candidate')
                value['online_link']=dict(candidate_sha256=current_hash,previous_candidate_sha256=self.records[-2]['candidate_sha256'] if len(self.records)>1 else None,
                    current_history_ids=sorted({e['id'] for e in usable}),query_id=value['query']['id'],
                    new_evidence_ids=value['new_gap_ids'],reselected=True,heldout_access=False)
                dump(self.out/f'query{len(self.records)-1:02}'/'acquisition.json',value)
            return value
        def reuse_acquisition(self,record,current_candidate):
            value=super().reuse_acquisition(record,current_candidate)
            # Original measured first acquisition is charged logically to all
            # paired arms; actual reused compilations are zero and identifiable.
            value['first_query_physical_reuse']=True
            value['online_link']=copy.deepcopy(record.get('online_link',{}))
            dump(self.out/'query00'/'acquisition.json',value)
            return value
    return CurrentSession(cid,strategy,seed,out,initial_queries=queries,initial_evidence=baseline['evidence'],
        cost_model=cost_model,wall_budget=180,max_queries=max_queries,adapter=SearchCases)
