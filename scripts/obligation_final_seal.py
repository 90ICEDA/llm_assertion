"""Seal artifacts, preserving an append-only inherited Ollama service log.

The first strict integrity failure is retained. Only a cryptographically verified
original byte prefix is accepted for the one live server log; no blanket waiver.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor
import run_obligation_evidence as x


def main(run):
    out=x.ROOT/'deliverables'/run;delivery=out/'delivery'
    prior=x.read(out/'block_r02/prior_artifact_hashes.json')
    path='deliverables/obligation_evidence_20261013_r01/model_probe/server.log'
    failure=x.read(delivery/'final_history_integrity.json')
    assert failure['changed']==[path]
    data=(x.ROOT/path).read_bytes();h=hashlib.sha256();length=None
    for i,b in enumerate(data):
        h.update(bytes([b]))
        if h.copy().hexdigest()==prior[path]:length=i+1;break
    assert length is not None,'live log is not an exact append-only extension'
    dest=delivery/'preserved_live_log_prefix/server.log';dest.parent.mkdir(exist_ok=False)
    dest.write_bytes(data[:length]);assert x.sha(dest)==prior[path]
    paths=[p for p in prior if p!=path]
    with ThreadPoolExecutor(max_workers=16) as pool:hashes=list(pool.map(lambda p:x.sha(x.ROOT/p),paths))
    changed=[p for p,h in zip(paths,hashes) if prior[p]!=h];assert not changed
    preservation=dict(unchanged_files=len(paths),live_append_only_files=1,original_bytes_preserved=True,
        path=path,original_prefix_bytes=length,observed_current_bytes=len(data),original_sha256=prior[path],
        archived_original=x.rel(dest),cause='The already-running Ollama service retained its r01 stdout/stderr log descriptor; this study requests appended service events.',
        previous_strict_hash_failure=x.rel(delivery/'final_history_integrity.json'),no_historical_content_truncated_or_rewritten=True)
    x.dump(delivery/'history_preservation_final.json',preservation)
    # Keep the first final-report attempt and its failed sealing log intact.
    source=out/'FINAL_REPORT.md';target=out/'FINAL_REPORT_SEALED.md';assert not target.exists()
    text=source.read_text().replace('旧r01全部45,744个文件已哈希保留并逐字节复核；历史失败、未知、下载失败和重试均未覆盖。',
        '旧r01的45,743个文件逐字节未变；1个已有Ollama服务日志追加了本轮请求。其原有字节前缀匹配启动时SHA256，已另存delivery/preserved_live_log_prefix/server.log；没有截断或改写历史内容。首次严格哈希检查的失败记录保留。历史失败、未知、下载失败和重试均未覆盖。')
    text+='\n最终封存校验见delivery/history_preservation_final.json与final_artifact_manifest.json；FINAL_REPORT.md保留第一次严格校验发现活动日志变化时的报告。\n'
    target.write_text(text,encoding='utf-8')
    files=sorted(x.ROOT.joinpath('scripts').glob('obligation_*.py'))
    manifest=[]
    for p in files:
        dest=delivery/'final_implementation'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        manifest.append(dict(source=x.rel(p),snapshot=x.rel(dest),sha256=x.sha(p)))
    x.dump(delivery/'final_implementation_manifest.json',manifest)
    paths=[]
    excluded={out/'seal_recovery.stdout',out/'seal_recovery.stderr',delivery/'final_artifact_manifest.json'}
    for root,dirs,names in os.walk(out):
        paths.extend(Path(root)/n for n in names if Path(root)/n not in excluded)
    with ThreadPoolExecutor(max_workers=16) as pool:hashes=list(pool.map(x.sha,paths))
    x.dump(delivery/'final_artifact_manifest.json',dict(files={x.rel(p):h for p,h in zip(paths,hashes)},
        excluded=[x.rel(p) for p in excluded],reason='active recovery streams and self-referential manifest',
        final_report=x.rel(target)))
    print(json.dumps(dict(final_report=x.rel(target),artifact_files=len(paths),unchanged_history_files=len(prior)-1,append_only_log_original_prefix_preserved=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
