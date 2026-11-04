"""Offline checks for the curated GitHub release; no model/native execution."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True

def main():
    manifest = json.loads((ROOT/'docs/reguard_research/manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        p = ROOT/item['path']
        data = p.read_bytes()
        raw_ok = hashlib.sha256(data).hexdigest() == item['sha256']
        lf_ok = hashlib.sha256(data.replace(b'\r\n',b'\n')).hexdigest() == item.get('text_lf_sha256')
        if not (raw_ok or lf_ok):
            raise ValueError('Published file changed: '+item['path'])
    names = [
        'test_research194_active_semantics', 'test_research194_refinement',
        'test_research194_refinement_safe_localization',
        'test_research196_component_guard', 'test_research196_temporal',
        'test_research197.TemporalRegression.test_typed_bounds_and_no_unrestricted_field_edit',
        'test_research197.TemporalRegression.test_no_shared_source_module_patching',
        'test_research199.Factorial.test_contract_independent_of_routing_and_enforced',
        'test_research199.Factorial.test_reserved_replacement_only_selected_occurrence',
    ]
    suite = unittest.TestLoader().loadTestsFromNames(names)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print(f"Manifest: {len(manifest['files'])} files; tests: {result.testsRun}; offline only.")
    return 0 if result.wasSuccessful() else 1

if __name__ == '__main__':
    raise SystemExit(main())
