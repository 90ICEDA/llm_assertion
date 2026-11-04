"""Recognize a linked native local -> compose -> regenerate chain, not labels."""
def ordered_stages(stages):
    expected=('local','compose','regenerate');position=0
    for stage in stages:
        if stage==expected[position]:
            position+=1
            if position==len(expected):return True
    return False

def chains(history):
    native=[r for r in history if r.get('event')=='native_measured']
    result=[]
    for i in range(len(native)-2):
        a,b,c=native[i:i+3]
        if [r.get('stage') for r in (a,b,c)]!=['local','compose','regenerate']:continue
        if not a['before_sha256']==b['before_sha256']==c['before_sha256']:continue
        if any(r['decision'].get('critical_unknown') for r in (a,b,c)):continue
        if any(r['decision']['accepted'] or not r['decision']['semantic_failure'] for r in (a,b)):continue
        receipts=[a.get('fallback_receipt',{}),b.get('fallback_receipt',{})]
        if [r.get('stage') for r in receipts]!=['local','compose']:continue
        if any(receipt.get('active_sha256')!=a['before_sha256'] or not receipt.get('native_bindings') for receipt in receipts):continue
        result.append(dict(rounds=[r['round'] for r in (a,b,c)],active_sha256=a['before_sha256'],
            regeneration_accepted=c['decision']['accepted'],regeneration_complete=c['decision']['complete']))
    return result

def structural_chains(history):
    """Partial local improvement -> certified missing component -> fallback.

    This is distinct from a rejected-local-proposal chain. It never pretends
    that the accepted local proposal failed, or that a certificate is a model
    call. All three real proposals must have confirmed native measurements.
    """
    result=[]
    for i,local in enumerate(history):
        if local.get('event')!='native_measured' or local.get('stage')!='local':continue
        d=local['decision']
        if not d['accepted'] or d['complete'] or d['critical_unknown']:continue
        active=local['retained_sha256'];certificate=None;composition=None
        for r in history[i+1:]:
            if r.get('event')=='structural_local_domain_empty':
                c=r['certificate']
                if c.get('active_sha256')==active and c.get('missing_obligations') and c.get('confirmed_target_ids') and c.get('native_bindings'):certificate=c
            if r.get('event')!='native_measured':continue
            if r.get('before_sha256')!=active or r['decision'].get('critical_unknown'):break
            if r['stage']=='compose':
                receipt=r.get('fallback_receipt',{})
                if (certificate and not r['decision']['accepted'] and r['decision']['semantic_failure']
                    and receipt.get('stage')=='compose' and receipt.get('active_sha256')==active and receipt.get('native_bindings')):
                    composition=r
                else:break
            elif r['stage']=='regenerate' and composition:
                result.append(dict(rounds=[local['round'],composition['round'],r['round']],active_after_local_sha256=active,
                    certificate_kind='local_domain_empty',missing_obligations=certificate['missing_obligations'],
                    regeneration_accepted=r['decision']['accepted'],regeneration_complete=r['decision']['complete']))
                break
            else:break
    return result
