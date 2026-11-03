# research17_loop source review

Scope: static read-only review of `scripts/research17_loop.py`, `research17_model.py`, and `research17_fifo_feedback.py` while the main experiment is running. No new independent-test artifact was opened. No main experiment file was modified. Findings describe source behavior, not model or test outcomes.

## Main closed loop

The core keeps one common accepted initial candidate, obtains real search cases using strict five-condition validation, replays both controls and mutants, checks the sampled reference queue independently, and runs `decide` on all development rows and nonempty acquired target keys. A proposal only replaces the accepted version after the gate and health checks pass. Compile/interface failures and rejected edits are retained. Native control failures are checked for all properties, avoiding the obligation projection blind spot noted in the earlier audit.

The strict gate rejects unknown attribution in the after-ledger, missing historical identities, lost detections/triggers, and uncorrected acquired targets. Later post-first-violation evidence remains excluded as attribution unknown, so acceptance remains finite-prefix/historical evidence scoped; it is not full-case or global protection.

## Test isolation

No direct test-to-training data flow was found. Core holdout inputs are created only after core freeze. Its return value is not used by `main`; the decision whether to run four arms depends on the earlier development `core['resolved']`, not holdout scores. Each arm restarts from the same initial candidate. `Model.call` only receives explicitly supplied development feedback; its global call list is used for cost accounting, not model conversation history. The four-arm shared test is created after all four candidates freeze.

This conclusion requires the operator to retain the frozen source/protocol and not inspect core test outcomes to alter later arm prompts, selection, hyperparameters, or implementation. Merely writing the core test before arm execution does not itself leak its contents, but actual subsequent manual adaptation would make it development data.

## Fairness issue to disclose or fix in a new execution

`refine` gathers `targets` from all case ledgers at line 138. Gate-enabled arms must repair all acquired targets. However, plain acceptance at lines 152-157 loads only `case_{len(cases)-1}`. If search finds both Depth 2 and Depth 5 witnesses, B validates only the final depth while D validates both. This changes current-gap validation scope as well as historical non-regression. Therefore any B/D difference cannot be attributed solely to the non-regression mechanism in this implementation.

Rejected-proposal feedback at line 169 similarly gives plain arms only the final case and guarded arms all cases. Historical feedback is an intended mechanism difference, but omitting an earlier still-current acquired target is an additional confound. In a later experiment, define the same acquired-current-case set for B/D, validate all its targets in both arms, and let only historical protection checks differ. Preserve the present run and report this limitation if it has already started; do not silently edit archived protocol/results.

A/C have no acquired gap and may legitimately choose `keep`; report this as retention with no discovered improvement, not successful repair of the searched gap. All arms receive the common specification; only B/D receive acquired search evidence.

## Reporting and scope

Holdout IDs include the mutant mode. Consequently, the same fixed input schedule is rerun and receives a distinct evidence identity for each of four mutants. Legal row counts include these repeated controls; label them replay sample rows, not independent legal transactions/scenarios. Gap counts should remain separately deduplicated by obligation and fault mechanism.

The model schema constrains syntax to predicates plus same/next-sample implication, and every predicate is selected by the actual model. This is narrower than unrestricted SVA. `drain_due` is an environment fair-drain checkpoint and the reference count is monitor state; success is for monitor-assisted bounded transaction assertions, not a DUT-only unbounded liveness proof.

Shared global model/token/time caps can terminate later arms before their individual maxima. Report actual incomplete arms and cost differences instead of asserting equal realized budgets. Core pilot calls and search costs must remain separately visible.

No issue identified here invalidates the core development repair check; the main actionable limitation is the differing current-target scope in the four-arm comparison.
