"""Prepare an exact external-service request for review; never submit it."""
from pathlib import Path
import hashlib
import json
import research17_loop as loop
import research20_stall_runtime as extension
from research27_model import RemoteModel

out=loop.ROOT/'deliverables/research27_remote_preview_20261020_r01'
out.mkdir(parents=True,exist_ok=False)
source=loop.ROOT/'deliverables/research27_closed_loop_20261020_r02'
before=loop.read(source/'core/before/result.json')
current=loop.read(source/'shared_initial.json')
feedback=dict(requested_obligations=['no_unsolicited_output','reset_cancellation'],
    counts=before['counts'],actual_native_evidence=before['feedback'],
    actual_rejection=loop.read(source/'core/v1/decision.json'),
    transport_or_interface_diagnostic=loop.read(source/'core/v1/model_call/result.json'))
config=dict(loop.CONFIG,fresh_unconstrained_property=True,direct_property=True,
    max_model_calls=2,call_timeout=180,max_tokens=240000)
model=RemoteModel(out,config)
extension.install()
try:
    request=model._payload(current,'no_unsolicited_output',feedback,'core_fresh_boundary_repair')
finally:
    extension.uninstall()
loop.dump(out/'request.preview.json',request)
loop.dump(out/'review.json',dict(endpoint=model.url,model=model.remote_model,max_calls=2,
    model_calls=0,credentials_read=False,external_transmission=False,
    source_development=str(source/'core/before'),
    request_sha256=hashlib.sha256((out/'request.preview.json').read_bytes()).hexdigest(),
    scope='Full axis_fifo RTL, testbench, confirmed obligations and two actual development observation cards; no independent results. Final execution regenerates path provenance from its own development replay.'))
print(json.dumps(loop.read(out/'review.json')))
