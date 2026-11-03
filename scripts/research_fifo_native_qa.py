"""Engineering-only qualification of the native LLM harness; no model calls."""
from pathlib import Path
import json
from research_native_closed_loop import evaluate, OUT

if __name__ == '__main__':
    candidate={'assertions':[{'id':'a0','property':'(mvalid && mready) |-> (ref_count > 0 && mdata == ref_expected)',
        'trigger':'mvalid && mready','obligations':['order_payload','no_unsolicited_output']}]}
    result=evaluate(candidate,OUT/'engineering_qa',2026101441,2,2)
    print(json.dumps(dict(status=result['status'],false_positives=result['false_positives'],
        detection_count=len(result['detections']),miss_count=len(result['misses']),
        verdicts={k:r['property_status'] for k,r in result['native_results'].items()},
        no_llm=True),indent=2))
