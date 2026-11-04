"""Reviewable readiness report; never presents preparation as experiment success."""
import argparse
from collections import Counter
from html import escape
from pathlib import Path
from research194_refinement_runner import read,dump,file_hash

def run(prepared,out):
    from research198_prepare import verify
    p=verify(prepared);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    q=Path(p['qualification']);qualification=read(q/'outcome.json');review=read(Path(prepared)/'review.json')
    data=dict(status='awaiting_new_model_authorization',model_calls=0,prepared_requests=36,maximum_model_calls=p['maximum_model_calls'],
        first_stages=review['first_stages'],native_qualification=qualification,
        completed=['Separate partial local repair from missing-component composition','Corrected typed operations integrated into automatic R3 with fallback enabled','Same five-call ceiling for all arms','Fixed-evidence reuse and historical search costs separated','Fresh fault instances and independent input seeds preregistered'],
        pending=['Fresh real-model automatic trajectories','Honest full fallback path coverage audit','Frozen independent acceptance','Matched cost sections and final mechanism conclusions'],
        limitations=p['limits'],protocol_sha256=file_hash(Path(prepared)/'protocol.json'),
        qualification_interpretation='Handwritten native qualification and archived model-response replay are implementation checks, not fresh model experiments.')
    dump(out/'readiness.json',data)
    rows=''.join('<tr><td>'+escape(policy)+'</td><td>'+str(v['free'])+'</td><td>'+str(v['local'])+'</td><td>'+str(v['compose'])+'</td></tr>' for policy,v in data['first_stages'].items())
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>REGuard research198 准备与边界</title><style>body{max-width:1050px;margin:40px auto;font:16px/1.7 sans-serif;color:#172335}table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #ccd3dd}code{background:#eef2f7}li{margin:8px 0}</style><h1>自动局部优先与完整回退：准备完成，真实模型实验待执行</h1>
<p>旧控制器发现任意未声明义务便进入组合；新策略先尝试已有组件的证据支持局部修改。只在原生确认失败后进入后续阶段，unknown、接口错误或不变提案不能提供回退资格。旧封存结果不变。</p>
<table><tr><th>策略</th><th>自由修改首轮</th><th>局部首轮</th><th>组合首轮</th></tr>'''+rows+'''</table>
<p>3 个父案例 × 2 个种子 × S0/S3 已获得证据 × 3 个控制策略，共 36 条轨迹，每条最多 5 次调用，共最多 180 次。所有组固定初始候选、开发输入、模型与预算。这里是固定搜索结果后的组合比较，不冒充在线自适应搜索消融。</p>
<p>已完成本地原生手写回退资格验证；这不等于真实模型三阶段实测完成。模型不会被要求故意给出错误修改来制造分支覆盖。</p>
<p>新验收在全部版本冻结后生成输入并验证预留故障；未曝光或未知保留，禁止为了正面结果替换故障。独立验收信息不进入模型请求。</p>
<ul><li><a href="../research198_refinement_prepare_20261104_r01/protocol.json">封存协议</a></li><li><a href="../research198_refinement_prepare_20261104_r01/review.json">36 份首轮请求清单</a></li><li><a href="../research198_qualification_20261104_r01/routing_diagnosis.json">12 条旧/新路由诊断</a></li><li><a href="../research198_qualification_20261104_r01/fallback.json">手写原生回退验证</a></li><li><a href="../reguard_mechanisms_20261104_r07/report.html">上一轮真实结果</a></li></ul>
<p>覆盖边界：有限 1..32 周期采样窗口，三个不同在途 ID、响应年龄 1..8；未覆盖同 ID 复用或完整 Ibex 异常流水线。本轮不扩张这些研究范围。</p></html>'''
    (out/'report.html').write_text(html,encoding='utf-8')
    print(dict(status=data['status'],requests=36,maximum_calls=180,model_calls=0),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.out)
