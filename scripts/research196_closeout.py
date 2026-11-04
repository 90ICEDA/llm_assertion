"""Append execution-provenance notes without changing experiment conclusions."""
import argparse
from html import escape
from pathlib import Path
from research194_refinement_runner import ROOT, read, dump, file_hash


def closeout(report):
    report = Path(report)
    repair = ROOT/'deliverables/research196_finish_compat_20261104_r01'
    first = ROOT/'deliverables/research196_finish_20261104_r01'
    if read(repair/'status.json')['status'] != 'local_phases_completed':
        raise ValueError('postprocessing_incomplete')
    if not (report/'search_cost_curves.png').is_file():
        raise ValueError('plot_not_rendered')
    target = report/'report.html'
    if (report/'closeout.json').exists():
        raise ValueError('closeout_already_recorded')
    data = dict(status='local_campaign_and_acceptance_executed',
                source_sha256=file_hash(__file__),
                first_postprocessing_attempt=read(first/'status.json'),
                compatibility_repair=read(repair/'protocol.json'),
                resumed_postprocessing=read(repair/'status.json'),
                plot_rendered=True,
                additional_model_calls=0,
                note='Completion records execution, not scope acceptance or a demonstrated positive mechanism effect.')
    dump(report/'closeout.json', data)
    text = target.read_text(encoding='utf-8')
    note = ('<h2>验收执行修补与完成记录</h2><p>首次独立验收在输入构造前因私有案例模块缺少 Ibex 动态注册而退出。'
            '兼容层仅补入原注册元数据，封存源码、候选、输入生成器及预留故障定义均未修改。原失败记录保留；修补后完整执行本地验收，无额外模型调用。</p>'
            '<p><a href="closeout.json">执行与修补记录</a> · '
            '<a href="../research196_finish_20261104_r01/status.json">首次失败记录</a> · '
            '<a href="../research196_finish_compat_20261104_r01/protocol.json">验收前封存的兼容层说明</a></p>')
    target.write_text(text+'\n'+note, encoding='utf-8')
    dump(report/'plot_completed.json', dict(status='rendered', sha256=file_hash(report/'search_cost_curves.png')))
    print(dict(status='closeout_recorded', additional_model_calls=0), flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,required=True)
    closeout(parser.parse_args().report)
