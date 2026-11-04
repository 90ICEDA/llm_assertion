"""Review sealed concrete requests; never describe readiness as model success."""
import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit,unquote
from research194_refinement_runner import ROOT,read,dump,file_hash
from research199_prepare import verify
from research199_independent import FAULTS

def run(prepared,out):
    prepared=Path(prepared);p=verify(prepared);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    review=read(prepared/'review.json');qual=read(Path(p['qualification'])/'outcome.json');checks=0
    for e in p['entries']:
        request=read(e['request']);text=str(request)
        for secret in [f['id'] for f in FAULTS.values()]+['19981','19993','r199_reserved','fully_transaction_protected_exposed_obligations']:
            if secret in text:raise ValueError('independent_metadata_in_request:'+e['id'])
            checks+=1
        if request['model']!=p['model'] or request['max_tokens']!=2048 or request['temperature']!=.2 or request['seed']!=e['seed']:raise ValueError('request_parameters')
        checks+=4
    data=dict(status='awaiting_new_exact_scope_authorization',model_calls=0,prepared_requests=review['first_requests'],maximum_model_calls=p['maximum_model_calls'],
        first_stages=review['first_stages'],first_request_bytes=review['request_bytes'],protocol_sha256=file_hash(prepared/'protocol.json'),
        local_checks=checks,native_qualification=qual,
        completed=['P0 obligation diagnosis from archived evidence','Factorial routing and contract switches','Common retained-candidate composition permission fix','12 physically executed development query pairs','Native accepted archived edit followed by actual changed-candidate acquisition','Prefix cost and evidence-linkage analysis registered','Independent new fault instances and input seeds registered but not executed'],
        pending=['48 fresh-model trajectories','Actual B0-B3 and online A0-A3 results','Natural fallback coverage','Frozen independent acceptance and costs','Final delivery audit'],
        boundaries=['Archived edit qualification is not a fresh model success.','Do not require a positive evidence-improvement chain to finish a registered experiment.','P0 examined old held-out results; exclude those old instances from new unseen claims.'])
    dump(out/'readiness.json',data)
    rows=''.join('<tr><td>'+a+'</td><td>'+str(v['local'])+'</td><td>'+str(v['compose'])+'</td><td>'+str(v['free'])+'</td></tr>' for a,v in review['first_stages'].items())
    html='''<!doctype html><meta charset="utf-8"><title>R199 准备与授权审阅</title><style>body{font:16px/1.65 sans-serif;max-width:1100px;margin:35px auto}table{border-collapse:collapse}td,th{border:1px solid #bbc;padding:8px}</style><h1>R199：义务诊断已完成，因果隔离与在线实验待真实模型执行</h1>
<p>本页是准备记录，不是算法结果。48 条轨迹，每条最多三次，总计最多 144 次调用；相同模型、2048 输出 tokens 上限、300 秒超时、并行度 2、不重试。</p>
<p>B0/B1/B2/B3：旧通用／局部优先通用／旧专用／局部优先专用。使用相同 S3 开发证据、定位、组合权限和原生历史保护门。A0/A1/A2/A3：S0 基础反馈／S3 基础反馈／S0 新局部细化／S3 新局部细化，接受修改后重新按当前候选查询。</p>
<table><tr><th>组</th><th>首轮局部</th><th>首轮组合</th><th>首轮自由</th></tr>'''+rows+'''</table>
<p>已物理执行 12 组首轮开发查询，共 24 次编译执行。在线原生资格验证使用一份已归档模型响应，接受窗口修改后，实际执行了基于新候选选择的另一条查询。这不是新的模型结果，也不是完整回退成功。</p>
<p>主要成本分析预登记为 131072 tokens 的完整检查点截面，同时保留全部预登记查询／服务耗时／轮次截面。固定证据组的历史获取成本单列；在线组首轮共享物理执行并分别计入逻辑获取成本。不声称严格等实际成本随机重跑。</p>
<p>三个新故障实例及新验收种子已登记，尚未构造或执行独立输入。开发与验收不共享模型可见信息；R197/R198 的旧预留故障作为诊断材料，不再作新未见故障证据。所有注册的无曝光、unknown 和失败均保留。</p>
<ul><li><a href="../research199_diagnosis_20261104_r01/report.html">P0 义务级诊断</a></li><li><a href="../research199_refinement_prepare_20261104_r01/protocol.json">封存实验协议与分析规则</a></li><li><a href="../research199_refinement_prepare_20261104_r01/review.json">48 份实际首轮请求清单</a></li><li><a href="../research199_qualification_20261104_r01/outcome.json">在线原生资格验证</a></li><li><a href="../reguard_mechanisms_20261104_r09/completion_review.html">此前真实模型结果</a></li><li><a href="readiness.json">本页数据</a></li></ul>
<p>模型阶段需要新授权：先前授权明确绑定 research198 等旧封包，本次改变了契约隔离和在线请求生成策略。独立验收信息不发送。</p>'''
    (out/'report.html').write_text(html,encoding='utf-8')
    links=[]
    class Links(HTMLParser):
        def handle_starttag(self,tag,attrs):
            href=dict(attrs).get('href') if tag=='a' else None
            if not href:return
            uri=urlsplit(href)
            if not uri.scheme and uri.path:links.append(dict(href=href,exists=(out/unquote(uri.path)).resolve().is_file()))
    Links().feed(html)
    if not all(r['exists'] for r in links):raise ValueError('broken_review_link')
    dump(out/'preparation_audit.json',dict(status='passed',request_checks=checks,requests_reconstructed=len(p['entries']),links=links,model_calls=0,
        protocol_sha256=file_hash(prepared/'protocol.json'),report_sha256=file_hash(out/'report.html'),reviewer_sha256=file_hash(__file__)))
    print({k:v for k,v in data.items() if k not in ('native_qualification','completed','pending','boundaries','first_stages')},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',required=True,type=Path);p.add_argument('--out',required=True,type=Path);a=p.parse_args();run(a.prepared,a.out)
