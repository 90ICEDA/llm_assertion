"""Read-only diagnosis of rejected responses; never assembles or accepts a candidate."""
import argparse
import json
from pathlib import Path
import re
import research40_interface_continuation as renderer


def diagnose(run, out):
    out.mkdir(parents=True, exist_ok=False)
    read = lambda p: json.loads(p.read_text(encoding='utf-8'))
    rows = []
    initial = read(run/'arms/s4201/A/frozen_candidate.json')
    for folder in sorted(run.glob('s*/*/model_call')):
        pair = read(folder.parent/'pair_result.json')
        edit_path = folder/'model_edit.json'
        edit = read(edit_path) if edit_path.exists() else None
        row = dict(pair=folder.parent.relative_to(run).as_posix(),
                   status=pair['call']['status'], candidate_status=pair['call']['candidate_status'],
                   operation=edit.get('operation') if edit else None,
                   reason_characters=len(edit['reason']) if edit else None)
        if edit and edit['operation'] == 'replace_one':
            # Rendering only: keep the entire original AST and reason untouched.
            item = edit['assertions'][0]
            arrow = '|=>' if item['timing'] == 'next_sample' else '|->'
            prop = f"{renderer.expression(item['antecedent'])} {arrow} {renderer.expression(item['consequent'])}"
            old = next(a['property'] for a in initial['assertions'] if a['id'] == edit['assertion_id'])
            tokens = lambda s: re.sub(r'[\s()]', '', s)
            row.update(rendered_for_diagnosis_only=prop, original_property=old,
                       same_tokens_ignoring_parentheses=tokens(prop) == tokens(old),
                       equivalence_scope='Text observation for this simple conjunction/equality only; not a general semantic equivalence check or native proposal execution.')
        rows.append(row)
    result = dict(rows=rows, model_calls=0, native_calls=0,
                  acceptance_changes=0, original_trial_unchanged=True,
                  scope='Post-run diagnosis only. No shortened reasons, candidate substitution, or retroactive acceptance.')
    (out/'diagnosis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    assert len(rows) == 6
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    diagnose(a.run, a.out)
