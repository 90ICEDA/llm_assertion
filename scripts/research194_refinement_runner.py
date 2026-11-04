"""Bounded, genuinely adaptive native refinement; preparation has no transport.

The backend is injected. Handwritten qualification and external-model execution
have separate provenance. All calls use a newly approved research194 seal; the
research192 permission is intentionally unusable here.
"""
import copy
import hashlib
import json
from pathlib import Path
import time
import threading
import ast
import research194_refinement as r
import research194_cases as cases
import research194_metrics as metrics

ROOT=Path(__file__).resolve().parents[1]
ENDPOINT='https://api.highwayapi.ai/openai/chat/completions'
SEEDS=(19407,19419)

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def file_hash(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind_measurement(measurement,candidate):
    result=copy.deepcopy(measurement)
    if result.get('candidate_sha256')!=r.digest(candidate):raise ValueError('native_candidate_binding')
    for ev in result.get('evidence',[]):
        if ev.get('candidate_sha256',r.digest(candidate))!=r.digest(candidate):raise ValueError('evidence_candidate_binding')
        ev['candidate_sha256']=r.digest(candidate)
    bindings={}
    for job in result.get('executions',[]):
        folder=Path(job['folder'])
        for name in ('result.json','reference.json','execute.log','compile.json','execute.json','wave.vcd','tb.sv','tool_version.json'):
            p=folder/name
            if p.is_file():bindings[str(p.resolve())]=file_hash(p)
    result['native_bindings']=bindings
    result.update(metrics.temporal_detection(result))
    return result


def query_union(*groups):
    result={}
    for group in groups:
        for query in group:
            key=r.digest(dict(rows=query['rows'],fault=query.get('_fault','primary')))
            result.setdefault(key,copy.deepcopy(query))
    return list(result.values())


def merge_measurements(candidate,measurements):
    """Compose already-paid same-candidate histories; never execute new inputs."""
    items=[bind_measurement(m,candidate) for m in measurements]
    result=copy.deepcopy(items[0])
    for key in ('targets','detected_ids','triggered_ids','target_transaction_ids','covered_obligations'):
        result[key]=sorted({x for item in items for x in item.get(key,[])})
    for key in ('evidence','executions','critical_unknown'):
        result[key]=[copy.deepcopy(x) for item in items for x in item.get(key,[])]
    result['false_positives']=list({x['id']:x for item in items for x in item.get('false_positives',[])}.values())
    for key in ('native_complete','reference_complete'):result[key]=all(m.get(key) is True for m in items)
    result['native_bindings']={path:value for m in items for path,value in m['native_bindings'].items()}
    result['cost']=dict(native_compile_attempts=0,native_execution_attempts=0,native_seconds=0,wall_seconds=0,
        reused_native_compile_attempts=sum(m['cost'].get('native_compile_attempts',0) for m in items),
        logical_native_jobs=sum(m['cost'].get('native_compile_attempts',0) for m in items),model_calls=0)
    result['history_composition']=dict(source_measurement_sha256=[r.digest(m) for m in measurements],
        physical_native_jobs=0,reason='same candidate; union only already acquired public/development inputs')
    result.update(metrics.temporal_detection(result))
    return result


def model_evidence(measurement):
    """Stable first-target observations; bounded legal examples, raw all retained.

Every false alarm is retained. This is identical across arms and is not oracle
search: it only reduces repeated legal samples in already-paid native results.
"""
    records=r.normalize_evidence(measurement.get('evidence',[]));selected={};legal_count={}
    for row in records:
        if row['label']=='violation' and row.get('counted_target',True) is False:continue
        if row['id'] in selected:continue
        alarm=any(a.get('failure') is True for a in row['assertions'])
        if row['label']=='legal' and not alarm:
            key=row.get('obligation')
            if legal_count.get(key,0)>=8:continue
            legal_count[key]=legal_count.get(key,0)+1
        if row['label']=='violation':
            row['detection_status']=('timely' if row['id'] in measurement['detected_ids'] else
                'late_only' if row['id'] in measurement.get('transaction_detected_ids',[]) else 'not_detected')
            row['detection_delay_cycles']=measurement.get('detection_delay_cycles',{}).get(row['id'])
        selected[row['id']]=row
    return list(selected.values())


class CaseAdapter:
    def __init__(self,case_id):
        self.case_id=case_id;self.case=cases.get_case(case_id)
        self.case['specification']=self.case.get('specification',self.case.get('spec',self.case.get('description')))
        self.case['rtl']={name:(ROOT/name).read_text(encoding='utf-8') for name in self.case.get('sources',[])}
    def validate(self,candidate):return cases.validate(self.case_id,candidate)
    def evaluate(self,candidate,out,queries):
        return bind_measurement(cases.evaluate(self.case_id,candidate,out,queries=queries,split='development'),candidate)


def controller_from(adapter,strategy,baseline,max_rounds=3):
    baseline=bind_measurement(baseline,adapter.case['initial'])
    return r.Controller(adapter.case['initial'],strategy,adapter.case['obligations'],
        protected=set(baseline['detected_ids']),protected_transactions=set(baseline['transaction_detected_ids']),max_rounds=max_rounds)


def prepare_first(adapter,strategy,seed,baseline,queries,acquired,out,max_rounds=3,current_measurement=None):
    """Freeze exact first request and state. No model/credential access occurs."""
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    initial=adapter.case['initial'];controller=controller_from(adapter,strategy,baseline,max_rounds)
    measurement=bind_measurement(current_measurement or acquired['measurement'],initial)
    # A preparation bundle must expose all selected queries at once and include
    # baseline history; caller may supply a real cumulative current measurement.
    if set(baseline['detected_ids'])-set(measurement['targets']):
        raise ValueError('first_measurement_omits_protected_history')
    evidence=model_evidence(measurement)
    controller.consider_empty_domain(measurement)
    request=r.build_request(adapter.case,controller,evidence,seed,0)
    state=dict(case_id=adapter.case_id,strategy=strategy,seed=seed,max_rounds=max_rounds,
        initial=initial,baseline=baseline,queries=queries,first_acquisition=acquired,
        first_measurement=measurement,public_evidence=evidence,
        first_request_sha256=r.digest(request),case_sha256=r.digest(adapter.case))
    dump(out/'state.json',state);dump(out/'request.preview.json',request)
    return dict(state=str(out/'state.json'),request=str(out/'request.preview.json'),
                request_sha256=r.digest(request),state_sha256=file_hash(out/'state.json'))


def run_trajectory(adapter,strategy,seed,out,baseline,public_queries,session,backend,
                   max_rounds=3,prepared=None):
    """One paid acquisition per round, cumulative native history per proposal.

backend(request, folder) returns (call_record, decoded_JSON_or_None). A malformed
model output consumes that round. A transport failure stops, never retries.
No current/proposal measurement is borrowed from another candidate hash.
"""
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    controller=controller_from(adapter,strategy,baseline,max_rounds)
    queries=copy.deepcopy(public_queries);current=bind_measurement(baseline,controller.active)
    records=[];costs=[];acquisitions=[];started=time.monotonic()
    trajectory_id=f'{adapter.case_id}/seed{seed}/{getattr(session,"strategy","unknown")}/{strategy}'
    dump(out/'initial.json',controller.active);dump(out/'baseline.json',current)
    dump(out/'frozen.json',controller.active);dump(out/'terminal_measurement.json',current)
    for index in range(max_rounds):
        if controller.finished:break
        rd=out/f'round{index+1:02}';rd.mkdir()
        if index==0 and prepared is not None:
            state=read(Path(prepared)/'state.json');stored=read(Path(prepared)/'request.preview.json')
            if (state['case_id'],state['strategy'],state['seed'])!=(adapter.case_id,strategy,seed):raise ValueError('prepared_arm_mismatch')
            if state['case_sha256']!=r.digest(adapter.case):raise ValueError('prepared_case_changed')
            acquired=state['first_acquisition'];queries=state['queries'];current=state['first_measurement']
            acquired=session.reuse_acquisition(acquired,controller.active)
        else:
            try:acquired=session.acquire(controller.active,index,history=r.normalize_evidence(current['evidence']))
            except Exception as exc:
                current=copy.deepcopy(current);current['native_complete']=False
                current['critical_unknown'].append(dict(reason='acquisition_interrupted',round=index+1,error_type=type(exc).__name__))
                records.append(dict(round=index+1,status='infrastructure_interrupted',phase='acquisition',error_type=type(exc).__name__,model_calls=0))
                controller.finished=True;break
            selected=acquired.get('queries',[acquired['query']] if 'query' in acquired else [])
            queries=query_union(queries,selected)
            # Existing history was already measured on precisely this retained
            # candidate. Merge only its new same-candidate acquisition, avoiding
            # an unnecessary repeat compilation of unchanged candidate/history.
            current=merge_measurements(controller.active,[current,acquired['measurement']])
            dump(rd/'current_history_reuse.json',current['history_composition'])
            costs.append(dict(purpose='current_history_reuse',round=index+1,**current['cost']))
        acquisitions.append(acquired);costs.append(dict(purpose='acquisition',round=index+1,**acquired.get('cost',{})))
        dump(rd/'evidence_linkage.json',dict(refinement_trajectory_id=trajectory_id,
            source_acquisition_task_id=acquired.get('task_id'),source_acquisition_sha256=r.digest(acquired),
            candidate_sha256=r.digest(controller.active),evidence_ids=sorted({e['id'] for e in current['evidence']})))
        if current.get('candidate_sha256')!=r.digest(controller.active):raise ValueError('current_history_binding')
        if current['critical_unknown'] or not current.get('native_complete') or not current.get('reference_complete'):
            records.append(dict(round=index+1,status='unknown_acquisition_or_history',model_calls=0));break
        evidence=model_evidence(current)
        controller.consider_empty_domain(current)
        request=r.build_request(adapter.case,controller,evidence,seed,index)
        if index==0 and prepared is not None and request!=stored:raise ValueError('sealed_first_request_mismatch')
        dump(rd/'request.preview.json',request);dump(rd/'current_measurement.json',current)
        dump(out/'terminal_measurement.json',current);dump(out/'trajectory_queries.json',queries)
        dump(rd/'localization.json',r.localize(controller.active,evidence))
        try:call,value=backend(request,rd/'model_call')
        except Exception as exc:
            attempted=(rd/'model_call'/'attempt.json').exists()
            call=dict(status='model_boundary_exception',model_calls=int(attempted),prompt_tokens=None,completion_tokens=None,error_type=type(exc).__name__)
            value=None
        record=dict(round=index+1,trajectory_id=trajectory_id,request_sha256=r.digest(request),model=call)
        records.append(record);dump(out/'rounds.json',records)
        if value is None:
            if call.get('status')=='response_received' and call.get('candidate_status')=='interface_rejected':
                controller.interface_failure('decode_error',str(call.get('candidate_error')))
                record['status']='interface_rejected';continue
            record['status']='model_transport_or_decode_failure';controller.finished=True;break
        dump(rd/'model_edit.json',value)
        try:proposal,edits=controller.parse(value,evidence,adapter.validate)
        except (ValueError,TypeError,KeyError) as exc:
            controller.interface_failure(type(exc).__name__,str(exc));record.update(status='interface_rejected',error=str(exc))
            dump(out/'controller_history.json',controller.history);continue
        dump(rd/'proposal.json',proposal);dump(rd/'edit_record.json',edits)
        if proposal==controller.active:
            controller.interface_failure('no_semantic_change','Byte-identical proposal; no native fallback authorization.')
            record['status']='no_change';continue
        try:measured=adapter.evaluate(proposal,rd/'proposal_native',queries)
        except Exception as exc:
            record.update(status='infrastructure_interrupted',error_type=type(exc).__name__,
                error=str(exc),proposal_unknown=True,causal_comparison_eligible=False)
            controller.finished=True;break
        costs.append(dict(purpose='proposal_history',round=index+1,**measured['cost']))
        entry=controller.observe(proposal,measured,current_targets=acquired['measurement']['targets'],edit_record=edits,baseline=current)
        record.update(status='accepted' if entry['decision']['accepted'] else 'rejected',decision=entry['decision'],stage=entry['stage'])
        if entry['decision']['accepted']:
            current=measured;dump(out/'frozen.json',controller.active);dump(out/'terminal_measurement.json',current)
        dump(out/'controller_history.json',controller.history);dump(out/'rounds.json',records)
    dump(out/'rounds.json',records);dump(out/'cost_components.json',costs)
    dump(out/'acquisitions.json',acquisitions);dump(out/'controller_history.json',controller.history)
    dump(out/'frozen.json',controller.active)
    dump(out/'terminal_measurement.json',current)
    dump(out/'trajectory_queries.json',queries)
    outcome=dict(case_id=adapter.case_id,strategy=strategy,seed=seed,
        trajectory_id=trajectory_id,
        search=getattr(session,'strategy',None),search_strategy=getattr(session,'strategy',None),parent_bug=adapter.case.get('parent_bug',adapter.case_id+'/artificial'),
        status='frozen',frozen_sha256=r.digest(controller.active),initial_sha256=r.digest(controller.initial),
        model_calls=sum(x.get('model',{}).get('model_calls',0) for x in records),
        actual_model_calls=sum(x.get('model',{}).get('model_calls',0) for x in records),
        accepted_rounds=sum(x.get('status')=='accepted' for x in records),
        effective_rounds=sum(x.get('status')=='accepted' for x in records),
        regression_proposed=sum(bool(x.get('decision',{}).get('regression')) for x in records),
        regression_accepted=sum(x.get('status')=='accepted' and bool(x.get('decision',{}).get('regression')) for x in records),
        interface_failures=sum(x.get('status') in ('interface_rejected','no_change') for x in records),
        terminal_measurement_sha256=r.digest(current),acquired_query_submissions=len(acquisitions),
        native_compile_attempts=sum(x.get('native_compile_attempts',0) for x in costs),
        native_execution_attempts=sum(x.get('native_execution_attempts',0) for x in costs),
        model_tokens_known=sum((x.get('model',{}).get('prompt_tokens') or 0)+(x.get('model',{}).get('completion_tokens') or 0) for x in records),
        model_token_unknown_calls=sum(x.get('model',{}).get('model_calls',0)>0 and (x['model'].get('prompt_tokens') is None or x['model'].get('completion_tokens') is None) for x in records),
        provenance=getattr(backend,'provenance','injected_backend_requires_explicit_provenance'),
        causal_comparison_eligible=not any(x.get('status') in ('infrastructure_interrupted','unknown_acquisition_or_history') for x in records),
        wall_seconds=time.monotonic()-started,independent_acceptance='not_read_or_run')
    dump(out/'outcome.json',outcome)
    return outcome


def freeze_interruption(folder,state,error,search_strategy,condition=None):
    """Keep population and last saved accepted candidate after outer exceptions."""
    folder=Path(folder);candidate=read(folder/'frozen.json') if (folder/'frozen.json').exists() else state['initial']
    measurement=read(folder/'terminal_measurement.json') if (folder/'terminal_measurement.json').exists() else state['first_measurement']
    if measurement.get('candidate_sha256')!=r.digest(candidate):
        measurement=copy.deepcopy(measurement);measurement['critical_unknown'].append(dict(reason='checkpoint_candidate_measurement_mismatch'));measurement['native_complete']=False
    submitted=len(list(folder.rglob('attempt.json')))
    dump(folder/'frozen.json',candidate);dump(folder/'terminal_measurement.json',measurement)
    if not (folder/'trajectory_queries.json').exists():dump(folder/'trajectory_queries.json',state['queries'])
    outcome=dict(case_id=state['case_id'],seed=state['seed'],strategy=state['strategy'],search_strategy=search_strategy,
        status='frozen',termination_reason='unhandled_interruption_retained_last_checkpoint',provenance='real_remote_model',
        model_calls=submitted,actual_model_calls=submitted,model_call_count_basis='persisted submission attempt records; no retries',
        initial_sha256=r.digest(state['initial']),frozen_sha256=r.digest(candidate),causal_comparison_eligible=False,
        error_type=type(error).__name__,error=str(error),model_token_cost_unknown=True)
    if condition is not None:outcome['condition']=condition
    dump(folder/'outcome.json',outcome);return outcome


class HandwrittenBackend:
    provenance='handwritten_qualification; zero model calls; not LLM improvement'
    def __init__(self,responses):self.responses=iter(responses)
    def __call__(self,request,folder):
        value=next(self.responses);dump(Path(folder)/'handwritten_fixture.json',value)
        return dict(model_calls=0,status='handwritten_fixture',prompt_tokens=0,completion_tokens=0),copy.deepcopy(value)


def source_bindings():
    names=['research194_refinement.py','research194_refinement_runner.py','research194_refinement_prepare.py','research194_cases.py',
           'research194_ibex.py','research194_active_search.py','research194_active_semantics.py',
           'research69_deadline_transport.py','research_native_runner.py']
    pending=[ROOT/'scripts'/name for name in names];result={}
    while pending:
        path=pending.pop()
        if str(path) in result:continue
        result[str(path)]=file_hash(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            modules=([a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) else [])
            for name in modules:
                if name and name.startswith('research'):
                    dependency=ROOT/'scripts'/(name+'.py')
                    if dependency.exists():pending.append(dependency)
    return result


def seal_package(out,entries,case_ids,maximum_rounds=3):
    """Future request bodies depend on real outputs; seal builder, not invented data."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    protocol=dict(version='research194',endpoint=ENDPOINT,model='deepseek/deepseek-v3-0324',
        seeds=list(SEEDS),temperature=.2,max_output_tokens=2048,timeout_seconds=300,retries=0,
        case_ids=case_ids,trajectories=[list(x) for x in r.TRAJECTORIES],max_rounds=maximum_rounds,
        maximum_model_calls=sum(e.get('mode')!='blocked_unknown' for e in entries)*maximum_rounds,
        fixed_trajectory_population=len(entries),maximum_population_model_calls=len(entries)*maximum_rounds,
        exact_first_requests=sum(e.get('mode')!='blocked_unknown' for e in entries),future_requests='Generated only from real earlier responses and development native evidence by sealed code; saved before dispatch.',
        native_budget=dict(public_baseline_queries_per_case_seed=1,search_queries_per_trajectory=maximum_rounds,
            native_jobs_per_query=2,proposal_gate_queries_per_round=list(range(2,maximum_rounds+2)),
            maximum_logical_native_jobs_per_trajectory=2*maximum_rounds+2*sum(range(2,maximum_rounds+2)),
            current_history='Reuse only exact candidate-bound earlier native records; physical cost zero, logical reuse recorded.',
            duplicate_inputs='Deduplicate only identical input-row hashes in proposal replay; submitted search query still costs.'),
        external_payload='Original/project RTL, specification, SVA, confirmed development waveforms/evidence and structured feedback.',
        authorization='NOT AUTHORIZED; old research192 16-call authorization is exhausted.',
        fault_augmentation='Excluded; separate actual package required.',source_bindings=source_bindings(),entries=entries)
    # Bind original RTL and adjacent include files, but do not disclose fault
    # catalogue or independent descriptors in model messages.
    for cid in case_ids:
        cfg=cases.get_case(cid)
        for source in cfg.get('sources',[]):
            p=ROOT/source;protocol['source_bindings'][str(p)]=file_hash(p)
            for include in p.parent.rglob('*.svh'):
                protocol['source_bindings'][str(include)]=file_hash(include)
    for include in (ROOT/'external/common_cells/include').rglob('*.svh'):
        protocol['source_bindings'][str(include)]=file_hash(include)
    for include in (ROOT/'external/opentitan/hw/ip/prim/rtl').rglob('*.svh'):
        protocol['source_bindings'][str(include)]=file_hash(include)
    dump(out/'protocol.json',protocol)
    dump(out/'seal.json',dict(protocol_sha256=file_hash(out/'protocol.json'),version='research194'))
    return protocol


def verify_package(prepared):
    prepared=Path(prepared);seal=read(prepared/'seal.json');p=read(prepared/'protocol.json')
    if seal['protocol_sha256']!=file_hash(prepared/'protocol.json'):raise ValueError('protocol_changed')
    for path,expected in p['source_bindings'].items():
        if file_hash(path)!=expected:raise ValueError('source_changed:'+path)
    for e in p['entries']:
        if file_hash(e['state'])!=e['state_sha256']:raise ValueError('prepared_input_changed')
        if e.get('mode')!='blocked_unknown' and r.digest(read(e['request']))!=e['request_sha256']:raise ValueError('prepared_request_changed')
        state=read(e['state'])
        for path,expected in state['first_measurement']['native_bindings'].items():
            if file_hash(path)!=expected:raise ValueError('native_evidence_changed:'+path)
    return p,seal['protocol_sha256']


class ApprovedRemoteBackend:
    """Construct only after a NEW user authorization bound to this exact seal.

No automatic authorization is inferred from CLI arguments or older grants.
The root operator records the actual user message/reference in authorization.
"""
    provenance='real_remote_model'
    def __init__(self,prepared,authorization,ledger):
        self.prepared=Path(prepared);self.protocol,self.seal=verify_package(prepared)
        auth=read(authorization)
        if auth.get('version')!='research194' or auth.get('protocol_sha256')!=self.seal or auth.get('endpoint')!=ENDPOINT or auth.get('approved') is not True or not auth.get('user_message_reference'):
            raise ValueError('new_explicit_seal_bound_user_authorization_required')
        self.limit=min(auth['maximum_model_calls'],self.protocol['maximum_model_calls']);self.ledger=Path(ledger)
        if self.ledger.exists():raise ValueError('ledger_exists_no_implicit_resume_or_retry')
        self.calls=[];self.lock=threading.RLock();dump(self.ledger,self.calls)
    def __call__(self,request,folder):
        verify_package(self.prepared)
        if request['model']!=self.protocol['model'] or request['max_tokens']!=2048 or request['temperature']!=.2:raise ValueError('request_configuration_changed')
        # Reserve physical slot before transport, even if construction fails.
        with self.lock:
            if len(self.calls)>=self.limit:raise ValueError('package_budget_exhausted')
            row=dict(index=len(self.calls),request_sha256=r.digest(request),status='reserved_no_retry',folder=str(folder))
            self.calls.append(row);dump(self.ledger,self.calls)
        import research69_deadline_transport as transport
        class Exact(transport.RemoteModel):
            def _payload(inner,*args):return copy.deepcopy(request)
            def save_decoded_output(inner,path,value,current,secret):
                dump(Path(path)/'model_edit.json',value)
                return value,'raw_json_no_semantic_rewrite'
        config=dict(remote_url=ENDPOINT,remote_model=request['model'],max_model_calls=1,
            max_tokens=sum(len(m['content'].encode()) for m in request['messages'])+8192,
            max_wall_seconds=360,call_timeout=300,options=dict(seed=request['seed'],temperature=.2,num_predict=2048))
        model=Exact(Path(folder).parent/'transport',config)
        metadata=Path(folder).parent/'transport'/'remote_transport_config.json'
        meta=read(metadata);meta['timeout_seconds']=300;meta['max_output_tokens']=2048;meta['timeout_metadata_version']='research194_actual_deadline';dump(metadata,meta)
        result,value=model.call(folder,[],None,{},'research194_bounded_refinement')
        with self.lock:
            row.update(status=result['status'],model_calls=result.get('model_calls',1));dump(self.ledger,self.calls)
        return result,value
