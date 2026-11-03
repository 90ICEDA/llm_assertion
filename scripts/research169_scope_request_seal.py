"""Finalize request wording to agree with validated host constants. Local only."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import research169_adapter_parameter_scope as s


def main(source,out):
    s.c.verify(source);s.c.verify(s.OLD)
    checks,check=s.check_list()
    request=s.read(source/'request.preview.json');body=json.loads(request['messages'][1]['content'])
    old_contract=body['output_contract']
    check('known old contract text',old_contract.count('Interface signals only;')==1)
    body['output_contract']=old_contract.replace('Interface signals only;',
        'Only interface signals and the six explicitly bound constant parameters in assertion_host_scope are allowed;')
    old_request=s.read(s.OLD/'request.preview.json');old_body=json.loads(old_request['messages'][1]['content'])
    delta={k for k in set(body)|set(old_body) if body.get(k)!=old_body.get(k)}
    check('exact scope-related delta only',delta=={'output_contract','assertion_host_scope'})
    check('runtime constants match stated RTL configuration',body['config']==body['assertion_host_scope']['parameters']==s.PARAMETERS)
    check('no parameter rewriting promise',body['assertion_host_scope']['expressions_preserved'].find('never replaces names')>=0)
    request['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    for k in ('model','seed','temperature','max_tokens'):
        check('unchanged sampler '+k,request[k]==old_request[k])
    check('unchanged system request',request['messages'][0]==old_request['messages'][0])
    check('no diagnostic response injected',body['current_assertions']==s.read(s.OLD/'initial.json'))
    check('old outcome remains failed',s.read(s.OLD_RUN/'outcome.json')['status']=='stop_interface_or_repeat')
    mismatch=s.q.ROOT/'deliverables/research169_scope_native_20261028_r01/mismatch/after/execute.log'
    check('negative control caught binding guard','PARAMETER_SCOPE_MISMATCH' in mismatch.read_text())
    shutil.copytree(source,out,ignore=shutil.ignore_patterns('seal.json'))
    s.dump(out/'request.preview.json',request)
    p=s.read(out/'protocol.json');p['request_contract']='Interface signals plus only six explicitly bound host constants; no other internals/hierarchy.'
    p['generator_change']='Host declarations and shared DUT binding; request changes only output_contract and assertion_host_scope. All predicates, initial seed, model, development information, data selection, O/H gates and budgets unchanged.'
    p['status']='fully_sealed_local_only_awaiting_new_scope_authorization'
    s.dump(out/'protocol.json',p)
    # Exercise final request, not just its predecessor; these remain labeled local fixtures.
    for i,names in enumerate([['replacement','complementary'],['replacement','replacement'],['complementary'],['overbroad'],['interface'],['transport']]):
        b=s.c.FixtureBackend(names);folder=out/'final_request_branch_checks'/str(i)
        s.c.execute(out,folder,b);r=s.read(folder/'outcome.json')
        check('final request no actual calls '+str(i),s.read(folder/'cost.json')['model_calls']==0)
        check('final request no model recovery claim '+str(i),not r['real_chain_success'] and r['conditional_recovery_denominator']==0)
        check('bounded conditional second call '+str(i),len(b.used)==(2 if i<2 else 1))
        if i<2:
            check('retain old H after rejection '+str(i),s.read(folder/'shared_decision.json')['active_hashes']['H']==s.c.digest(s.read(out/'initial.json')))
        check('independent entry only after local full recovery '+str(i),b.independent_called==(i==0))
    check('no independent inputs selected',not list(out.rglob('scenarios.json')))
    budget=s.c.Budget();budget.reserve_call('shared',request)
    check('final payload fits sealed reservation',len(budget.calls)==1)
    s.dump(out/'scope_contract_checks.json',checks)
    bindings=s.read(out/'code_bindings.json')
    for f in (Path(__file__),source/'seal.json'):
        bindings[s.q.old.rel(f)]=s.q.sha(f)
    s.dump(out/'code_bindings.json',bindings)
    old_summary=(out/'SUMMARY.md').read_text()
    summary=old_summary.replace('新请求只增加显式作用域说明','新请求增加显式作用域说明，并同步修改output_contract的允许标识符约定')
    summary=summary.replace(s.q.old.rel(source),s.q.old.rel(out))
    summary+=f'\n最终请求另通过{len(checks)}项约定一致性/分支检查。r01作为中间审查封存保留；用于后续新授权的请求是当前r02，不使用仍有“仅接口信号”旧约定的中间版本。\n'
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8')
    s.seal_files(out);s.c.verify(out);s.c.verify(s.OLD)
    print('FINAL_SCOPE_SEALED',len(checks),'additional checks; model0; recovery0/0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True,type=Path);ap.add_argument('--out',required=True,type=Path)
    a=ap.parse_args();main(a.source.resolve(),a.out.resolve())
