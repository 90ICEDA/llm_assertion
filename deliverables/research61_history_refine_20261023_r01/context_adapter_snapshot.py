"""One local continuation with exact, source-bound OP RTL excerpts.

Changed prompt information scope is explicit. Native DUT remains the complete
original decoder. A reversible ndiff carries the second OP block without a
duplicate copy. No SVA or model output is hand-corrected.
"""
import argparse
import difflib
import json
from pathlib import Path
from unittest.mock import patch
import research60_local_phase as base
g=base.g
ORIGINAL_REQUEST=base.request


def block(path,start_marker,end_marker):
    lines=path.read_text().splitlines(keepends=True)
    start=next(i for i,s in enumerate(lines) if start_marker in s)
    end=next(i for i in range(start+1,len(lines)) if end_marker in lines[i])
    return dict(file=path.relative_to(g.ROOT).as_posix(),file_sha256=g.old.digest(path),start_line=start+1,end_line=end,text=''.join(lines[start:end]))


def request(prep,feedback,seed):
    req=ORIGINAL_REQUEST(prep,feedback,seed)
    body=json.loads(req['messages'][1]['content'])
    before=block(prep/'before/ibex_decoder.sv','      OPCODE_OP: begin','      OPCODE_MISC_MEM: begin')
    after=block(prep/'after/ibex_decoder.sv','      OPCODE_OP: begin','      OPCODE_MISC_MEM: begin')
    delta=list(difflib.ndiff(before['text'].splitlines(keepends=True),after['text'].splitlines(keepends=True)))
    assert ''.join(difflib.restore(delta,1))==before['text'] and ''.join(difflib.restore(delta,2))==after['text']
    # ndiff without redundant unchanged lines, with line indices to reconstruct.
    edits=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(a=before['text'].splitlines(keepends=True),b=after['text'].splitlines(keepends=True),autojunk=False).get_opcodes():
        if tag!='equal':edits.append(dict(before_start_zero_based=a,before_end_exclusive=b,replacement_lines=after['text'].splitlines(keepends=True)[c:d]))
    reconstructed=before['text'].splitlines(keepends=True)
    for e in reversed(edits):reconstructed[e['before_start_zero_based']:e['before_end_exclusive']]=e['replacement_lines']
    assert ''.join(reconstructed)==after['text']
    assignments={}
    for rev in ('before','after'):
        p=prep/rev/'ibex_decoder.sv';lines=p.read_text().splitlines()
        assignments[rev]=[dict(line=i+1,text=s) for i,s in enumerate(lines) if 'assign instr =' in s or 'assign opcode =' in s or 'assign illegal_insn_o' in s or "illegal_insn      = 1'b0" in s or "illegal_insn         = 1'b0" in s]
    body['rtl']=dict(input_scope='Exact OP-case excerpts and signal assignments, NOT entire decoder in this prompt. Full original files are hashed and used for native execution.',
        before_op=before,after_op={k:v for k,v in after.items() if k!='text'},after_op_reconstruction=dict(base='before_op.text',edits=edits,rule='Apply replacements in reverse index order to original before text split into lines retaining line endings.'),signal_assignments=assignments,
        omitted='Unrelated opcode blocks, package enums and unused signal declarations. The confirmed public OP/BRANCH obligations and interface semantics are unchanged; this is not a controlled comparison to full-context generation.')
    body['task']+=' The original before/after OP blocks are provided with an exact reconstructable line edit, not a hand-written DUT approximation. Choose OP assertions from the confirmed obligation; the fixed BRANCH property must remain unchanged.'
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    req['options']['num_ctx']=12288
    return req


def run(out):
    def validate(rtl):
        before=rtl['before_op'];after=rtl['after_op']
        for r in (before,after):
            p=g.ROOT/r['file'];assert g.old.digest(p)==r['file_sha256']
        p=g.ROOT/before['file'];original=''.join(p.read_text().splitlines(keepends=True)[before['start_line']-1:before['end_line']])
        assert original==before['text']
        lines=original.splitlines(keepends=True)
        for e in reversed(rtl['after_op_reconstruction']['edits']):lines[e['before_start_zero_based']:e['before_end_exclusive']]=e['replacement_lines']
        p=g.ROOT/after['file'];assert ''.join(lines)==''.join(p.read_text().splitlines(keepends=True)[after['start_line']-1:after['end_line']])
        for rev,assignments in rtl['signal_assignments'].items():
            lines=(base.P/rev/'ibex_decoder.sv').read_text().splitlines()
            assert all(lines[r['line']-1]==r['text'] for r in assignments)
    try:
        with patch.object(base,'request',request):base.run(out,iterations=1,timeout=900,context_validator=validate)
    finally:
        if out.exists():
            import shutil
            shutil.copy2(__file__,out/'context_adapter_snapshot.py')
            protocol=g.read(out/'protocol.json');protocol['changes']='One real local7B generation with exact source-bound OP excerpts and reconstructable before/after edit; complete original RTL remains native DUT. Different context scope, not a controlled comparison.'
            protocol['prior_attempt']='research60_local_20261023_r01: one submitted generation cancelled; final usage unavailable; no native candidate.'
            g.dump(out/'protocol.json',protocol)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.out.resolve())
