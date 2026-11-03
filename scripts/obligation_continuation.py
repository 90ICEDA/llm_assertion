"""Continuation run: new interfaces/RTL/data, preserving all previous artifacts."""
import argparse
import collections
import copy
import difflib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request

import obligation_isolated_search as iso
from obligation_isolated_search import x
import obligation_refinement_block as ref
import obligation_refinement_public as public
import obligation_continuation_interface as interface

PRIOR=x.ROOT/'deliverables/obligation_evidence_20261013_r02'
NAME='obligation_continuation_20261013_r01'
BASE_CONFIGURE=iso.configure


def configure():
    x.checker.normalize=interface.normalize
    BASE_CONFIGURE()
    x.engine.tb_text=interface.tb_text


def init():
    x.OUT.mkdir(exist_ok=False)
    shutil.copytree(PRIOR/'frozen',x.OUT/'frozen')
    for f in ('protocol.json','obligation_catalog.json','perturbations.json'):
        shutil.copyfile(PRIOR/f,x.OUT/('historical_'+f))
    x.dump(x.OUT/'lineage.json',dict(prior=x.rel(PRIOR),prior_manifest_sha256=x.sha(PRIOR/'delivery/final_artifact_manifest.json'),
        audit='deliverables/obligation_completion_audit_20261013_r01/REPORT.md',historical_inputs_are_development=True,
        preserve_negative_results=True,stat_new_control='separate engineered fix; not a historical repair'))
    for path in (Path(__file__),Path(interface.__file__)):
        x.snapshot(path)
    model=x.read(PRIOR/'refinement_r04/protocol.json')
    config={k:model[k] for k in ('model','model_digest','sampling')}
    config.update(interface=interface.VERSION,timeout_seconds=420,retries=0,rounds=2,active_queries_per_round=4,
        common_initial_queries=2,regression_queries_per_round=2,query_budget_per_parent_arm=14,
        model_budget_per_parent_arm=2,final_selection='last executable proposal after fixed two rounds; errors retain previous candidate',
        model_cost_scope='preflight, historical replay, initial historical generation, and formal refinement separately costed',
        human_clarifications=0,human_time_seconds=None,formal_solver_calls=0)
    x.dump(x.OUT/'common_config.json',config)
    print('INIT',x.rel(x.OUT),flush=True)


def ensure_service():
    folder=x.OUT/'service';folder.mkdir(exist_ok=True)
    try:
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3))
        owned=False
    except Exception:
        log=(folder/'server.log').open('ab')
        env=dict(os.environ,OLLAMA_HOST='127.0.0.1:11434')
        p=subprocess.Popen(['ollama','serve'],stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        x.dump(folder/'owned_service.json',dict(pid=p.pid,command=['ollama','serve'],log=x.rel(folder/'server.log')))
        owned=True
        for _ in range(30):
            try:tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2));break
            except Exception:time.sleep(1)
        else:raise RuntimeError('local model service unavailable')
    version=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/version',timeout=5))
    x.dump(folder/'service.json',dict(owned=owned,tags=tags,version=version))
    return tags


def query(k, arm, phase, i, rows, cs):
    ident=f'{k}/{arm}/{phase}/{i}'
    x.append(ref.BLOCK/'query_attempts.jsonl',dict(id=ident,input_sha256=x.digest(rows)))
    q=iso.evaluate(x.read(x.OUT/'frozen'/k/'definition.json'),rows,cs,'formal/'+ident)
    q.update(id=ident,case=k,arm=arm,phase=phase)
    x.append(ref.BLOCK/'queries.jsonl',q)
    return q


def call_model(k,arm,round_no,candidates,feedback,block=None):
    cfg=x.read(x.OUT/'common_config.json');d=x.read(x.OUT/'frozen'/k/'definition.json')
    folder=(block or ref.BLOCK)/'models'/k/arm/str(round_no)
    names=list(d['observation_base']);allowed=names+[d['rst']]+[f'p{j}_{n}' for j in (1,2,3) for n in names]
    language=dict(allowed_identifiers=allowed,delay=[0,1,2],max_assertions=4,
        expression='SystemVerilog expressions only; no properties, $functions, internal names, statements or assignments. popcount(declared_signal) allowed.',
        history='p1/p2/p3 store exact preceding samples, zero after reset; no historical reset registers.',
        reset=f'{d["rst"]} is a public scalar and may appear in expressions. Implicit active-low reset cancels pending checks and history.',
        sampling='pre-NBA posedge; consequent at trigger+delay; for captured input use authorized pN values at the due sample.')
    if round_no:
        previous=folder.parent/str(round_no-1)
        if (previous/'result.json').exists():
            result=x.read(previous/'result.json');language['previous_status']=result['status'];language['previous_error']=result.get('error')
            if result['status']!='parsed':language['previous_response']=x.read(previous/'response.raw.json')['message']['content']
    prompt=dict(task='Improve this assertion set using the public specification and acquired development feedback. Preserve protection and avoid rejecting legal behavior. Return JSON {"assertions":[{"antecedent":"...","consequent":"...","delay":0}]} only.',
        contract=x.read(x.OUT/'frozen'/k/'public_contract.json'),
        ports={**{n:w for n,w in {**d['inputs'],**d['outputs']}.items() if n in names},d['rst']:1},
        expression_rules=language,current=[{n:c[n] for n in ('antecedent','consequent','delay')} for c in candidates],feedback=feedback)
    request=dict(model=cfg['model'],stream=True,format='json',messages=[dict(role='user',content=json.dumps(prompt))],options=cfg['sampling'])
    result,content=interface.stream_call(request,folder,x.dump,cfg['model_digest'],cfg['timeout_seconds'])
    result['candidates']=None
    if result['status']=='response_received':
        try:result.update(candidates=interface.extract(content,d,f'{k}_{arm}_{round_no}'),status='parsed')
        except json.JSONDecodeError as exc:result.update(status='response_json_error',error=repr(exc))
        except (AssertionError,KeyError,TypeError,ValueError) as exc:result.update(status='candidate_language_error',error=repr(exc))
    x.dump(folder/'result.json',result)
    return result


def preflight():
    out=x.OUT/'interface_preflight';out.mkdir(exist_ok=False);configure();ensure_service()
    qualification=[]
    for k in ('filter','fifo','stat'):
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        for ant,should in [(d['rst'],True),('p1_'+d['rst'],False),('private_internal',False),('1; $finish',False)]:
            c=dict(antecedent=ant,consequent='1',delay=0)
            try:interface.normalize(c,d,3);accepted=True
            except AssertionError:accepted=False
            assert accepted==should
            qualification.append(dict(case=k,expression=ant,accepted=accepted,expected=should))
    x.dump(out/'grammar_qualification.json',qualification)
    replay=[]
    for f in sorted((PRIOR/'refinement_r04/models').glob('*/*/*/result.json')):
        k,arm,round_no=f.parts[-4:-1];d=x.read(x.OUT/'frozen'/k/'definition.json');old=x.read(f)
        r=dict(case=k,arm=arm,round=round_no,original=x.rel(f),original_status=old['status'],original_error=old.get('error'))
        response=f.parent/'response.raw.json'
        if not response.exists():
            r.update(status='no_response_historical_timeout',cause='client reached 180.103 seconds; no response or tokens; resource cause not proven')
        else:
            content=x.read(response)['message']['content']
            try:
                cs=interface.extract(content,d,'offline_'+k+arm+round_no)
                rows=x.read(PRIOR/'refinement_r04/common'/f'{k}.json')[0]
                q=iso.evaluate(d,rows,cs,f'interface_offline/{k}/{arm}/{round_no}')
                x.append(out/'offline_queries.jsonl',q)
                r.update(status=q['status'],proposal_unchanged=True,ast_sha256=x.digest([{n:c[n] for n in ('antecedent','consequent','delay')} for c in cs]),
                         recovered_interface_rejection='permission:identifier' in old.get('error',''),runs=q['runs'])
            except (AssertionError,KeyError,TypeError,ValueError) as exc:r.update(status='candidate_language_error',error=repr(exc))
        replay.append(r)
    x.dump(out/'historical_replay.json',replay)
    # Real calls are protocol smoke tests, not formal arm data. Use all three
    # affected parents, with the same public projection as the formal runner.
    real=[]
    for k in ('filter','fifo','stat'):
        cs=x.read(PRIOR/'refinement_r04/initial'/f'{k}.json');d=x.read(x.OUT/'frozen'/k/'definition.json')
        rows=x.read(PRIOR/'refinement_r04/common'/f'{k}.json')[0]
        q=iso.evaluate(d,rows,cs,'preflight_initial/'+k);q['case']=k
        x.append(out/'real_queries.jsonl',q)
        r=call_model(k,'preflight',0,cs,[public.feedback(q)],out)
        if r['candidates']:
            after=iso.evaluate(d,rows,r['candidates'],'preflight_after/'+k);after['case']=k
            feedback=public.feedback(after);x.append(out/'real_queries.jsonl',after)
            r=dict(case=k,model_result=r,execution=after['status'],feedback=feedback)
        else:r=dict(case=k,model_result=r,execution='no_candidate')
        real.append(r);print('PREFLIGHT',k,r['execution'],flush=True)
    x.dump(out/'summary.json',dict(historical_proposals=len(replay),historical_responses=sum(r['status']!='no_response_historical_timeout' for r in replay),
        recovered_rejections=sum(r.get('recovered_interface_rejection',False) and r['status']=='ok' for r in replay),
        historical_candidate_errors=[r for r in replay if r['status'] not in ('ok','no_response_historical_timeout')],
        real_calls=real,passed=all(r['execution']=='ok' for r in real),no_manual_changes=True))


def stat_control():
    out=x.OUT/'stat_control';out.mkdir(exist_ok=False);configure()
    d=x.read(x.OUT/'frozen/stat/definition.json');original=x.OUT/'frozen/stat/correct.v'
    old=original.read_text();shutil.copyfile(original,out/'original_correct.v')
    fixed=old.replace('reg [1:0] valid_pipe;','reg [1:0] valid_pipe;\n  reg [7:0] captured_len;')
    fixed=fixed.replace('valid_pipe<=0;stat_len_o<=0;','valid_pipe<=0;stat_len_o<=0;captured_len<=0;')
    fixed=fixed.replace('if(frame_done_i) stat_len_o<=frame_len_i;',
        'if(frame_done_i) captured_len<=frame_len_i; if(valid_pipe[0]) stat_len_o<=captured_len;')
    assert fixed!=old
    (out/'correct_v2.v').write_text(fixed)
    (out/'patch.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),fixed.splitlines(True),fromfile='original_correct.v',tofile='correct_v2.v')))
    # New continuation version only. Preserve both old correct and old mutant.
    shutil.copyfile(original,x.OUT/'frozen/stat/original_correct.v')
    original.write_text(fixed)
    x.dump(out/'specification.json',dict(source=x.read(PRIOR/'frozen/stat/spec_sources.json'),
        accepted='each active pre-NBA sample with frame_done_i=1; no ready/spacing constraint',
        captured='frame_len_i sampled at the same triggering edge',deadline='due sample = trigger + 2',
        overlap='every event has epoch+trigger identity; consecutive events allowed',reset='pending events cancelled, both payload/valid pipeline reset',
        provenance='engineered control correction from existing textual contract, not a real historical bug repair',
        statistical_scope='old stage2 remains original-RTL result; affected stat block will be compared separately'))
    scenarios=[]
    rows=x.read(PRIOR/'runs/supplemental_qa/stat_overlap_minimal/stat/correct/input.json')
    scenarios.append(('19_73',rows))
    for i in range(8):scenarios.append((f'overlap_reset_{i}',x.policy.guided(d,630017+i*419,i)))
    base=x.policy.ordinary(d,630999)
    for i,r in enumerate(base):
        r['frame_done_i']=int(i in (2,3,4,8,9,12,13,14,18));r['frame_len_i']=(19+i*73)%256;r[d['rst']]=int(i>=2 and i not in (4,13))
    scenarios.append(('pending_cancel',base))
    cs=x.read(x.OUT/'frozen/stat/candidates.json')['candidates'];results=[]
    for name,rows in scenarios:
        q=iso.evaluate(d,rows,cs,'stat_control/'+name);x.append(out/'queries.jsonl',q)
        legal=x.read(x.ROOT/q['runs'][0]['run']/'independent_reference.json')
        assert all(c['passed'] for e in legal['events'] for c in e['checks'])
        results.append(dict(scenario=name,query=q,legal_control_pass=True))
    x.dump(out/'summary.json',dict(scenarios=len(results),all_legal_control_pass=True,new_sha256=x.sha(original),old_sha256=x.sha(out/'original_correct.v'),
        old_evidence_relabeling='none: old monitor already recognized overlap as real violation; legacy fixed/buggy signature remains version-specific',results=results))
    print('STAT control qualification',len(results),'passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default=NAME);p.add_argument('action',choices=['init','preflight','stat_control'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;iso.configure=configure;globals()[a.action]()
