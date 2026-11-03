"""Keep original six-parent denominator separate from new engineered cohorts."""
from research15_pipeline import ROOT,OUT,read,dump


def run():
    previous=read(ROOT/'deliverables/research_search_20261014_r01/parent_method_results.json')
    reasons={
        'onehot':'Regression only this round; no new complete native LLM assertion-set acceptance for this parent.',
        'fifo':'Original FIFO presented defect still lacks confirmed target witness. Depth>=2 artificial boundary mutants are a separate engineering cohort.',
        'filter':'Previous four-policy candidate diagnostics exist; complete native LLM obligation coverage not established.',
        'stat':'Cited upstream module has a different interface from the local two-cycle synthetic example. Upstream timing/overlap provenance unconfirmed.',
        'spill':'Collision-empty subset has witnesses; invalid-payload obligation specification remains unresolved.',
        'intr':'Mask/timing specification remains unresolved; cannot claim whole-parent success.'}
    parents=[]
    for case,reason in reasons.items():
        rows=[r for r in previous if r['case']==case]
        parents.append(dict(parent=case,whole_parent_native_llm_pass=False,whole_parent_status='not_established',
            reason=reason,previous_development_search=[{k:r.get(k) for k in (
                'method','queries','gap_count','fp_gaps','fn_gaps','unknown_spec_queries','unsupported_candidate_query_entries','covered_obligations')}
                for r in rows],
            previous_execution_scope='Procedural diagnostic candidate search, not native SVA full parent success.',
            new_independent_test_status='not_run_for_this_original_parent'))
    result=dict(original_parent_denominator=6,complete_native_llm_parent_passes=0,
        unresolved_or_not_fully_verified_parents=6,parents=parents,
        separate_cohorts=[dict(name='complex_axis_fifo_boundary_mutants',historical_original_bug=False,
                              status_source='research15_native_20261015_r01/summary.json'),
                         dict(name='Ibex54_original_compressed_decoder',historical_original_bug=True,learned_assertion_set=False),
                         dict(name='Ibex166_original_decoder',historical_original_bug=True,learned_assertion_set=False)],
        scope='Do not merge local obligation improvements or engineered fault witnesses into the original six-parent full-success denominator.')
    dump(OUT/'parent_status.json',result)
    return result


if __name__=='__main__':run()
