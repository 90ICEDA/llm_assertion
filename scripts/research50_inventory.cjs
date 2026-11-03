// Read saved input containers with native Windows filesystem access.
// This emits row values, not Python-compatible hashes: Python computes those.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const [index, output] = process.argv.slice(2);
if (!index || !output || fs.existsSync(output)) throw Error('New index/output required');
const root = path.resolve(__dirname, '..');
const skipped = 'deliverables/research50_prepare_20261022_r01/';
const unique = [], lookup = new Map(), sources = [], unreadable = [];
function canonical(v) {
  if (Array.isArray(v)) return '['+v.map(canonical).join(',')+']';
  if (v && typeof v === 'object') return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
  return JSON.stringify(v);
}
function* inputs(v) {
  if (Array.isArray(v)) {
    if (v.length && v.every(r=>r && typeof r==='object' && ['cycle','intent','ready','data'].every(k=>k in r))) yield v;
    else for (const item of v) yield* inputs(item);
  } else if (v && typeof v==='object') {
    if (Array.isArray(v.rows)) yield* inputs(v.rows);
    else for (const [key,item] of Object.entries(v))
      if (!['ledger','trace','reference_trace','messages','metrics'].includes(key)) yield* inputs(item);
  }
}
const paths = fs.readFileSync(index,'utf8').replace(/^\uFEFF/,'').trim().split(/\r?\n/);
for (const item of paths) {
  const rel = item.replaceAll('\\','/');
  if (rel.startsWith(skipped)) continue;
  if (!rel.startsWith('deliverables/') || rel.split('/').includes('..')) throw Error('Unexpected source');
  try {
    const bytes = fs.readFileSync(path.join(root,rel));
    const value = JSON.parse(bytes.toString('utf8').replace(/^\uFEFF/,''));
    const ids = new Set();
    for (const rows of inputs(value)) {
      const key=canonical(rows);
      if (!lookup.has(key)) { lookup.set(key,unique.length); unique.push(rows); }
      ids.add(lookup.get(key));
    }
    if (ids.size) sources.push({path:rel,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),row_ids:[...ids]});
  } catch (e) { unreadable.push({path:rel,error:e.name}); }
}
fs.writeFileSync(output,JSON.stringify({format:'raw_input_inventory_v1',sources,unique_rows:unique,unreadable,
  file_index_sha256:crypto.createHash('sha256').update(fs.readFileSync(index)).digest('hex')}));
console.log(JSON.stringify({sources:sources.length,unique_rows:unique.length,unreadable:unreadable.length}));
if (unreadable.length) process.exitCode=1;
