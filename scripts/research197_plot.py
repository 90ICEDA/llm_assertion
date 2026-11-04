"""Render actual completed-query cost curves from saved R197 analysis."""
import argparse
import math
import os
from pathlib import Path
import statistics
import sys
from research194_refinement_runner import ROOT,read


def render(out):
    out=Path(out);data=read(out/'search_analysis.json')
    sys.path.insert(0,str(ROOT/'.research195_plotdeps'))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'.research195_plotcache'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    end=max(1,math.ceil(max(r['points'][-1]['seconds'] for r in data['runs'])))
    for strategy in ('S0','S1','S2','S3'):
        runs=[r for r in data['runs'] if r['strategy']==strategy]
        for ax,axis,grid in ((axes[0],'queries',range(4)),(axes[1],'seconds',range(0,end+1))):
            values=[statistics.mean(max((p for p in r['points'] if p[axis]<=budget),key=lambda p:p['queries'])['new_gap_count'] for r in runs) for budget in grid]
            ax.step(grid,values,where='post',label=strategy)
    axes[0].set_xlabel('Completed query budget');axes[1].set_xlabel('Actual query-service seconds')
    for ax in axes:ax.set_ylabel('Mean confirmed context gaps / case-seed');ax.legend();ax.grid(alpha=.25)
    fig.suptitle('R197: paired initial candidates, adaptive R1, early stops retained')
    fig.tight_layout();fig.savefig(out/'search_cost_curves.png',dpi=170);fig.savefig(out/'search_cost_curves.pdf');plt.close(fig)
    page=out/'report.html';html=page.read_text(encoding='utf-8')
    if 'search_cost_curves.png' not in html:
        page.write_text(html+'\n<h2>Actual search cost curves</h2><img style="max-width:100%" src="search_cost_curves.png" alt="Confirmed context gaps against query and actual service cost"><p>Completed queries only. Natural early stops retained. Context gaps are not independent bugs or final assertion improvements.</p>',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);render(p.parse_args().out)
