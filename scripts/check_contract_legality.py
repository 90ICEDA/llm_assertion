from run_repair_contract import ROOT,OUT,IDS,definition,read,dump
findings=[]
for p in (OUT/'frozen').glob('*/*_inputs.json'):
 if p.parent.name!='fifo':continue
 rows=read(p);bad=[]
 for i,(a,b) in enumerate(zip(rows,rows[1:]),1):
  if a['rst_ni'] and b['rst_ni'] and a['push_i'] and not a['pop_i'] and (not b['push_i'] or a['data_i']!=b['data_i']):bad.append(i)
 findings.append({'path':str(p.relative_to(ROOT)),'abandoned_stalled_input_cycles':bad})
print(findings)
for base in ROOT.glob('rtl_cases*'):
 p=base/IDS['fifo']
 if p.is_dir():
  for name in ['spec.md','experiment/spec.txt']:
   if (p/name).exists():print('SPEC',str(p/name),(p/name).read_text())
  if (p/'correct.v').exists():
   text=(p/'correct.v').read_text();print('FIFO_PROTOCOL',[(i+1,s) for i,s in enumerate(text.splitlines()) if any(w in s.lower() for w in ['assert','depth == 0','depth > 0','push_i','full_o'])][-35:])
dump(OUT/'input_legality_precheck.json',findings)
