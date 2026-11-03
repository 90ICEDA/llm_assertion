from run_repair_contract import OUT,read
for label,k,v in [('e12/held_24','onehot','correct'),('e12/held_24','spill','correct'),('legacy_legal_variant','spill','correct'),('controlled_coverage/spill_valid_only','spill','buggy'),('controlled_coverage/stat_drop_valid','stat','buggy'),('controlled_coverage/stat_corrupt_length','stat','buggy')]:
 r=read(OUT/'runs'/label/k/v/'result.json')
 print(label,k,v,'violations',r.get('obligation_violation_cycles'))
 for c in r['candidates']:
  if c['id'] in ['slot_06','slot_07','slot_08']:print(c['id'],{n:c[n] for n in ['trigger_count','fail_hit','first_failure_cycle','false_positive_cycles','missed_violation_cycles']})
print('method freezes',len(list((OUT/'methods').glob('*/*/freeze.json'))))
if (OUT/'legacy_checker_crosscheck.json').exists():
 bad=[c for c in read(OUT/'legacy_checker_crosscheck.json')['checks'] if not c['independent_ast_evaluation_matches']]
 print('CROSSCHECK_FAILURES',len(bad),bad[:10])
if (OUT/'parent_results.json').exists():
 print('FULL_PASSES',[(r['case'],r['method']) for r in read(OUT/'parent_results.json') if r['complete_pass'] is True])
if (OUT/'history_refinement.json').exists():
 print('HISTORY_CONFLICTS',[(r['parent_bug_id'],[(v['history_depth'],v['conflict_groups']) for v in r['levels']]) for r in read(OUT/'history_refinement.json')])
