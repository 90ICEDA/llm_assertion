"""Check that reused independent inputs stop BEFORE any replay or file output."""
import argparse
from pathlib import Path
import research17_loop as loop
import research41_fresh_campaign as campaign
from research35_campaign import holdout


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    protected_before=campaign.protected_manifest()
    split=loop.read(campaign.PROTECTED/'independent/split.json')
    candidate=loop.read(campaign.PROTECTED/'core/frozen_candidate.json')
    rejected=False
    try:
        holdout(out/'must_not_execute',candidate,[],
            extra_exposed_hashes=campaign.split_hashes(split),fixed_split=split)
    except AssertionError:
        rejected=True
    assert rejected and not (out/'must_not_execute').exists()
    assert protected_before==campaign.protected_manifest()
    loop.dump(out/'verification.json',dict(passed=True,overlap_rejected_before_native=True,
        no_independent_output_created=True,research40_preserved=True,
        excluded_distinct_inputs=len(campaign.split_hashes(split)),
        model_calls=0,native_calls=0,formal_calls=0,
        scope='Intentional same-input exclusion check only. research40 samples used for hash exclusion, not model feedback or assertion editing. Not a fresh test batch.'))
    print('INDEPENDENCE_EXCLUSION passed; model/native calls=0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
