"""Raw native, information isolation and authorization preflight, no model calls."""
import argparse
import copy
import json
from pathlib import Path
import research94_prospective_gate_pilot as p
import research88_cross_parent_audit as audit

x=p.x
read,dump,sha,ROOT=p.read,p.dump,p.sha,p.ROOT


def run(prep,out):
    x.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[];rows=0
    def check(name,condition):
        assert condition,name
        checks.append(name)
    baseline=read(prep/'baseline_full.json');initial=read(prep/'initial.json')
    n,ev,records=audit.inspect_version(prep/'baseline_native',initial,baseline);rows+=n
    check('initial not counted as accepted',p.decisions(ev)==dict(O=False,H=False,R=False))
    public=p.feedback(ev,records,False)
    check('public feedback bound',public==read(prep/'initial_public_feedback.json'))
    changed=copy.deepcopy(records)
    # Ordinary feedback must be invariant to hidden-history outcomes or labels.
    changed['history']=dict(counts={'sentinel_private_history':123},ledger=[],required_untriggered=['PRIVATE_SENTINEL'])
    check('history mutation cannot alter O feedback',p.feedback(ev,changed,False)==public)
    req=p.payload(initial,public,0)
    check('first request exact',req==read(prep/'request.preview.json'))
    for arm in p.ARMS:check('first request identical '+arm,req==read(prep/'arms'/arm/'request.preview.json'))
    check('no hidden history in first feedback','history' not in public['visible_counts'])
    check('no rejected/success archive proposal in first prompt',not any(s in json.dumps(req) for s in ('prior_local_attempts','research92_real','research93','research61_ast','636')))
    for name,expected in [('positive',dict(O=True,H=True,R=True)),('known_overbroad',dict(O=True,H=False,R=False))]:
        root=prep/'controls'/name;candidate=read(root/'candidate.json')
        n,ce,cr=audit.inspect_version(root/'native',candidate,baseline);rows+=n
        check(name+' fixed three-rule decisions',p.decisions(ce)==expected)
        h=p.feedback(ce,cr,True);r=p.feedback(ce,cr,True)
        check(name+' H/R same evidence and prompt',p.payload(candidate,h,1)==p.payload(candidate,r,1))
        check(name+' public only selected cohorts',set(p.feedback(ce,cr,False)['visible_counts'])=={'alignment','search'})
        before=x.old.acceptance.inspect(baseline['ledger'])['rows']
        after=x.old.acceptance.inspect(x.paired.aggregate(cr['history'],cr['search'])['ledger'])['rows']
        check(name+' same full historical identities',set(before)==set(after) and all(
            all(before[k].get(f)==after[k].get(f) for f in ('obligation','stimulus_sha256','oracle')) for k in before))
    dummy=dict(purpose='research94_prospective_gate_pilot',authorized_calls=4,
        endpoint=p.prior.transport.DEFAULT_URL,model=p.prior.transport.DEFAULT_MODEL,
        prepared_sha256=sha(prep/'sealed.json'),run_output='deliverables/research94_AUTH_TEST_NOT_RUN')
    runpath=ROOT/dummy['run_output'];p.grant_check(dummy,prep,runpath)
    for field,value in [('authorized_calls',0),('purpose','research92_remote_recovery'),('endpoint','https://invalid.example/'),('prepared_sha256','0'*64)]:
        bad=copy.deepcopy(dummy);bad[field]=value
        try:p.grant_check(bad,prep,runpath)
        except (KeyError,AssertionError):checks.append('invalid grant '+field+' rejected')
        else:raise AssertionError(field)
    check('no test invocation directory created',not runpath.exists())
    check('research93 unchanged',p.protected_snapshot()==read(prep/'protected93.json'))
    model=read(prep/'model_config.json');protocol=read(prep/'protocol.json')
    check('four physical calls and two logical per trajectory',model['max_model_calls']==4 and protocol['maximum_per_trajectory']==2)
    check('no automatic expansion','Passing does NOT authorize expansion.' in protocol['expansion_gate'])
    check('first request fits conservative total reservation',sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']<model['max_tokens']/4)
    cost=read(prep/'preparation_cost.json')['total']
    check('fresh native qualification costs18/18',cost['native_compile_calls']==18 and cost['native_execute_calls']==18 and cost['model_calls']==0)
    result=dict(passed=True,checks=checks,native_rows_recomputed=rows,model_calls=0,
        new_native_calls=0,prepared_sha256=sha(prep/'sealed.json'),script_sha256=sha(Path(__file__)))
    dump(out/'preflight.json',result)
    (out/'SUMMARY.md').write_text('\n'.join([
        '# research94–96：前瞻性三规则先导准备','',
        f'本地资格检查完成：18次原生编译与18次实验执行；逐行复核{rows}条记录，{len(checks)}项预检通过。真实模型先导尚未执行。','',
        'O普通检查、H同历史绝对检查、R防退化比较。一个新真实提案共享用于三规则配对决定；被拒绝组各自最多再调用一次，最多4个物理调用、每条轨迹最多2次。初始请求逐字一致；H/R收到相同历史事实，O只收到公共证据。后续独立响应不可拼接。','',
        '原始Ibex#166已知任务；本轮候选由未来调用生成，不把归档提案或research93成功版本当新候选。BRANCH沿用原始模型组件，OP全部由模型输出。原生正对照三规则都接受；过宽性质O接受而H/R拒绝。它们只是本地控制，不是先导模型成功。','',
        'H/R在当前严格完整覆盖要求下可能等价。两个已执行控制的决定相同；不削弱绝对检查来制造相对比较器优势，也不将候选生成差异归给门控。','',
        '扩种子条件：共享新提案普通接受、历史额外拒绝；对应历史组在同一预算内恢复，并通过冻结后的新独立验收。否则记录阴性或不具区分力结果并停止。即使通过，本脚本也不自动扩种子。','',
        '请求：deliverables/research94_prepare_20261025_r01/request.preview.json。当前尚无本实验远程授权；research92剩余一次仅限原恢复协议，不能自动转用。','',
        '复核（无模型调用）：`wsl -- python3 scripts/research96_pilot_preflight.py --prepared deliverables/research94_prepare_20261025_r01 --out deliverables/research96_preflight_NEW`',
    ])+'\n',encoding='utf-8')
    print('PREFLIGHT96',len(checks),rows,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve())
