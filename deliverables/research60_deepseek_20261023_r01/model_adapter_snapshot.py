"""One cached local DeepSeek trial; model switch is explicitly exploratory."""
import argparse
from pathlib import Path
import shutil
from unittest.mock import patch
import research60_compact_local as compact
g=compact.g;base=compact.base
ORIGINAL=compact.request


def request(prep,feedback,seed):
    req=ORIGINAL(prep,feedback,seed)
    req['model']='deepseek-coder:6.7b-instruct'
    req['options']['num_ctx']=8192
    return req


def run(out):
    try:
        with patch.object(compact,'request',request):compact.run(out)
    finally:
        if out.exists():
            shutil.copy2(__file__,out/'model_adapter_snapshot.py')
            protocol=g.read(out/'protocol.json');protocol['changes']='One real cached local DeepSeek6.7B synthesis with exact source-bound OP excerpts, no failed OP template. Same original native DUT and phase/full acceptance; model/context change is exploratory.'
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
