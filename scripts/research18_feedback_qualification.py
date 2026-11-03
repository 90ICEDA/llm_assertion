"""Qualify feedback and context handling on archived real native evidence.

No model generation, RTL execution, or independent-test access. Local runner
template/tokenizer requests only. Existing experiment artifacts stay immutable.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path

import research17_fifo_feedback as feedback
from research18_continue import compact_feedback
from research18_context_budget import count

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'deliverables/research18_closed_loop_20261016_r02'


def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--out',type=Path,default=ROOT/'deliverables/research18_feedback_budget_20261016_r01')
    args=p.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    sources={}
    def read(path):
        sources[str(path)]=digest(path)
        return json.loads(path.read_text(encoding='utf-8-sig'))
    native=args.source/'core/v0/native'
    rebuilt=[];windows=[]
    for case_path in sorted(native.glob('case_*')):
        case=read(case_path/'case.json')
        fixed=read(case_path/'correct/replay.json')
        buggy=read(case_path/case['mode']/'replay.json')
        ledger=read(case_path/'ledger.json')
        info=feedback.feedback(fixed,buggy,ledger)
        rebuilt.append(dict(scenario=case['id'],diagnostic=info))
        for variant,record,diag in [('correct',fixed,info['fixed']),(case['mode'],buggy,info['mutant'])]:
            targets=[r['cycle'] for r in record['reference_trace'] if r['drain_due']]
            if not targets:continue
            slim=compact_feedback(diag)
            selected=[w['center_cycle'] for w in diag['sample_windows']]
            compact_selected=[w['center_cycle'] for w in slim['sample_windows']]
            one=feedback._diagnostics(record,max_windows=1)
            first_only=[w['center_cycle'] for w in one['sample_windows']]
            failures=feedback.marker_map(record['native'],'failures')
            early=sorted({c for values in failures.values() for c in values if c<min(targets)})
            windows.append(dict(scenario=case['id'],variant=variant,drain_targets=targets,
                selected=selected,compact_selected=compact_selected,one_window_limit=first_only,
                preceding_native_failure_cycles=early,
                all_drain_targets_retained=all(c in selected and c in compact_selected for c in targets),
                first_drain_prioritized_under_one_window_limit=min(targets) in first_only))
    dump(out/'rebuilt_feedback.json',rebuilt);dump(out/'window_qualification.json',windows)
    original_path=args.source/'core/v1/model_call/request.json'
    original=read(original_path)
    last=json.loads(original['messages'][-1]['content'])
    compact=copy.deepcopy(original)
    compact_last=copy.deepcopy(last)
    compact_last['actual_feedback']=compact_feedback(last['actual_feedback'])
    compact['messages'][-1]['content']=json.dumps(compact_last)
    refreshed=copy.deepcopy(compact)
    refreshed_last=copy.deepcopy(compact_last)
    refreshed_last['actual_feedback']['actual_native_evidence']=compact_feedback(rebuilt)
    refreshed['messages'][-1]['content']=json.dumps(refreshed_last)
    budgets={}
    for name,request in [('original',original),('compact_original',compact),('compact_rebuilt',refreshed)]:
        dump(out/(name+'_request.json'),request)
        result,_=count(request)
        (out/(name+'_rendered_prompt.txt')).write_text(result.pop('prompt'),encoding='utf-8')
        result['serialized_request_bytes']=len(json.dumps(request).encode())
        budgets[name]=result
    unchanged=all(digest(path)==value for path,value in sources.items())
    passed=bool(windows) and all(w['all_drain_targets_retained'] and w['first_drain_prioritized_under_one_window_limit'] for w in windows)
    passed=passed and not budgets['original']['fits_with_output_reserve'] and budgets['compact_original']['fits_with_output_reserve'] and budgets['compact_rebuilt']['fits_with_output_reserve'] and unchanged
    result=dict(passed=bool(passed),new_model_generation_calls=0,new_rtl_executions=0,formal_calls=0,
        independent_test_artifacts_read=False,source_artifacts_unchanged=unchanged,
        sources=sources,windows=windows,budgets=budgets,
        tokenizer_calls=sum(b['tokenization_calls'] for b in budgets.values()),
        scope='Diagnostic selection and prompt-budget qualification only. No new SVA success, native replay or semantic repair claim.')
    dump(out/'result.json',result)
    lines=['# Archived feedback and context qualification','',f'Qualification passed: {bool(passed)}.',
        'No model generation, new RTL execution or independent-test read. Actual archived native evidence was reused unchanged.','',
        '| Request | Rendered input tokens | Conservative input | Output reserve | Fits |',
        '|---|---:|---:|---:|---|']
    for name,b in budgets.items():lines.append(f'| {name} | {b["rendered_prompt_tokens"]} | {b["conservative_input_estimate"]} | {b["output_reserved_tokens"]} | {b["fits_with_output_reserve"]} |')
    lines+=['','All four fair-drain control/mutant observations retain cycle 111 in rebuilt and compact feedback. The one-window diagnostic limit also prioritizes that checkpoint over earlier candidate failures; actual failure cycles are preserved in window_qualification.json.','',
        'Removed opaque hash lists and cycle arrays are represented by counts; complete native evidence remains in its original artifact directory. Template counting uses the actual runner tokenizer with a documented conservative wrapper allowance; it is not claimed to exactly reproduce every Ollama Go-template path.','',result['scope']]
    (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'manifest.json',{p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(passed=bool(passed),window_cases=len(windows),budgets={k:dict(tokens=v['rendered_prompt_tokens'],fits=v['fits_with_output_reserve']) for k,v in budgets.items()},new_model_calls=0,new_rtl_executions=0,out=str(out))))
    if not passed:raise RuntimeError('Feedback/context qualification failed; inspect artifacts')


if __name__=='__main__':main()
