"""Standalone matplotlib figures from registered completed-prefix cost slices."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research195_cost_sections_20261103_r01'
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.research195_plotcache'))
sys.path.insert(0,str(ROOT/'.research195_plotdeps'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def build():
    data=json.loads((OUT/'analysis.json').read_text(encoding='utf-8'))
    rows=[r for r in data['summary'] if r['budget'].isdigit()]
    fig,axes=plt.subplots(2,3,figsize=(15,8),constrained_layout=True)
    colors=['#2366a8','#d07516','#13836f','#9346a1'];markers=['o','s','^','x']
    for column,group in enumerate(('R','S','A')):
        selected=[r for r in rows if r['group']==group]
        for i,arm in enumerate(sorted({r['arm'] for r in selected})):
            points=sorted((r for r in selected if r['arm']==arm),key=lambda r:int(r['budget']))
            xx=[int(r['budget']) for r in points]
            for row,key in enumerate(('parent_macro_transaction_rate','parent_macro_legal_fp_contexts')):
                yy=[r[key] for r in points]
                axes[row,column].scatter(xx,yy,label=arm,color=colors[i],marker=markers[i],s=48,linewidths=1.3,alpha=.85)
        for row in range(2):
            ax=axes[row,column];ax.set_xscale('symlog',base=2,linthresh=16384)
            ax.set_xticks([0,16384,32768,65536,131072,262144,524288],['0','16k','32k','64k','128k','256k','512k'])
            ax.grid(alpha=.22);ax.set_xlabel('Actual prompt + completion token ceiling')
            ax.set_ylabel('Transaction-obligation target detection' if row==0 else 'Parent-macro legal alarm contexts')
            ax.set_title(group+' comparison');ax.legend(ncol=4,fontsize=8,loc='best')
            if row==0:ax.set_ylim(-.02,1.02)
    fig.suptitle('All paired parents, including early stops (retrospective R194 test reuse)',fontsize=15)
    fig.savefig(OUT/'token_cost_sections.png',dpi=170)
    fig.savefig(OUT/'token_cost_sections.svg')
    plt.close(fig)
    metadata=dict(matplotlib_version=matplotlib.__version__,analysis_sha256=hashlib.sha256((OUT/'analysis.json').read_bytes()).hexdigest(),
        plot_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        note='Points are measured completed-prefix sections; no interpolation is implied. All paired parents enter these means, including early stops; these are NOT means restricted to common observed-cost support. Detection denominator is transaction-obligation targets, not unique transactions. Unknown fault intersections and common cost support are listed in analysis.json. This is not equal wall-clock spending or a new unseen test set.')
    (OUT/'plot_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n',encoding='utf-8')
    (OUT/'curves.html').write_text('<!doctype html><meta charset="utf-8"><title>模型成本截面</title><style>body{font:16px/1.6 system-ui;max-width:1500px;margin:30px auto;padding:20px}img{width:100%}</style><h1>已完成调用的 tokens 成本截面</h1><p>点表示已实测的预算截面，不在点间插值。均值覆盖全部可配对父案例，包含提前终止并保留原状态的轨迹，不是共同成本支持子集的均值。检出率分母为事务×义务目标，并非独立事务。各截面共同可判定故障、父案例数及共同成本支持范围见原始表。此图不代表等墙钟花费，也不是新的未见测试集。</p><img src="token_cost_sections.png"><p><a href="token_cost_sections.svg">SVG</a> · <a href="report.html">比较表与限制</a> · <a href="analysis.json">逐单元数据</a> · <a href="plot_metadata.json">图表来源</a></p>',encoding='utf-8')
    print(OUT/'curves.html')

if __name__=='__main__':build()
