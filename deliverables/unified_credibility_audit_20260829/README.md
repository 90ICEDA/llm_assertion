# Unified credibility audit delivery

This delivery contains the sample-flow/accounting audit, probe-order sensitivity replay, blinded manual-separability review, replayable witnesses, append-only unexpected-behavior log, and a hash-inventoried archive of raw evidence and scripts.

- `raw_evidence.tar.gz`: actual raw files with repository-relative paths.
- `artifact_inventory.csv`: per-file role, byte size and SHA-256.
- `SHA256SUMS.txt`: archive and inventory checksums.
- `artifacts/`: convenient unpacked copies of the three new audit deliverables.
- `unexpected_behavior.md`: append-only anomaly history; resolved false alarms are retained.

Compiled `.out`, `.pyc` and VCD rebuild products are omitted; result JSON retains commands, tool outputs, return codes, timeout flags, hashes and verdicts, while stimuli/checkers/SVA are included for replay.
