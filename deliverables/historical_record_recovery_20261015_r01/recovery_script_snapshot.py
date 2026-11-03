"""Recover historical provenance without overwriting sealed experiments.

Only project-specific source edits are extracted from local session logs. No
conversation text, credentials, or unrelated session payloads are archived.
"""
import argparse
import ast
import hashlib
import json
import re
import subprocess
import importlib.util
import sys
import shutil
import tarfile
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/historical_record_recovery_20261015_r01'


def sha(data):return hashlib.sha256(data).hexdigest()
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def source_history():
    base=Path('/mnt/c/Users/没有惊喜/.codex/sessions/2026/10')
    wanted={'research15_evidence.py','research15_acceptance.py'}
    events=[];scanned=[]
    for day in ('14','15'):
        for path in sorted((base/day).glob('*.jsonl')):
            relevant=False
            with path.open(encoding='utf-8') as stream:
                for number,line in enumerate(stream,1):
                    try:record=json.loads(line)
                    except json.JSONDecodeError:continue
                    payload=record.get('payload',{})
                    if record.get('type')=='session_meta':
                        relevant='assertionforge-main1' in str(payload.get('cwd','')).lower()
                    if not relevant or payload.get('type') not in ('function_call','custom_tool_call'):continue
                    code=payload.get('arguments',payload.get('input',''))
                    if not isinstance(code,str) or not any(n in code for n in wanted):continue
                    patches=[]
                    for match in re.finditer(r'tools\.apply_patch\s*\(\s*(?=")',code):
                        try:value,_=json.JSONDecoder().raw_decode(code[match.end():]);patches.append(value)
                        except json.JSONDecodeError:continue
                    if payload.get('name','').endswith('apply_patch') and code.startswith('*** Begin Patch'):patches.append(code)
                    for patch in patches:
                        for match in re.finditer(r'^\*\*\* (Add|Update) File: ([^\n]+)\n(.*?)(?=^\*\*\* (?:Add|Update|Delete|End)|\Z)',patch,re.M|re.S):
                            kind,name,body=match.groups();name=name.strip().replace('\\','/').rsplit('/',1)[-1]
                            if name not in wanted:continue
                            events.append(dict(timestamp=record.get('timestamp'),call_id=payload.get('call_id'),
                                session_file=path.name,line=number,kind=kind,name=name,body=body))
            if relevant:scanned.append(dict(file=path.name,sha256=sha(path.read_bytes())))
    # Resumed/forked sessions can contain identical inherited calls.
    unique={}
    for event in events:unique[(event['call_id'],event['name'],event['body'])]=event
    events=sorted(unique.values(),key=lambda e:(e['timestamp'] or '',e['session_file'],e['line']))
    states={};versions=[];errors=[]
    for index,event in enumerate(events):
        name=event['name'];body=event['body']
        try:
            if event['kind']=='Add':
                content='\n'.join(line[1:] for line in body.splitlines() if line.startswith('+'))+'\n'
                if name in states and states[name]!=content:raise ValueError('second conflicting Add')
            else:
                content=states[name]
                for hunk in re.split(r'^@@[^\n]*\n',body,flags=re.M):
                    old=[];new=[]
                    for line in hunk.splitlines():
                        if not line or line.startswith('***'):continue
                        if line[0] in ' -':old.append(line[1:])
                        if line[0] in ' +':new.append(line[1:])
                    if not old and not new:continue
                    before='\n'.join(old)+'\n';after='\n'.join(new)+('\n' if new else '')
                    if content.count(before)!=1:raise ValueError('nonunique or missing patch context')
                    content=content.replace(before,after,1)
            ast.parse(content)
            states[name]=content
            folder=OUT/'source_history'/name/f'v{index:03d}'
            folder.mkdir(parents=True,exist_ok=True)
            (folder/name).write_text(content,encoding='utf-8')
            (folder/'source_edit.patch').write_text(f'*** {event["kind"]} File: scripts/{name}\n'+body,encoding='utf-8')
            item={k:v for k,v in event.items() if k!='body'}
            item.update(source_sha256=sha(content.encode()),recovered_file=str((folder/name).relative_to(ROOT)))
            dump(folder/'provenance.json',item);versions.append(item)
        except (KeyError,ValueError,SyntaxError) as exc:errors.append({k:v for k,v in event.items() if k!='body'}|{'error':str(exc)})
    comparisons=[]
    for name,content in states.items():
        current=(ROOT/'scripts'/name).read_text()
        comparisons.append(dict(file=name,exact_normalized_text_match=current==content,
                                recovered_sha256=sha(content.encode()),current_normalized_sha256=sha(current.encode())))
    result=dict(scanned_project_sessions=scanned,versions=versions,errors=errors,final_state_comparisons=comparisons,
        scope='Historical source reconstructed from chronological original edit records; only source patches archived. Process-memory identity must additionally be inferred from invocation chronology and original replay reproduction.')
    dump(OUT/'source_history/index.json',result)
    print(json.dumps(dict(versions=len(versions),errors=len(errors),comparisons=comparisons)))


def git_provenance():
    folder=OUT/'git_provenance';folder.mkdir(parents=True,exist_ok=True)
    dep=ROOT/'external/verilog-axis'
    def git(*args):return subprocess.run(['git','-C',str(dep),*args],capture_output=True,check=True).stdout
    commit=git('rev-parse','HEAD').decode().strip()
    status=git('status','--porcelain','--untracked-files=no').decode()
    (folder/'dependency_status.txt').write_text(status)
    (folder/'dependency_commit.txt').write_bytes(git('show','--no-patch','--format=fuller',commit))
    comparisons=[]
    for filename in ('axis_fifo.v','axis_stat_counter.v'):
        original=git('show',f'{commit}:rtl/{filename}');local=(dep/'rtl'/filename).read_bytes()
        (folder/('git_'+filename)).write_bytes(original)
        comparisons.append(dict(file=filename,commit=commit,git_blob=git('rev-parse',f'{commit}:rtl/{filename}').decode().strip(),
            committed_sha256=sha(original),working_sha256=sha(local),exact_bytes_equal=original==local,
            newline_normalized_equal=original.replace(b'\r\n',b'\n')==local.replace(b'\r\n',b'\n'),
            pinned_source_url=f'https://raw.githubusercontent.com/alexforencich/verilog-axis/{commit}/rtl/{filename}'))
    evidence=[]
    paths=[ROOT/'deliverables/research_fifo_20261014_r01/config.json',ROOT/'deliverables/research15_search_20261015_r01/fixed_initial_negative/protocol.json']
    for path in paths:
        config=read(path);recorded=config.get('source_sha256')
        evidence.append(dict(experiment_record=str(path.relative_to(ROOT)),recorded_rtl_sha256=recorded,
            matches_working_fifo=recorded==comparisons[0]['working_sha256']))
    root_entries=[p.name for p in (ROOT/'.git').iterdir()] if (ROOT/'.git').is_dir() else None
    result=dict(root_git_entries=root_entries,root_historical_HEAD_recovered=False,
        dependency_HEAD=commit,dependency_is_shallow=(dep/'.git/shallow').exists(),source_comparisons=comparisons,
        historical_experiment_matches=evidence,
        conclusion='Dependency revision recovered locally; exact bytes or explicitly reported line-ending normalization links experiment RTL to committed blob. Root project commit cannot be inferred from a dependency commit.')
    dump(folder/'result.json',result);print(json.dumps(result))


def replay_source_history():
    index=read(OUT/'source_history/index.json');versions=index['versions']
    gate_versions=[v for v in versions if v['name']=='research15_acceptance.py']
    adapters=[v for v in versions if v['name']=='research15_evidence.py']
    actual=ROOT/'deliverables/research15_native_20261015_r01'
    cohorts=[actual/'initial_qualification/original',actual/'initial_qualification/semantic_repair',actual/'initial_temporal_continuation']
    checks=[];matched=[]
    def module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec)
        sys.modules[name]=mod;spec.loader.exec_module(mod);return mod
    for adapter in adapters:
        gate=max((v for v in gate_versions if v['timestamp']<=adapter['timestamp']),key=lambda v:v['timestamp'])
        g=module('research15_acceptance',ROOT/gate['recovered_file'])
        a=module('recovered_historical_evidence',ROOT/adapter['recovered_file'])
        for cohort in cohorts:
            old=read(cohort/'ledger.json')
            output=a.paired_ledger(read(cohort/'correct/replay.json'),read(cohort/'corrupt/replay.json'),
                                   'initial_qualification:d2:p0:s2026101501')
            info=g.inspect(output['ledger'])
            record=dict(cohort=str(cohort.relative_to(ROOT)),adapter=adapter['recovered_file'],gate=gate['recovered_file'],
                exact_json_match=output==old,original_sha256=sha(json.dumps(old,sort_keys=True).encode()),
                recomputed_sha256=sha(json.dumps(output,sort_keys=True).encode()),
                counts={k:len(info[k]) for k in ('rows','unknown','false_positives','detections','misses','triggers')})
            checks.append(record)
            if record['exact_json_match']:matched.append(record)
    invocations=[]
    base=Path('/mnt/c/Users/没有惊喜/.codex/sessions/2026/10')
    for item in index['scanned_project_sessions']:
        matches=list(base.glob('*/'+item['file']))
        if not matches:continue
        for number,line in enumerate(matches[0].read_text().splitlines(),1):
            rec=json.loads(line);payload=rec.get('payload',{})
            if payload.get('type') not in ('function_call','custom_tool_call'):continue
            code=payload.get('arguments',payload.get('input',''))
            commands=[]
            try:
                argument=json.loads(code)
                if isinstance(argument,dict) and isinstance(argument.get('cmd'),str):commands.append(argument['cmd'])
            except (json.JSONDecodeError,TypeError):pass
            for m in re.finditer(r'(?:\bcmd|"cmd")\s*:\s*("(?:\\.|[^"\\])*")',code):
                try:commands.append(json.loads(m[1]))
                except json.JSONDecodeError:pass
            for shell in set(commands):
                for command in re.findall(r'python3(?: -u)? (?:/mnt/d/AssertionForge-main1/)?scripts/(?:research15_native_models\.py qualify|research15_native_temporal_repair\.py)',shell):
                    invocations.append(dict(timestamp=rec.get('timestamp'),command=command,session_file=item['file'],line=number))
    result=dict(checks=checks,matched_original_ledgers=matched,invocations=invocations,
        all_three_original_ledgers_reproduced=all(any(c['cohort']==str(p.relative_to(ROOT)) for c in matched) for p in cohorts),
        simulation_calls=0,model_calls=0,
        scope='Recompute the complete original JSON ledger from archived actual RTL replays using recovered historical Python. Exact output equality plus chronological original edits supports historical reconstruction. It is not a newly obtained old process-memory dump and does not turn erroneous old judgments into valid findings.')
    dump(OUT/'source_history/replay_validation.json',result)
    print(json.dumps(dict(all_three_original_ledgers_reproduced=result['all_three_original_ledgers_reproduced'],matches=matched,invocations=invocations)))


def related_repository():
    other=Path('/mnt/d/AssertionForge-main')
    def git(*args):return subprocess.run(['git','-C',str(other),*args],capture_output=True)
    head=git('rev-parse','HEAD').stdout.decode().strip()
    commits=git('log','--all','--format=%H %aI').stdout.decode().splitlines()
    paths=['README.md','scripts/research15_evidence.py','scripts/research15_acceptance.py',
           'scripts/research_native_closed_loop.py',
           'rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early/correct.v',
           'rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early/case_metadata.json']
    records=[]
    for path in paths:
        obj=git('show',f'{head}:{path}');local=ROOT/path
        record=dict(path=path,in_related_HEAD=obj.returncode==0,current_exists=local.exists())
        if obj.returncode==0:
            record.update(related_sha256=sha(obj.stdout),current_sha256=sha(local.read_bytes()) if local.exists() else None,
                same_normalized_text=local.exists() and obj.stdout.replace(b'\r\n',b'\n')==local.read_bytes().replace(b'\r\n',b'\n'))
        history=git('log','--all','--format=%H %aI','--',path).stdout.decode().splitlines()
        record['commits_touching_path']=history
        records.append(record)
    dump(OUT/'git_provenance/related_repository.json',dict(directory=str(other),HEAD=head,commits=commits,files=records,
        identity_claim='Related checkout only; not the original experimental checkout or a recovered root HEAD. Matching selected files cannot establish identical uncommitted/untracked state.'))
    print(json.dumps(dict(HEAD=head,commit_count=len(commits),files=records)))


def cancelled_usage():
    folder=OUT/'cancelled_usage';folder.mkdir(parents=True,exist_ok=True)
    service=ROOT/'deliverables/research_gate_20261014_r01/service/server.log'
    lines=service.read_text().splitlines()
    start=next(i for i,s in enumerate(lines) if 'prompt=18354' in s)
    end=next(i for i,s in enumerate(lines[start:],start) if 'task 129' in s and 'stop processing' in s)
    # Store only task-specific lines and its surrounding truncation/HTTP result.
    selected=[dict(line=i+1,text=lines[i]) for i in range(start,end+1)
              if 'task 129' in lines[i] or 'id_task = 129' in lines[i] or 'prompt=18354' in lines[i] or '[GIN]' in lines[i]]
    dump(folder/'service_observations.json',selected)
    base=ROOT/'deliverables/research_native_20261014_r01/closed_loop/model_calls/revision'
    originals={}
    for name in ('attempt.json','cancellation.json','request.json'):
        shutil.copy2(base/name,folder/name);originals[name]=sha((base/name).read_bytes())
    attempts=read(base/'attempt.json')
    result=dict(status='partially_recovered_final_usage_unavailable',model_calls=1,retries=0,
        provider_prompt_eval_count=None,provider_eval_count=None,
        observations=dict(task_id=129,request_submitted_utc=attempts['started_utc'],
            prompt_token_count_reported_before_truncation=18354,scheduled_prompt_tokens_after_truncation=16383,
            last_progress_report_tokens=7168,released_slot_n_tokens=8196,
            service_reported_http_duration_seconds=258,service_http_status=500,
            service_end_local='2026-10-14 20:04:19 +08:00',
            submitted_to_service_end_wall_timestamp_difference_seconds=254,
            previous_artifact_recording_interval_upper_bound_seconds=388.651028),
        source_file=str(service.relative_to(ROOT)),source_sha256=sha(service.read_bytes()),
        source_lines=[start+1,end+1],original_records=originals,
        unavailable_files=[n for n in ('response.stream.jsonl','response.raw.json','transport_result.json','result.json') if not (base/n).exists()],
        interpretation='258s is the associated server HTTP duration, not exact client latency. Wall timestamps yield 254s and are not identical to that duration. Slot/cache/progress counters are not a final prompt_eval_count or eval_count receipt; do not sum them as actual/billed tokens. No completed response was recorded.',
        exact_recovery_requirements='Original server final task usage or provider request-level accounting receipt; neither exists in the checked records. Re-tokenizing or rerunning the prompt cannot recover consumed historical tokens.',
        forward_solution='Persist request id, monotonic start, every response chunk and final usage in an append-only journal; finalize cancelled status in finally/SIGINT handlers. Record server observations separately when final usage is absent. Never replace unavailable usage with estimated prompt length.')
    dump(folder/'recovered_cost_record.json',result)
    print(json.dumps(dict(status=result['status'],service_duration_seconds=258,final_usage_available=False)))


def archive_inventory():
    records=[]
    for path in sorted(ROOT.glob('*.tar.gz')):
        if path.stat().st_size>100_000_000:
            records.append(dict(file=path.name,bytes=path.stat().st_size,inspected=False,
                reason='Large Python runtime environment archive, not a project backup; body not searched.'))
            continue
        matches=[];count=0
        with tarfile.open(path,'r|gz') as archive:
            for entry in archive:
                count+=1
                if '/.git/' in '/'+entry.name or 'research15_evidence.py' in entry.name or 'case505_axis_stat_counter' in entry.name:
                    matches.append(entry.name)
        records.append(dict(file=path.name,bytes=path.stat().st_size,inspected=True,members=count,relevant_members=matches))
    dump(OUT/'git_provenance/archive_inventory.json',records)
    print(json.dumps(dict(inspected=sum(r['inspected'] for r in records),skipped=sum(not r['inspected'] for r in records),matches=sum(len(r.get('relevant_members',[])) for r in records))))


def stat_origin():
    folder=OUT/'stat_origin';folder.mkdir(parents=True,exist_ok=True)
    case=ROOT/'rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early'
    source=ROOT/'deliverables/research15_history_20261015_r01/stat_spec/audit.json'
    shutil.copy2(source,folder/'prior_audit.json')
    hashes={}
    for name in ('correct.v','buggy.v','case_metadata.json','spec.md','mutation.diff'):
        if (case/name).exists():
            shutil.copy2(case/name,folder/name);hashes[name]=sha((case/name).read_bytes())
    result=dict(parent='case505_axis_stat_counter_frame_pulse_early',status='provenance_mismatch_confirmed_not_repaired',
        actual_upstream_commit=read(OUT/'git_provenance/result.json')['dependency_HEAD'],
        upstream_module='AXI monitor/statistics module',local_module='Eight-line frame_done/stat_valid pipeline surrogate',
        source_hashes=hashes,
        missing=['Transformation/reduction derivation from the claimed upstream module','Confirmed mapping of events, cycles and resets','Upstream authority for local two-cycle and overlap semantics','Original creation patch/session establishing the claimed historical mutation'],
        effective_classification='local_synthetic_pipeline_with_unverified_upstream_mapping',
        effective_historical_admission=False,raw_metadata_preserved=True,
        search_scope=['scripts/src/configs/docs/analysis text search','Related July project Git tree/history','Available July/August/September session logs by exact case id','Small local project/result archives by member names'],
        warning='The existing local metadata says actual_rtl_logic_change/final_verified_admitted. This recovery overlay supersedes its historical-provenance interpretation only; it does not rewrite old files or invalidate the existence of local synthetic simulations.',
        solution_options=[
            dict(option='Preserve the current local case as synthetic engineering data',needed='Explicit local specification owner must define sampled latency, captured length and overlap; all resulting conclusions limited to that contract.',historical_claim_allowed=False),
            dict(option='Recover the missing derivation',needed='Original generation script/patch, its input upstream blob, reduction assumptions, event mapping and equivalence evidence. Archive and independently verify before historical admission.',historical_claim_allowed='only after verification'),
            dict(option='Create a new real upstream task',needed='Select an actual fixed-before/fixed-after upstream commit pair and reproduce its AXI-level behavior with an independent monitor. This is a new experiment, not repair of the old provenance.',historical_claim_allowed='only for the new reproduced task')])
    dump(folder/'effective_provenance.json',result)
    print(json.dumps(dict(status=result['status'],historical_admission=False)))


def fetch_pinned_sources():
    folder=OUT/'git_provenance/official_download';folder.mkdir(parents=True,exist_ok=True)
    records=[]
    for entry in read(OUT/'git_provenance/result.json')['source_comparisons']:
        result=dict(file=entry['file'],url=entry['pinned_source_url'])
        try:
            with urllib.request.urlopen(entry['pinned_source_url'],timeout=30) as response:body=response.read()
            (folder/entry['file']).write_bytes(body)
            result.update(status='downloaded',sha256=sha(body),matches_local_git_blob_sha256=sha(body)==entry['committed_sha256'])
        except Exception as exc:result.update(status='unavailable',error_type=type(exc).__name__)
        records.append(result)
    dump(folder/'result.json',records);print(json.dumps(records))


def content_versions():
    replay=read(OUT/'source_history/replay_validation.json')
    records=[]
    for item in replay['matched_original_ledgers']:
        folder=ROOT/item['cohort']
        call_name={'original':'initial','semantic_repair':'initial_semantic_repair','initial_temporal_continuation':'initial_temporal_repair'}[folder.name]
        call=ROOT/'deliverables/research15_native_20261015_r01/model_calls'/call_name
        paths=[ROOT/item['adapter'],ROOT/item['gate'],folder/'ledger.json',folder/'compiled/tb.sv',
               folder/'compiled/compile.json',folder/'compiled/tool_version.log',
               folder/'correct/replay.json',folder/'corrupt/replay.json',
               ROOT/'external/verilog-axis/rtl/axis_fifo.v']
        paths += [call/n for n in ('request.json','response.raw.json','response.stream.jsonl','candidate.json','candidate.sva','attempt.json','result.json')]
        files={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in paths if p.exists()}
        missing=[str(p.relative_to(ROOT)) for p in paths if not p.exists()]
        records.append(dict(cohort=item['cohort'],artifact_snapshot_id=sha(json.dumps(files,sort_keys=True).encode()),
            files=files,missing=missing,root_git_commit=None,
            recovered_python_adapter=item['adapter'],recovered_python_gate=item['gate'],
            native_rtl_dependency_commit='48ff7a7e2ef782cf778d47910cf85835c64b1bce',
            scope='Content-addressed historical artifact bundle, assembled retrospectively from original records and verified source reconstruction. Not a recovered Git commit or a full original machine snapshot.'))
    dump(OUT/'content_versions.json',records)
    checks=[]
    for base in ('research_integration_20261014_r01','research15_integration_20261015_r01'):
        manifest=ROOT/'deliverables'/base/'delivery_manifest.json'
        for relative,expected in read(manifest).items():
            p=ROOT/relative;actual=sha(p.read_bytes()) if p.exists() else None
            checks.append(dict(path=relative,expected=expected,actual=actual,passed=actual==expected))
    dump(OUT/'preserved_originals.json',dict(passed=all(c['passed'] for c in checks),checks=checks))
    print(json.dumps(dict(content_versions=len(records),missing_files=sum(len(r['missing']) for r in records),original_checks=len(checks),all_originals_unchanged=all(c['passed'] for c in checks))))


def report():
    recovery=read(OUT/'source_history/replay_validation.json')
    assert recovery['all_three_original_ledgers_reproduced']
    assert all(c['exact_normalized_text_match'] for c in read(OUT/'source_history/index.json')['final_state_comparisons'])
    assert read(OUT/'preserved_originals.json')['passed']
    remote=read(OUT/'git_provenance/official_download/windows_result.json')
    assert all(r['matches_local_git_blob'] for r in remote)
    status=[
        dict(id='historical_python_source',status='recovered_and_reproduced',result='从原始编辑日志重建2文件7个源码状态；三份原始ledger全JSON一致；启动命令时序与版本相符。',artifact='source_history/replay_validation.json',remaining='没有旧进程内存转储；结论为有原始编辑链及行为验证的历史源码重建。'),
        dict(id='fifo_upstream_revision',status='recovered_and_verified',result='精确提交48ff7a7e2ef782cf778d47910cf85835c64b1bce；本地Git blob与GitHub固定URL下载字节一致；实验源码仅CRLF/LF不同。',artifact='git_provenance/result.json',remaining='这是使用版本的确认，不证明该文件只存在于此唯一历史提交，也不把人工故障变成上游Bug。'),
        dict(id='root_experiment_git_commit',status='partially_recovered_original_commit_unavailable',result='找到相邻旧仓库49da13029efe7d0080866457d75a3a5bf68811c9，但它没有本轮研究代码。为3份关键历史运行补建内容寻址版本清单。',artifact='content_versions.json',remaining='缺失原工作区Git HEAD/refs/objects或完整当时备份；不能凭相关仓库README相同认定实验提交。'),
        dict(id='cancelled_call_usage',status='partially_recovered_final_usage_unavailable',result='补录HTTP服务耗时258秒、截断前18354与截断后16383的日志计数、slot释放值8196；最终usage仍null。',artifact='cancelled_usage/recovered_cost_record.json',remaining='需要原服务最终task usage或按请求usage回执；重新分词/重跑均不能恢复历史实际消耗。'),
        dict(id='stat_upstream_derivation',status='unrecoverable_from_checked_records_mismatch_confirmed',result='官方固定源码再次核验通过，确认与本地8行pipeline接口不同；已追加有效来源更正，历史admission=false。',artifact='stat_origin/effective_provenance.json',remaining='缺创建脚本/补丁、输入上游blob、约简过程和事件等价映射；旧元数据不能充当证明。')]
    dump(OUT/'recovery_status.json',dict(items=status,model_calls=0,rtl_simulation_calls=0,
        replay_validation='Python recomputation of archived actual RTL observations only',old_experiment_outcomes_changed=False,
        scope='The five historical-record gaps identified in the prior response; future unexecuted experiments are outside this recovery task.'))
    lines=['# 过去实验记录补全报告','',
        '本轮补齐此前列出的5类历史记录缺口。2项已恢复并验证，2项部分补齐，1项确认来源不匹配且缺少历史推导，提供明确解决路径。未执行新的模型或RTL实验，未改写旧封存记录。','',
        '| 缺口 | 状态 | 补全结果 |','|---|---|---|']
    for row in status:lines.append(f'| {row["id"]} | {row["status"]} | {row["result"]} |')
    lines += ['', '## 已恢复：旧适配器执行版本','',
        '从本地原始工具调用记录提取相关代码补丁，重建research15_evidence.py及research15_acceptance.py，共7个源码状态。只保存相关源码编辑、记录位置和哈希，不复制无关会话。最终重建文本与现存文件一致。','',
        '2026-10-15 13:23:41（UTC+8）启动initial资格进程时，适配器v005已写入；13:25:41修改到v006后，原进程仍使用已导入的旧模块。13:27:44额外时序修复启动时使用新版本。这与三份原始结果完全匹配。','',
        '| 历史运行 | 恢复适配器 | 恢复接受门 | 原始ledger复算 |','|---|---|---|---|',
        '| original | v005 | v004 | 全JSON一致 |','| semantic_repair | v005 | v004 | 全JSON一致 |','| initial_temporal_continuation | v006 | v004 | 全JSON一致 |','',
        '这是历史重建，不是事后取得旧进程内存快照。重建能解释旧错误：original旧版仍输出3条所谓detections，修正版本将它们降为unknown。恢复错误版本仅用于可复现性，不能恢复其错误科学结论。具体源码、补丁、调用记录和校验哈希见source_history/。','',
        '## 已恢复：FIFO精确上游版本','',
        '本地external/verilog-axis的HEAD与shallow记录均为48ff7a7e2ef782cf778d47910cf85835c64b1bce。该提交axis_fifo.v的Git blob为dfa465792f052486ac6f8d4c483318d4a338076d。',
        'GitHub固定提交文件下载与本地Git对象SHA256一致：aefddc67fc3552d919280424606fc6b048e61d7df9ee7ee0f8801c082c1cfc39。实验工作文件SHA256为b29a492b29dcb6b060a3d40d77206e490533433b23d2a954d3b84b08985db16e；仅CRLF/LF差异，规范化文本一致。20261014及20261015实验记录的source_sha256与该工作文件匹配。',
        '官方来源：[固定提交axis_fifo.v](https://raw.githubusercontent.com/alexforencich/verilog-axis/48ff7a7e2ef782cf778d47910cf85835c64b1bce/rtl/axis_fifo.v)。WSL首次下载失败保留，Windows成功下载和哈希验证另存official_download/windows_result.json。','',
        '## 部分补齐：项目Git版本','',
        '当前工作区.git为空。只读检查相邻D:/AssertionForge-main，找到2026-07-01提交49da13029efe7d0080866457d75a3a5bf68811c9，但研究适配器、原生闭环及stat案例都不在其中，故不能把它填为实验HEAD。检查27个较小归档目录成员，未发现可用项目Git历史；发现的stat成员主要是既有实验/训练结果。3.7GB Python运行环境归档未搜索内容，此限制记录在inventory。','',
        '已建立content_versions.json：为三个关键运行关联模型请求/响应/SVA、实际编译TB/命令/工具版本、实际RTL回放和恢复Python版本，生成内容寻址ID。它可作为历史产物版本标识，但不是Git提交。','',
        '仍需的解决方案：若有当时项目完整备份或远端分支，恢复其.git并核验每个实验输入哈希；若无，保留root_git_commit=null，使用此次内容版本清单及已有封存快照。后续另建版本控制和运行前快照，只能记录未来，不得倒填过去。','',
        '## 部分补齐：被取消模型调用成本','',
        '原始请求、attempt及cancellation已归档。服务task129日志补出截断前prompt=18354、调度后16383、最后进度7168、释放slot n_tokens=8196、HTTP500及服务耗时4m18s。',
        '服务耗时258秒与提交/结束墙钟差254秒不同；旧388.651028秒是记录区间上界。三者分字段保留，不能混为精确客户端调用耗时。slot计数不是最终prompt_eval_count，不能把8196直接当实际输入token。没有最终usage回执，输入/输出实际消耗继续null，未收到完整响应也不等于生成token必为0。','',
        '仍需的解决方案：寻找原模型服务最终task usage或按请求统计回执；如果没有则无法精确恢复。统计中保留1次取消调用、实测服务耗时及token不可用项。未来在发请求前创建日志，逐块flush响应并在finally/SIGINT写取消终态；服务进度计数与正式usage分开保存。重跑只能产生新成本，不能补成旧成本。','',
        '## 无法补成真实来源：stat','',
        '官方axis_stat_counter.v固定提交与本地依赖换行规范化一致，但本地case505是不同接口的8行模型。元数据原称actual_rtl_logic_change/final_verified_admitted，当前没有原始推导证明。已写stat_origin/effective_provenance.json覆盖来源解释：local_synthetic_pipeline_with_unverified_upstream_mapping，historical_admission=false；原元数据留存。','',
        '可选解决方案：',
        '1. 保留为人工工程案例，由明确的规格定义采样延迟、长度捕获和重叠行为；不能据此声称上游历史修复。',
        '2. 找回生成脚本/原始补丁、输入源码blob、约简假设和事件映射，验证后再讨论历史接入；仅提供新的规格文字不能补出历史来源。',
        '3. 另选真实上游前后提交，在原AXI接口复现；这属于新的案例实验，不能追认旧案例。','',
        '## 验收与用法','',
        '两轮旧交付清单合计91项均未改变。恢复产物另存本目录，现有模型拒绝结果、unknown和未执行实验状态保持。',
        '复算历史版本：`wsl -- python3 scripts/recover_research_records.py replay_source_history`。',
        '核验补充档案：`wsl -- python3 scripts/recover_research_records.py verify`。',
        '机器可读入口：recovery_status.json；完整性清单：manifest.json；历史版本：content_versions.json。','']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    shutil.copy2(Path(__file__).resolve(),OUT/'recovery_script_snapshot.py')
    paths=[p for p in OUT.rglob('*') if p.is_file() and p.name not in ('manifest.json','verification.json') and '__pycache__' not in p.parts]
    dump(OUT/'manifest.json',{str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in sorted(paths)})
    print(json.dumps(dict(fully_recovered=2,partially_recovered=2,unresolved_mismatch=1,manifest_files=len(paths))))


def verify():
    checks=[]
    for relative,expected in read(OUT/'manifest.json').items():
        path=ROOT/relative;actual=sha(path.read_bytes()) if path.exists() else None
        checks.append(dict(path=relative,passed=expected==actual))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks)
    dump(OUT/'verification.json',result)
    assert result['passed'],'recovery_artifact_changed'
    print(json.dumps(dict(passed=True,checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['source_history','git_provenance','replay_source_history','related_repository','cancelled_usage','archive_inventory','stat_origin','fetch_pinned_sources','content_versions','report','verify'])
    args=parser.parse_args();globals()[args.action]()
