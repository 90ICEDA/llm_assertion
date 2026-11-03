# Trace Router Protocol

The router chooses `raw`, `temporal`, or `both` from trace length, first-divergence
distance, divergence-window length, differing-signal count, cross-cycle status,
explicit-delay status, control/data signal ratio, and model type.

Cases are split by independent parent bug. A parent and all of its trace variants
belong wholly to dev or wholly to test. `fit-lock` is the only command allowed to
read dev outcomes while choosing thresholds. It writes a locked JSON policy with a
SHA-256 over its complete contents. `route-test` verifies that hash and reads no
result file. Only after test routing has been written may `evaluate-test` join the
frozen decisions to test outcomes.

Commands:

```powershell
python src/trace_router.py fit-lock
python src/trace_router.py route-test
python src/trace_router.py evaluate-test --output outputs/trace_router/test_evaluation.csv
```

The current policy is explicitly marked as a legacy prototype because its temporal
arm predates the strict temporal-relation abstraction contract. Refit and relock it
after compliant temporal results are available; do not treat the current test score
as the final benchmark result.
